from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leaps_harness.planning import build_workflow_plan
from leaps_harness.validation import validate_workflow_file


class ExampleWorkflowTests(unittest.TestCase):
    def test_github_review_knowledge_example_validates_with_claude_config(self) -> None:
        workflow_path = ROOT / "examples" / "github_review_knowledge" / "workflow.json"
        config_path = ROOT / "configs" / "claude_github_review_knowledge.example.json"

        errors = validate_workflow_file(workflow_path, config_paths=[config_path])
        plan = build_workflow_plan(workflow_path, config_paths=[config_path])

        self.assertEqual(errors, [])
        self.assertEqual(plan["workflow"], "github_review_knowledge_example")
        self.assertEqual(plan["step_count"], 4)
        self.assertEqual(plan["steps"][0]["id"], "select_module_files")
        self.assertEqual(plan["steps"][2]["id"], "draft_knowledge_update")

    def test_github_review_knowledge_selects_only_module_scope(self) -> None:
        example_dir = ROOT / "examples" / "github_review_knowledge"
        completed = subprocess.run(
            [
                sys.executable,
                "tools/select_module_files.py",
                "input/sample_repo",
                "bpc",
            ],
            cwd=example_dir,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        selection = json.loads(completed.stdout)
        paths = [item["path"] for item in selection["selected_files"]]
        self.assertIn("isp/bpc/bpc.cpp", paths)
        self.assertIn("isp/bpc/bpc.h", paths)
        self.assertIn("isp/common/fixed_point.h", paths)
        self.assertIn("tests/bpc_test.cpp", paths)
        self.assertNotIn("isp/demosaic/demosaic.cpp", paths)

    def test_github_review_knowledge_applies_structured_update(self) -> None:
        example_dir = ROOT / "examples" / "github_review_knowledge"
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            worker_output = workspace / "worker_output.json"
            knowledge_root = workspace / "REPO_KNOWLEDGE"
            worker_output.write_text(
                json.dumps(
                    {
                        "module": "bpc",
                        "purpose": "bad pixel correction",
                        "summary": "BPC clamps boundaries and replaces outliers.",
                        "confidence": "medium",
                        "module_doc_markdown": "# Module: bpc\n\nPurpose: bad pixel correction.",
                        "patterns": [
                            {
                                "name": "boundary",
                                "markdown": "Clamp reads at image edges.",
                            }
                        ],
                        "skills": [
                            {
                                "name": "debug_bpc",
                                "markdown": "# Debug BPC\n\n## Goal\nInspect outlier replacement.",
                            }
                        ],
                        "todos": ["Confirm SIMD path."],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/apply_knowledge_update.py",
                    "bpc",
                    str(knowledge_root),
                    str(worker_output),
                ],
                cwd=example_dir,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["module"], "bpc")
            self.assertTrue((knowledge_root / "modules" / "bpc.md").exists())
            self.assertTrue((knowledge_root / "patterns" / "boundary.md").exists())
            self.assertTrue((knowledge_root / "skills" / "debug_bpc.md").exists())
            self.assertIn("Confirm SIMD path.", (knowledge_root / "_inbox" / "discovered_notes.md").read_text())

    def test_weekly_style_transfer_example_validates_with_claude_config(self) -> None:
        workflow_path = ROOT / "examples" / "weekly_style_transfer" / "workflow.json"
        config_path = ROOT / "configs" / "claude_weekly_style_transfer.example.json"

        errors = validate_workflow_file(workflow_path, config_paths=[config_path])
        plan = build_workflow_plan(workflow_path, config_paths=[config_path])

        self.assertEqual(errors, [])
        self.assertEqual(plan["workflow"], "weekly_style_transfer_example")
        self.assertEqual(plan["step_count"], 7)
        self.assertEqual(plan["steps"][4]["type"], "iterative_review")
        self.assertEqual(plan["steps"][6]["id"], "build_evaluation_report")

    def test_weekly_style_transfer_contract_validator_accepts_hidden_reference(self) -> None:
        example_dir = ROOT / "examples" / "weekly_style_transfer"
        completed = subprocess.run(
            [
                sys.executable,
                "tools/validate_report_contract.py",
                "expected/hidden_group_weekly.md",
                "input/work_units.json",
            ],
            cwd=example_dir,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["passed"])

    def test_weekly_style_transfer_evaluation_report_generator(self) -> None:
        example_dir = ROOT / "examples" / "weekly_style_transfer"
        history_path = example_dir / "history.json"
        review_path = example_dir / "review.json"
        contract_path = example_dir / "contract.json"
        draft_path = example_dir / "expected" / "hidden_group_weekly.md"
        history_path.write_text(
            json.dumps(
                [
                    {
                        "attempt": 1,
                        "passed": True,
                        "status": "success",
                        "feedback": "",
                        "draft": str(draft_path),
                    }
                ]
            ),
            encoding="utf-8",
        )
        review_path.write_text(
            json.dumps(
                {
                    "status": "success",
                    "scores": {
                        "format_match": 1.0,
                        "tone_match": 1.0,
                    },
                }
            ),
            encoding="utf-8",
        )
        contract_path.write_text(json.dumps({"passed": True, "errors": []}), encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/build_evaluation_report.py",
                    "input/group_style_samples",
                    "expected/hidden_group_weekly.md",
                    "history.json",
                    "review.json",
                    "contract.json",
                ],
                cwd=example_dir,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
        finally:
            history_path.unlink(missing_ok=True)
            review_path.unlink(missing_ok=True)
            contract_path.unlink(missing_ok=True)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("# Weekly Style Transfer Evaluation", completed.stdout)
        self.assertIn("그룹 주간보고", completed.stdout)
        self.assertIn("## Group Style Samples", completed.stdout)
        self.assertIn("## Hidden Group Reference", completed.stdout)
        self.assertIn("### Attempt 1", completed.stdout)
        self.assertIn("## Deterministic Contract Validation", completed.stdout)


if __name__ == "__main__":
    unittest.main()
