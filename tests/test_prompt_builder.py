from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leaps_harness import PromptBuildError, build_prompt, build_prompt_from_file
from leaps_harness.cli import main


class PromptBuilderTests(unittest.TestCase):
    def test_build_prompt_renders_nested_dictionary_values(self) -> None:
        prompt = build_prompt(
            "Owner: {{ person.name }}\nRole: {{ person.role }}\nUnits:\n{{ work_units }}",
            {
                "person": {
                    "name": "Mina",
                    "role": "part lead",
                },
                "work_units": [
                    {
                        "title": "API gateway cache",
                        "status": "in progress",
                    }
                ],
            },
        )

        self.assertIn("Owner: Mina", prompt)
        self.assertIn("Role: part lead", prompt)
        self.assertIn('"title": "API gateway cache"', prompt)

    def test_build_prompt_reports_missing_values(self) -> None:
        with self.assertRaises(PromptBuildError):
            build_prompt("Hello {{ missing }}", {})

    def test_build_prompt_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            template_path = workspace / "template.txt"
            template_path.write_text("Hello {{ name }}", encoding="utf-8")

            prompt = build_prompt_from_file(template_path, {"name": "Harness"})

            self.assertEqual(prompt, "Hello Harness")

    def test_render_prompt_cli_uses_json_values_and_var_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            template_path = workspace / "template.txt"
            values_path = workspace / "values.json"
            output_path = workspace / "prompt.txt"
            template_path.write_text("Name: {{ person.name }}\nRole: {{ person.role }}", encoding="utf-8")
            values_path.write_text(
                json.dumps({"person": {"name": "Mina", "role": "part lead"}}),
                encoding="utf-8",
            )

            code = main(
                [
                    "render-prompt",
                    str(template_path),
                    "--values",
                    str(values_path),
                    "--var",
                    "person.role=group lead",
                    "--output",
                    str(output_path),
                ]
            )

            self.assertEqual(code, 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "Name: Mina\nRole: group lead")

    def test_render_prompt_cli_writes_to_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            template_path = workspace / "template.txt"
            template_path.write_text("Hello {{ name }}", encoding="utf-8")
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                code = main(["render-prompt", str(template_path), "--var", "name=Harness"])

            self.assertEqual(code, 0)
            self.assertEqual(buffer.getvalue(), "Hello Harness\n")


if __name__ == "__main__":
    unittest.main()
