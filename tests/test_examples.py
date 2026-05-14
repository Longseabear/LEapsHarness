from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leaps_harness.planning import build_workflow_plan
from leaps_harness.validation import validate_workflow_file


class ExampleWorkflowTests(unittest.TestCase):
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
