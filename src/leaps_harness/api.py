from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import ConfigError
from .planning import build_workflow_plan
from .runner import WorkflowError, WorkflowRunner


class HarnessApiHandler(BaseHTTPRequestHandler):
    server_version = "LEapsHarnessAPI/0.1"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not_found", "message": "Use GET /health, POST /plans, or POST /runs."})

    def do_POST(self) -> None:
        if self.path == "/plans":
            self._handle_plan()
            return
        if self.path == "/runs":
            self._handle_run()
            return
        self._send_json(404, {"error": "not_found", "message": "Use POST /plans or POST /runs."})

    def _handle_run(self) -> None:
        try:
            payload = self._read_json()
            workflow_path = self._resolve_workflow_path(payload)
            runner = WorkflowRunner(
                workflow_path,
                run_id=payload.get("run_id"),
                artifact_root=payload.get("artifact_root"),
                config_paths=self._resolve_config_paths(payload),
                run_vars=self._resolve_vars(payload),
            )
            summary = runner.run()
        except WorkflowError as exc:
            self._send_json(400, {"error": "workflow_error", "message": str(exc)})
            return
        except Exception as exc:
            self._send_json(500, {"error": "server_error", "message": str(exc)})
            return

        self._send_json(200, summary)

    def _handle_plan(self) -> None:
        try:
            payload = self._read_json()
            plan = build_workflow_plan(
                self._resolve_workflow_path(payload),
                config_paths=self._resolve_config_paths(payload),
                run_vars=self._resolve_vars(payload),
                artifact_root=payload.get("artifact_root"),
            )
        except (ConfigError, WorkflowError) as exc:
            self._send_json(400, {"error": "workflow_error", "message": str(exc)})
            return
        except Exception as exc:
            self._send_json(500, {"error": "server_error", "message": str(exc)})
            return

        status = 400 if plan["validation_errors"] else 200
        self._send_json(status, plan)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _resolve_workflow_path(self, payload: dict[str, Any]) -> Path:
        workflow = payload.get("workflow_path")
        if not workflow:
            raise WorkflowError("Request requires 'workflow_path'.")
        return self._resolve_path(workflow)

    def _resolve_config_paths(self, payload: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []
        legacy_config_path = payload.get("config_path")
        if legacy_config_path not in (None, ""):
            paths.append(self._resolve_path(legacy_config_path))

        config_paths = payload.get("config_paths")
        if config_paths in (None, ""):
            return paths
        if isinstance(config_paths, str):
            paths.append(self._resolve_path(config_paths))
            return paths
        if not isinstance(config_paths, list):
            raise WorkflowError("'config_paths' must be a string or list of strings.")
        for value in config_paths:
            if not isinstance(value, str):
                raise WorkflowError("'config_paths' must contain only strings.")
            paths.append(self._resolve_path(value))
        return paths

    def _resolve_vars(self, payload: dict[str, Any]) -> dict[str, Any]:
        values = payload.get("vars", {})
        if values is None:
            return {}
        if not isinstance(values, dict):
            raise WorkflowError("'vars' must be an object.")
        return values

    def _resolve_path(self, value: Any) -> Path:
        workflow = str(value)
        workflow_path = Path(str(workflow))
        if not workflow_path.is_absolute():
            workflow_root = getattr(self.server, "workflow_root", Path.cwd())
            workflow_path = Path(workflow_root) / workflow_path
        return workflow_path.resolve()

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(host: str, port: int, workflow_root: str | Path) -> None:
    server = ThreadingHTTPServer((host, port), HarnessApiHandler)
    server.workflow_root = Path(workflow_root).resolve()
    print(f"LEaps harness API listening on http://{host}:{port}")
    print(f"Workflow root: {server.workflow_root}")
    server.serve_forever()
