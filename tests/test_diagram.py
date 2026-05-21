from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leaps_harness import build_run_diagram, build_workflow_diagram
from leaps_harness.cli import main


class DiagramTests(unittest.TestCase):
    def test_workflow_diagram_extracts_artifact_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "input.txt").write_text("source", encoding="utf-8")
            (workspace / "template.txt").write_text("Draft from {{ source }}", encoding="utf-8")
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "diagram_workflow",
                        "steps": [
                            {
                                "id": "collect",
                                "type": "copy_file",
                                "source": "input.txt",
                            },
                            {
                                "id": "build_prompt",
                                "type": "prompt",
                                "template": "template.txt",
                                "data": {
                                    "source": {
                                        "from_artifact": "collect.path",
                                        "format": "text",
                                    }
                                },
                            },
                            {
                                "id": "draft",
                                "type": "llm",
                                "prompt": "{{ artifact.build_prompt.prompt }}",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            diagram = build_workflow_diagram(workflow_path)

            self.assertIn("```mermaid", diagram)
            self.assertIn('s0["collect<br/>copy_file"]', diagram)
            self.assertIn("s0 --> s1", diagram)
            self.assertIn("s1 --> s2", diagram)
            self.assertIn("- Validation: `passed`", diagram)

    def test_run_diagram_renders_step_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "workflow": "run_diagram_workflow",
                        "run_id": "diagram-run",
                        "status": "failed",
                        "steps": [
                            {
                                "id": "draft",
                                "type": "iterative_review",
                                "status": "succeeded",
                                "elapsed_seconds": 1.25,
                                "outputs": {"attempts": 3, "passed": True},
                            },
                            {
                                "id": "publish",
                                "type": "command",
                                "status": "reused",
                                "elapsed_seconds": 0.2,
                            },
                            {
                                "id": "notify",
                                "type": "command",
                                "status": "failed",
                                "error": "command failed",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            diagram = build_run_diagram(manifest_path)

            self.assertIn("# Run Diagram: diagram-run", diagram)
            self.assertIn("attempts: 3", diagram)
            self.assertIn("passed: True", diagram)
            self.assertIn("s0 --> s1", diagram)
            self.assertIn("class s0 succeeded;", diagram)
            self.assertIn("class s1 reused;", diagram)
            self.assertIn("class s2 failed;", diagram)

    def test_diagram_cli_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "input.txt").write_text("source", encoding="utf-8")
            workflow_path = workspace / "workflow.json"
            workflow_path.write_text(
                json.dumps(
                    {
                        "name": "diagram_cli_workflow",
                        "steps": [
                            {
                                "id": "collect",
                                "type": "copy_file",
                                "source": "input.txt",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_path = workspace / "diagrams" / "workflow.md"

            exit_code = main(["diagram", "workflow", str(workflow_path), "--output", str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.exists())
            self.assertIn("# Workflow Diagram: diagram_cli_workflow", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
