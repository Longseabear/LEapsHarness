from __future__ import annotations

import json
import http.client
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leaps_harness import StepExecutionError, WorkflowRunner
from leaps_harness.agent import CommandAgentAdapter
from leaps_harness.api import HarnessApiHandler
from leaps_harness.llm import CommandLLMAdapter
from leaps_harness.planning import build_workflow_plan
from leaps_harness.validation import validate_workflow_file


class WorkflowRunnerTests(unittest.TestCase):
    def test_runs_copy_command_prompt_and_llm_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "input.json").write_text(
                json.dumps({"people": [{"name": "A"}, {"name": "B"}]}),
                encoding="utf-8",
            )
            (workspace / "normalize.py").write_text(
                "\n".join(
                    [
                        "import json, pathlib, sys",
                        "data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))",
                        "print(json.dumps({'count': len(data['people'])}))",
                    ]
                ),
                encoding="utf-8",
            )
            (workspace / "prompt.txt").write_text("Count payload:\n{{ work_units }}\n", encoding="utf-8")
            workflow = {
                "name": "test_workflow",
                "artifact_root": "runs",
                "llm_adapters": {"default": {"type": "echo"}},
                "steps": [
                    {
                        "id": "collect",
                        "type": "copy_file",
                        "source": "input.json",
                        "artifact": "input.json",
                    },
                    {
                        "id": "normalize",
                        "type": "command",
                        "command": [sys.executable, "normalize.py", "{{ artifact.collect.path }}"],
                        "stdout_artifact": "work.json",
                    },
                    {
                        "id": "build_prompt",
                        "type": "prompt",
                        "template": "prompt.txt",
                        "data": {"work_units": {"from_artifact": "normalize.stdout", "format": "json"}},
                    },
                    {
                        "id": "draft",
                        "type": "llm",
                        "prompt": {"from_artifact": "build_prompt.prompt", "format": "text"},
                        "artifact": "report.md",
                    },
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            summary = WorkflowRunner(workflow_path, run_id="test-run").run()

            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(len(summary["steps"]), 4)
            response_path = Path(summary["steps"][-1]["outputs"]["response"])
            response = response_path.read_text(encoding="utf-8")
            self.assertIn("# Echo LLM Response", response)
            self.assertIn('"count": 2', response)
            self.assertTrue((workspace / "runs" / "test-run" / "manifest.json").exists())

    def test_command_failure_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow = {
                "name": "failing_workflow",
                "artifact_root": "runs",
                "steps": [
                    {
                        "id": "fail",
                        "type": "command",
                        "command": [sys.executable, "-c", "print('before failure'); raise SystemExit(3)"],
                    }
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            with self.assertRaises(StepExecutionError):
                WorkflowRunner(workflow_path, run_id="failed-run").run()

            manifest_path = workspace / "runs" / "failed-run" / "manifest.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            stdout_paths = [
                Path(record["path"])
                for record in manifest["artifacts"]
                if record["step_id"] == "fail" and record["name"] == "stdout.txt"
            ]
            self.assertEqual(len(stdout_paths), 1)
            self.assertIn("before failure", stdout_paths[0].read_text(encoding="utf-8"))

    def test_command_stdout_is_decoded_as_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow = {
                "name": "utf8_workflow",
                "artifact_root": "runs",
                "steps": [
                    {
                        "id": "utf8",
                        "type": "command",
                        "command": [
                            sys.executable,
                            "-c",
                            "import sys; sys.stdout.buffer.write('snowman: \\u2603'.encode('utf-8'))",
                        ],
                    }
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            summary = WorkflowRunner(workflow_path, run_id="utf8-run").run()

            stdout_path = Path(summary["steps"][0]["outputs"]["stdout"])
            self.assertEqual(stdout_path.read_text(encoding="utf-8"), "snowman: \u2603")

    def test_command_step_without_stdin_uses_devnull(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow = {
                "name": "stdin_closed_workflow",
                "artifact_root": "runs",
                "steps": [
                    {
                        "id": "no_stdin",
                        "type": "command",
                        "command": [sys.executable, "-c", "print('ok')"],
                    }
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            with patch("leaps_harness.runner.subprocess.run") as run:
                run.return_value = SimpleNamespace(stdout="ok\n", stderr="", returncode=0)
                WorkflowRunner(workflow_path, run_id="stdin-closed-run").run()

            kwargs = run.call_args.kwargs
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertNotIn("input", kwargs)

    def test_argument_mode_adapters_use_devnull_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            completed = SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

            with patch("leaps_harness.agent.subprocess.run") as run:
                run.return_value = completed
                CommandAgentAdapter(["agent"], workspace, input_mode="argument").run("prompt")

            agent_command = run.call_args.args[0]
            agent_kwargs = run.call_args.kwargs
            self.assertEqual(agent_command, ["agent", "prompt"])
            self.assertEqual(agent_kwargs["stdin"], subprocess.DEVNULL)
            self.assertNotIn("input", agent_kwargs)

            with patch("leaps_harness.llm.subprocess.run") as run:
                run.return_value = completed
                CommandLLMAdapter(["llm"], workspace, input_mode="argument").generate("prompt")

            llm_command = run.call_args.args[0]
            llm_kwargs = run.call_args.kwargs
            self.assertEqual(llm_command, ["llm", "prompt"])
            self.assertEqual(llm_kwargs["stdin"], subprocess.DEVNULL)
            self.assertNotIn("input", llm_kwargs)

    def test_policy_blocks_disallowed_command_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow = {
                "name": "policy_block_workflow",
                "artifact_root": "runs",
                "policy": {"allowed_commands": ["claude"]},
                "steps": [
                    {
                        "id": "blocked",
                        "type": "command",
                        "command": [sys.executable, "-c", "print('should not run')"],
                    }
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            with self.assertRaises(StepExecutionError):
                WorkflowRunner(workflow_path, run_id="policy-block-run").run()

            manifest = json.loads((workspace / "runs" / "policy-block-run" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertIn("not allowed by policy", manifest["error"])

    def test_policy_allows_configured_command_and_blocks_adapter_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "agent.py").write_text("import sys\nprint(sys.stdin.read())\n", encoding="utf-8")
            workflow = {
                "name": "policy_adapter_workflow",
                "artifact_root": "runs",
                "policy": {"allowed_commands": [Path(sys.executable).stem]},
                "agent_adapters": {
                    "writer": {
                        "type": "command",
                        "command": [sys.executable, "agent.py"],
                    }
                },
                "steps": [
                    {
                        "id": "agent",
                        "type": "agent",
                        "adapter": "writer",
                        "input": {"literal": "allowed"},
                    }
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            summary = WorkflowRunner(workflow_path, run_id="policy-allow-run").run()

            self.assertEqual(summary["status"], "succeeded")
            self.assertIn("allowed", Path(summary["steps"][0]["outputs"]["response"]).read_text(encoding="utf-8"))

            workflow["policy"] = {"allowed_commands": ["claude"]}
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            with self.assertRaises(StepExecutionError):
                WorkflowRunner(workflow_path, run_id="policy-adapter-block-run").run()

    def test_agent_output_contract_writes_summary_and_trace_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "agent.py").write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "prompt = sys.stdin.read()",
                        "print(json.dumps({",
                        "  'status': 'success',",
                        "  'summary': 'Drafted a structured result',",
                        "  'result': {'text': 'final answer', 'prompt_length': len(prompt)},",
                        "  'trace': {",
                        "    'decision_log': [{'step': 'read_prompt', 'note': 'used provided prompt only'}],",
                        "    'uncertainties': [],",
                        "    'artifacts': []",
                        "  }",
                        "}))",
                    ]
                ),
                encoding="utf-8",
            )
            workflow = {
                "name": "structured_agent_workflow",
                "artifact_root": "runs",
                "output_contract": {"mode": "require_json"},
                "agent_adapters": {
                    "writer": {
                        "type": "command",
                        "command": [sys.executable, "agent.py"],
                    }
                },
                "steps": [
                    {
                        "id": "agent",
                        "type": "agent",
                        "adapter": "writer",
                        "input": {"literal": "write safely"},
                    }
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            summary = WorkflowRunner(workflow_path, run_id="structured-agent-run").run()

            outputs = summary["steps"][0]["outputs"]
            envelope = json.loads(Path(outputs["envelope"]).read_text(encoding="utf-8"))
            summary_text = Path(outputs["summary"]).read_text(encoding="utf-8")
            self.assertEqual(envelope["status"], "success")
            self.assertEqual(envelope["summary"], "Drafted a structured result")
            self.assertEqual(envelope["result"]["text"], "final answer")
            self.assertEqual(envelope["trace"]["decision_log"][0]["step"], "read_prompt")
            self.assertIn("Summary: Drafted a structured result", summary_text)

    def test_output_contract_can_inject_instructions_and_reject_plain_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "agent.py").write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "prompt = sys.stdin.read()",
                        "if 'Required top-level fields' not in prompt:",
                        "    print('plain text')",
                        "else:",
                        "    print(json.dumps({'status': 'success', 'summary': 'saw instructions', 'result': prompt}))",
                    ]
                ),
                encoding="utf-8",
            )
            workflow = {
                "name": "contract_instruction_workflow",
                "artifact_root": "runs",
                "agent_adapters": {
                    "writer": {
                        "type": "command",
                        "command": [sys.executable, "agent.py"],
                        "output_contract": {
                            "mode": "require_json",
                            "inject_instructions": True,
                        },
                    }
                },
                "steps": [
                    {
                        "id": "agent",
                        "type": "agent",
                        "adapter": "writer",
                        "input": {"literal": "draft"},
                    }
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            summary = WorkflowRunner(workflow_path, run_id="contract-instruction-run").run()

            outputs = summary["steps"][0]["outputs"]
            input_text = Path(outputs["input"]).read_text(encoding="utf-8")
            envelope = json.loads(Path(outputs["envelope"]).read_text(encoding="utf-8"))
            self.assertIn("Required top-level fields", input_text)
            self.assertEqual(envelope["summary"], "saw instructions")

            workflow["agent_adapters"]["writer"]["output_contract"]["inject_instructions"] = False
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            with self.assertRaises(StepExecutionError):
                WorkflowRunner(workflow_path, run_id="contract-reject-run").run()

    def test_run_vars_override_workflow_vars(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "default.txt").write_text("default", encoding="utf-8")
            (workspace / "override.txt").write_text("override", encoding="utf-8")
            workflow = {
                "name": "vars_workflow",
                "artifact_root": "runs",
                "vars": {"input_path": "default.txt"},
                "steps": [
                    {
                        "id": "copy",
                        "type": "copy_file",
                        "source": "{{ var.input_path }}",
                        "artifact": "copied.txt",
                    }
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            summary = WorkflowRunner(
                workflow_path,
                run_id="vars-run",
                run_vars={"input_path": "override.txt"},
            ).run()

            copied_path = Path(summary["steps"][0]["outputs"]["path"])
            self.assertEqual(copied_path.read_text(encoding="utf-8"), "override")
            self.assertEqual(summary["vars"]["input_path"], "override.txt")

    def test_for_each_agent_review_and_readable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "agent.py").write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "item = json.loads(sys.stdin.read())",
                        "print('## ' + item['title'])",
                        "print('Owner: ' + item['owner'])",
                    ]
                ),
                encoding="utf-8",
            )
            (workspace / "item.txt").write_text("{{ item_json }}", encoding="utf-8")
            workflow = {
                "name": "foreach_workflow",
                "artifact_root": "runs",
                "agent_adapters": {
                    "default": {
                        "type": "command",
                        "command": [sys.executable, "agent.py"],
                    }
                },
                "steps": [
                    {
                        "id": "draft_items",
                        "type": "for_each",
                        "items": {
                            "literal": {
                                "work_units": [
                                    {
                                        "id": "work-1",
                                        "owner": "A",
                                        "title": "Alpha",
                                        "summary": "Done",
                                        "evidence": [],
                                    },
                                    {
                                        "id": "work-2",
                                        "owner": "B",
                                        "title": "Beta",
                                        "summary": "Done",
                                        "evidence": [],
                                    },
                                ]
                            }
                        },
                        "item_path": "work_units",
                        "input_template": "item.txt",
                        "combined_artifact": "combined.md",
                    },
                    {
                        "id": "review",
                        "type": "review",
                        "target": {"from_artifact": "draft_items.combined", "format": "text"},
                        "checks": [
                            {"type": "not_empty"},
                            {"type": "contains", "value": "Alpha"},
                        ],
                    },
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            summary = WorkflowRunner(workflow_path, run_id="foreach-run").run()

            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(summary["steps"][0]["outputs"]["count"], 2)
            self.assertTrue(summary["steps"][1]["outputs"]["passed"])
            readable_manifest = workspace / "runs" / "foreach-run" / "manifest.md"
            self.assertTrue(readable_manifest.exists())
            self.assertIn("draft_items", readable_manifest.read_text(encoding="utf-8"))

    def test_iterative_review_runs_three_feedback_rounds_before_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "source.txt").write_text("The blue bird was hidden in the heart.", encoding="utf-8")
            (workspace / "writer.py").write_text(
                "\n".join(
                    [
                        "import sys",
                        "prompt = sys.stdin.read()",
                        "if 'make the ending unresolved' in prompt:",
                        "    print('The blue bird waited in the cup. Nobody explained it.')",
                        "elif 'add an ordinary strange image' in prompt:",
                        "    print('The blue bird waited beside an empty cup.')",
                        "elif 'shorten the sentences' in prompt:",
                        "    print('The blue bird was quiet.')",
                        "else:",
                        "    print('A direct moral fairy tale.')",
                    ]
                ),
                encoding="utf-8",
            )
            (workspace / "reviewer.py").write_text(
                "\n".join(
                    [
                        "import json, sys",
                        "import re",
                        "prompt = sys.stdin.read()",
                        "attempt = int(re.search(r'Attempt: (\\d+)', prompt).group(1))",
                        "feedback = {",
                        "    1: 'shorten the sentences',",
                        "    2: 'add an ordinary strange image',",
                        "    3: 'make the ending unresolved',",
                        "}",
                        "if attempt >= 4 and 'Nobody explained it' in prompt:",
                        "    print(json.dumps({'status': 'success', 'feedback': ''}))",
                        "else:",
                        "    print(json.dumps({'status': 'fail', 'feedback': feedback.get(attempt, 'revise again')}))",
                    ]
                ),
                encoding="utf-8",
            )
            (workspace / "writer_prompt.txt").write_text(
                "Previous feedback: {{ previous_feedback }}\nStory: {{ source_story }}\n",
                encoding="utf-8",
            )
            (workspace / "reviewer_prompt.txt").write_text("Attempt: {{ attempt }}\nDraft:\n{{ draft }}\n", encoding="utf-8")
            workflow = {
                "name": "iterative_workflow",
                "artifact_root": "runs",
                "agent_adapters": {
                    "producer": {
                        "type": "command",
                        "command": [sys.executable, "writer.py"],
                    }
                },
                "llm_adapters": {
                    "reviewer": {
                        "type": "command",
                        "command": [sys.executable, "reviewer.py"],
                    }
                },
                "steps": [
                    {
                        "id": "collect",
                        "type": "copy_file",
                        "source": "source.txt",
                    },
                    {
                        "id": "loop",
                        "type": "iterative_review",
                        "producer_adapter": "producer",
                        "reviewer_adapter": "reviewer",
                        "producer_template": "writer_prompt.txt",
                        "reviewer_template": "reviewer_prompt.txt",
                        "max_attempts": 4,
                        "data": {
                            "source_story": {
                                "from_artifact": "collect.path",
                                "format": "text",
                            }
                        },
                    },
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            self.assertEqual(validate_workflow_file(workflow_path), [])
            plan = build_workflow_plan(workflow_path)
            self.assertEqual(
                plan["steps"][1]["outputs"],
                ["attempts", "envelope", "final", "history", "passed", "review", "summary"],
            )

            summary = WorkflowRunner(workflow_path, run_id="iterative-run").run()

            loop_outputs = summary["steps"][1]["outputs"]
            self.assertTrue(loop_outputs["passed"])
            self.assertEqual(loop_outputs["attempts"], 4)
            self.assertIn("waited in the cup", Path(loop_outputs["final"]).read_text(encoding="utf-8"))
            history = json.loads(Path(loop_outputs["history"]).read_text(encoding="utf-8"))
            self.assertEqual([item["passed"] for item in history], [False, False, False, True])
            self.assertTrue(Path(loop_outputs["envelope"]).exists())
            self.assertTrue(Path(history[0]["producer_envelope"]).exists())
            self.assertTrue(Path(history[0]["reviewer_envelope"]).exists())
            self.assertEqual(
                [item["feedback"] for item in history[:3]],
                ["shorten the sentences", "add an ordinary strange image", "make the ending unresolved"],
            )

    def test_resume_reuses_leading_succeeded_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "input.txt").write_text("source payload", encoding="utf-8")
            (workspace / "maybe_fail.py").write_text(
                "\n".join(
                    [
                        "import pathlib, sys",
                        "marker = pathlib.Path(sys.argv[1])",
                        "if not marker.exists():",
                        "    print('missing marker')",
                        "    raise SystemExit(5)",
                        "print('ok after marker')",
                    ]
                ),
                encoding="utf-8",
            )
            (workspace / "prompt.txt").write_text("Status: {{ status }}", encoding="utf-8")
            workflow = {
                "name": "resume_workflow",
                "artifact_root": "runs",
                "steps": [
                    {
                        "id": "collect",
                        "type": "copy_file",
                        "source": "input.txt",
                    },
                    {
                        "id": "maybe",
                        "type": "command",
                        "command": [sys.executable, "maybe_fail.py", "marker.txt"],
                        "stdout_artifact": "status.txt",
                    },
                    {
                        "id": "build_prompt",
                        "type": "prompt",
                        "template": "prompt.txt",
                        "data": {
                            "status": {
                                "from_artifact": "maybe.stdout",
                                "format": "text",
                            }
                        },
                    },
                ],
            }
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

            with self.assertRaises(StepExecutionError):
                WorkflowRunner(workflow_path, run_id="failed-run").run()

            failed_manifest = workspace / "runs" / "failed-run" / "manifest.json"
            (workspace / "marker.txt").write_text("ready", encoding="utf-8")

            summary = WorkflowRunner(
                workflow_path,
                run_id="resume-run",
                resume_from=failed_manifest,
            ).run()

            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(summary["steps"][0]["status"], "reused")
            self.assertEqual(summary["steps"][1]["status"], "succeeded")
            self.assertEqual(summary["reused_steps"], ["collect"])
            self.assertEqual(summary["resume_from_manifest"], str(failed_manifest.resolve()))
            prompt_path = Path(summary["steps"][2]["outputs"]["prompt"])
            self.assertIn("ok after marker", prompt_path.read_text(encoding="utf-8"))

    def test_api_runs_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps({"name": "api_workflow", "artifact_root": "runs", "steps": []}),
                encoding="utf-8",
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), HarnessApiHandler)
            server.workflow_root = workspace
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.request(
                    "POST",
                    "/runs",
                    body=json.dumps({"workflow_path": "workflow.json", "run_id": "api-run"}),
                    headers={"Content-Type": "application/json"},
                )
                response = conn.getresponse()
                body = json.loads(response.read().decode("utf-8"))
                conn.close()
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(response.status, 200)
            self.assertEqual(body["status"], "succeeded")
            self.assertTrue((workspace / "runs" / "api-run" / "manifest.md").exists())

    def test_api_plans_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "api_plan_workflow",
                        "artifact_root": "runs",
                        "vars": {"input_path": "default.txt"},
                        "steps": [],
                    }
                ),
                encoding="utf-8",
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), HarnessApiHandler)
            server.workflow_root = workspace
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.request(
                    "POST",
                    "/plans",
                    body=json.dumps({"workflow_path": "workflow.json", "vars": {"input_path": "override.txt"}}),
                    headers={"Content-Type": "application/json"},
                )
                response = conn.getresponse()
                body = json.loads(response.read().decode("utf-8"))
                conn.close()
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(response.status, 200)
            self.assertEqual(body["workflow"], "api_plan_workflow")
            self.assertEqual(body["vars"]["input_path"], "override.txt")
            self.assertFalse((workspace / "runs").exists())

    def test_runtime_config_supplies_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "agent.py").write_text("import sys\nprint('agent:' + sys.argv[1])\n", encoding="utf-8")
            (workspace / "llm_base.py").write_text("import sys\nprint('base:' + sys.argv[1])\n", encoding="utf-8")
            (workspace / "llm_override.py").write_text("import sys\nprint('override:' + sys.argv[1])\n", encoding="utf-8")
            workflow = {
                "name": "config_workflow",
                "artifact_root": "runs",
                "steps": [
                    {
                        "id": "agent_step",
                        "type": "agent",
                        "adapter": "configured_agent",
                        "input": {"literal": "hello"},
                    },
                    {
                        "id": "llm_step",
                        "type": "llm",
                        "adapter": "configured_llm",
                        "prompt": {"from_artifact": "agent_step.response", "format": "text"},
                    },
                ],
            }
            base_config = {
                "agent_adapters": {
                    "configured_agent": {
                        "type": "command",
                        "command": [sys.executable, "agent.py"],
                        "input_mode": "argument",
                    }
                },
                "llm_adapters": {
                    "configured_llm": {
                        "type": "command",
                        "command": [sys.executable, "llm_base.py"],
                        "input_mode": "argument",
                    }
                },
            }
            override_config = {
                "llm_adapters": {
                    "configured_llm": {
                        "type": "command",
                        "command": [sys.executable, "llm_override.py"],
                        "input_mode": "argument",
                    }
                },
            }
            workflow_path = workspace / "workflow.json"
            base_config_path = workspace / "base_config.json"
            override_config_path = workspace / "override_config.json"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            base_config_path.write_text(json.dumps(base_config), encoding="utf-8")
            override_config_path.write_text(json.dumps(override_config), encoding="utf-8")

            summary = WorkflowRunner(
                workflow_path,
                run_id="config-run",
                config_paths=[base_config_path, override_config_path],
            ).run()

            self.assertEqual(summary["status"], "succeeded")
            self.assertEqual(summary["config_paths"], [str(base_config_path.resolve()), str(override_config_path.resolve())])
            response_path = Path(summary["steps"][-1]["outputs"]["response"])
            self.assertIn("override:agent:hello", response_path.read_text(encoding="utf-8"))

    def test_validate_workflow_file_reports_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "bad_workflow",
                        "steps": [
                            {
                                "id": "draft",
                                "type": "llm",
                                "adapter": "missing_adapter",
                                "prompt": {"from_artifact": "missing.prompt", "format": "text"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            errors = validate_workflow_file(workflow_path)

            self.assertTrue(any("missing_adapter" in error for error in errors))
            self.assertTrue(any("missing" in error for error in errors))

    def test_validate_workflow_file_reports_invalid_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "bad_policy_workflow",
                        "policy": {"max_timeout_seconds": 0},
                        "steps": [],
                    }
                ),
                encoding="utf-8",
            )

            errors = validate_workflow_file(workflow_path)

            self.assertTrue(any("max_timeout_seconds" in error for error in errors))

    def test_review_contains_can_be_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "review_workflow",
                        "artifact_root": "runs",
                        "steps": [
                            {
                                "id": "review",
                                "type": "review",
                                "target": {"literal": "Weekly Report"},
                                "checks": [
                                    {
                                        "type": "contains",
                                        "value": "weekly report",
                                        "case_sensitive": False,
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = WorkflowRunner(workflow_path, run_id="review-run").run()

            self.assertTrue(summary["steps"][0]["outputs"]["passed"])

    def test_build_workflow_plan_does_not_create_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "input.txt").write_text("hello", encoding="utf-8")
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "plan_workflow",
                        "artifact_root": "runs",
                        "vars": {"input_path": "input.txt"},
                        "steps": [
                            {
                                "id": "copy",
                                "type": "copy_file",
                                "source": "{{ var.input_path }}",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            plan = build_workflow_plan(workflow_path, run_vars={"input_path": "override.txt"})

            self.assertEqual(plan["workflow"], "plan_workflow")
            self.assertEqual(plan["vars"]["input_path"], "override.txt")
            self.assertEqual(plan["step_count"], 1)
            self.assertEqual(plan["steps"][0]["id"], "copy")
            self.assertFalse((workspace / "runs").exists())


if __name__ == "__main__":
    unittest.main()
