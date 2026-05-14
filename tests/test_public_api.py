from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leaps_harness import WorkflowPlan, WorkflowResult, plan_workflow, run_workflow, validate_workflow


class PublicApiTests(unittest.TestCase):
    def test_public_api_returns_typed_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "input.txt").write_text("hello", encoding="utf-8")
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "public_api_workflow",
                        "artifact_root": "runs",
                        "vars": {"input_path": "input.txt"},
                        "steps": [
                            {
                                "id": "collect",
                                "type": "copy_file",
                                "source": "{{ var.input_path }}",
                                "artifact": "input.txt",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            plan = plan_workflow(workflow_path)
            validation = validate_workflow(workflow_path)
            result = run_workflow(workflow_path, run_id="public-api-run")

            self.assertIsInstance(plan, WorkflowPlan)
            self.assertTrue(plan.valid)
            self.assertEqual(plan.step_count, 1)
            self.assertTrue(validation.valid)
            self.assertIsInstance(result, WorkflowResult)
            self.assertTrue(result.succeeded)
            self.assertEqual(result.workflow, "public_api_workflow")
            self.assertTrue(result.manifest_path.exists())

    def test_public_api_accepts_single_or_multiple_configs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            workflow_path = workspace / "workflow.json"
            config_path = workspace / "config.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "config_public_api_workflow",
                        "artifact_root": "runs",
                        "steps": [
                            {
                                "id": "draft",
                                "type": "llm",
                                "adapter": "configured",
                                "prompt": {"literal": "hello"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            config_path.write_text(
                json.dumps({"llm_adapters": {"configured": {"type": "echo"}}}),
                encoding="utf-8",
            )

            self.assertTrue(validate_workflow(workflow_path, configs=config_path).valid)
            self.assertTrue(validate_workflow(workflow_path, configs=[config_path]).valid)


if __name__ == "__main__":
    unittest.main()
