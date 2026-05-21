from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .policy import ExecutionPolicy, PolicyError
from .template import render_template


class AgentAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentResult:
    text: str
    metadata: dict[str, Any]


class EchoAgentAdapter:
    def run(self, input_text: str) -> AgentResult:
        return AgentResult(
            text="# Echo Agent Response\n\n" + input_text,
            metadata={"adapter_type": "echo"},
        )


class CommandAgentAdapter:
    def __init__(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 120,
        input_mode: str = "stdin",
    ) -> None:
        if not command:
            raise AgentAdapterError("Command agent adapter requires a non-empty command.")
        if input_mode not in {"stdin", "argument"}:
            raise AgentAdapterError("Command agent adapter input_mode must be 'stdin' or 'argument'.")
        self.command = command
        self.cwd = cwd
        self.env = env or {}
        self.timeout_seconds = timeout_seconds
        self.input_mode = input_mode

    def run(self, input_text: str) -> AgentResult:
        env = os.environ.copy()
        env.update(self.env)
        command = self.command
        stdin = input_text
        if self.input_mode == "argument":
            command = [*self.command, input_text]
            stdin = None
        run_kwargs: dict[str, Any] = {
            "cwd": self.cwd,
            "env": env,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "capture_output": True,
            "timeout": self.timeout_seconds,
            "check": False,
        }
        if stdin is None:
            run_kwargs["stdin"] = subprocess.DEVNULL
        else:
            run_kwargs["input"] = stdin
        try:
            completed = subprocess.run(command, **run_kwargs)
        except OSError as exc:
            raise AgentAdapterError(f"Failed to start agent command: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AgentAdapterError(f"Agent command timed out after {self.timeout_seconds} seconds.") from exc

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
            raise AgentAdapterError(f"Agent command failed with exit code {completed.returncode}.")
        return AgentResult(text=completed.stdout, metadata=metadata)


def build_agent_adapter(
    name: str,
    config: dict[str, Any],
    workspace_dir: Path,
    values: dict[str, str],
    policy: ExecutionPolicy | None = None,
) -> EchoAgentAdapter | CommandAgentAdapter:
    adapter_type = config.get("type", "echo")
    if adapter_type == "echo":
        return EchoAgentAdapter()
    if adapter_type == "command":
        command = config.get("command")
        if not isinstance(command, list):
            raise AgentAdapterError(f"Agent adapter '{name}' command must be a list.")
        rendered_command = [render_template(str(part), values) for part in command]
        cwd = _resolve_path(config.get("cwd", "."), workspace_dir)
        env = {key: render_template(str(value), values) for key, value in config.get("env", {}).items()}
        timeout_seconds = int(config.get("timeout_seconds", 120))
        input_mode = str(config.get("input_mode", "stdin"))
        if policy:
            try:
                policy.check_command(
                    f"agent adapter '{name}'",
                    rendered_command,
                    cwd=cwd,
                    timeout_seconds=timeout_seconds,
                    env=env,
                )
            except PolicyError as exc:
                raise AgentAdapterError(str(exc)) from exc
        return CommandAgentAdapter(
            rendered_command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            input_mode=input_mode,
        )
    raise AgentAdapterError(f"Unsupported agent adapter type '{adapter_type}' for adapter '{name}'.")


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()
