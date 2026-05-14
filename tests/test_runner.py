from __future__ import annotations

import json
import http.client
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leaps_harness.api import HarnessApiHandler
from leaps_harness import StepExecutionError, WorkflowRunner
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

    def test_iterative_review_retries_until_reviewer_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "source.txt").write_text("The blue bird was hidden in the heart.", encoding="utf-8")
            (workspace / "writer.py").write_text(
                "\n".join(
                    [
                        "import sys",
                        "prompt = sys.stdin.read()",
                        "if 'make it quieter' in prompt:",
                        "    print('The blue bird waited in the cup. Nobody explained it.')",
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
                        "prompt = sys.stdin.read()",
                        "if 'waited in the cup' in prompt:",
                        "    print(json.dumps({'status': 'success', 'feedback': ''}))",
                        "else:",
                        "    print(json.dumps({'status': 'fail', 'feedback': 'make it quieter'}))",
                    ]
                ),
                encoding="utf-8",
            )
            (workspace / "writer_prompt.txt").write_text(
                "Previous feedback: {{ previous_feedback }}\nStory: {{ source_story }}\n",
                encoding="utf-8",
            )
            (workspace / "reviewer_prompt.txt").write_text("Draft:\n{{ draft }}\n", encoding="utf-8")
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
                        "max_attempts": 3,
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
            self.assertEqual(plan["steps"][1]["outputs"], ["attempts", "final", "history", "passed", "review"])

            summary = WorkflowRunner(workflow_path, run_id="iterative-run").run()

            loop_outputs = summary["steps"][1]["outputs"]
            self.assertTrue(loop_outputs["passed"])
            self.assertEqual(loop_outputs["attempts"], 2)
            self.assertIn("waited in the cup", Path(loop_outputs["final"]).read_text(encoding="utf-8"))
            history = json.loads(Path(loop_outputs["history"]).read_text(encoding="utf-8"))
            self.assertEqual([item["passed"] for item in history], [False, True])

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
