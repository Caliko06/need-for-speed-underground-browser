"""Shared live telemetry bridge so CLI runs stream in real time into the Web Workbench."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_UI_URL = os.environ.get("RECOMP_UI_URL", "http://127.0.0.1:5195")


class LiveEmitter:
    """Writes real-time JSONL telemetry and pushes live events to the Workbench HTTP server."""

    def __init__(
        self,
        project_root: Path,
        project_name: str,
        cmd: str,
        source: str = "cli",
        ui_url: str | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.project_name = project_name
        self.cmd = cmd
        self.source = source
        self.pid = os.getpid()
        self.ui_url = (ui_url or os.environ.get("RECOMP_UI_URL") or DEFAULT_UI_URL).rstrip("/")
        self.log_path = self.project_root / ".recomp-live.jsonl"
        self._q: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=256)
        self._ui_reachable = True
        self._thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._thread.start()

    def _sender_loop(self) -> None:
        url = f"{self.ui_url}/api/stream/ingest"
        while True:
            item = self._q.get()
            if item is None:
                return
            if not self._ui_reachable:
                continue
            try:
                data = json.dumps(item).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=0.25) as resp:
                    resp.read(16)
            except Exception:
                # UI server is not running; stop trying HTTP for subsequent ticks
                # (we still persist to .recomp-live.jsonl on disk).
                self._ui_reachable = False

    def emit(
        self,
        kind: str,
        stage: str,
        msg: str,
        *,
        running: bool = True,
        done: int | None = None,
        total: int | None = None,
        rate: float | None = None,
        addr: str | None = None,
        tool: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        ev: dict[str, Any] = {
            "ts": time.strftime("%H:%M:%S"),
            "kind": kind,
            "stage": stage,
            "project": self.project_name,
            "msg": msg,
            "running": running,
            "source": self.source,
            "pid": self.pid,
            "cmd": self.cmd,
        }
        if done is not None:
            ev["done"] = done
        if total is not None:
            ev["total"] = total
        if rate is not None:
            ev["rate"] = round(rate, 1)
        if addr:
            ev["addr"] = addr
        if tool:
            ev["tool"] = tool
        if extra:
            ev.update(extra)

        try:
            self.project_root.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev) + "\n")
        except Exception:
            pass

        if self._ui_reachable:
            try:
                self._q.put_nowait(ev)
            except queue.Full:
                try:
                    self._q.get_nowait()
                    self._q.put_nowait(ev)
                except Exception:
                    pass

    def close(self) -> None:
        try:
            self._q.put(None, timeout=0.2)
            self._thread.join(timeout=0.6)
        except Exception:
            pass
