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
        self.assertEqual(plan["step_count"], 6)
        self.assertEqual(plan["steps"][4]["type"], "iterative_review")

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


if __name__ == "__main__":
    unittest.main()
