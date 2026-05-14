from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .template import render_template


class LLMAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMResult:
    text: str
    metadata: dict[str, Any]


class EchoLLMAdapter:
    def generate(self, prompt: str) -> LLMResult:
        return LLMResult(
            text="# Echo LLM Response\n\n" + prompt,
            metadata={"adapter_type": "echo"},
        )


class CommandLLMAdapter:
    def __init__(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 120,
        input_mode: str = "stdin",
    ) -> None:
        if not command:
            raise LLMAdapterError("Command LLM adapter requires a non-empty command.")
        if input_mode not in {"stdin", "argument"}:
            raise LLMAdapterError("Command LLM adapter input_mode must be 'stdin' or 'argument'.")
        self.command = command
        self.cwd = cwd
        self.env = env or {}
        self.timeout_seconds = timeout_seconds
        self.input_mode = input_mode

    def generate(self, prompt: str) -> LLMResult:
        env = os.environ.copy()
        env.update(self.env)
        command = self.command
        stdin = prompt
        if self.input_mode == "argument":
            command = [*self.command, prompt]
            stdin = None
        try:
            completed = subprocess.run(
                command,
                cwd=self.cwd,
                env=env,
                input=stdin,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except OSError as exc:
            raise LLMAdapterError(f"Failed to start LLM command: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMAdapterError(f"LLM command timed out after {self.timeout_seconds} seconds.") from exc

        metadata = {
            "adapter_type": "command",
            "command": self.command,
            "cwd": str(self.cwd),
            "input_mode": self.input_mode,
            "returncode": completed.returncode,
            "stderr": completed.stderr,
            "timeout_seconds": self.timeout_seconds,
        }
        if completed.returncode != 0:
            raise LLMAdapterError(f"LLM command failed with exit code {completed.returncode}.")
        return LLMResult(text=completed.stdout, metadata=metadata)


def build_llm_adapter(
    name: str,
    config: dict[str, Any],
    workspace_dir: Path,
    values: dict[str, str],
) -> EchoLLMAdapter | CommandLLMAdapter:
    adapter_type = config.get("type", "echo")
    if adapter_type == "echo":
        return EchoLLMAdapter()
    if adapter_type == "command":
        command = config.get("command")
        if not isinstance(command, list):
            raise LLMAdapterError(f"LLM adapter '{name}' command must be a list.")
        rendered_command = [render_template(str(part), values) for part in command]
        cwd = _resolve_path(config.get("cwd", "."), workspace_dir)
        env = {key: render_template(str(value), values) for key, value in config.get("env", {}).items()}
        timeout_seconds = int(config.get("timeout_seconds", 120))
        input_mode = str(config.get("input_mode", "stdin"))
        return CommandLLMAdapter(
            rendered_command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            input_mode=input_mode,
        )
    raise LLMAdapterError(f"Unsupported LLM adapter type '{adapter_type}' for adapter '{name}'.")


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()
