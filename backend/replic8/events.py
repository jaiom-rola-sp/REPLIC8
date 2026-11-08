"""Activity log for the dashboard: onboarding, publishing, failures, repairs, rollbacks.

Events carry only identifiers, versions, counts and fixed reason codes, never
source code, model output, legacy stderr, caller input or secrets. They are kept
in memory for the API and appended to <data_dir>/events.jsonl.
"""

from __future__ import annotations

import json
import re
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SAFE_TEXT = re.compile(r"[^A-Za-z0-9 ._:/()+,=-]")
KINDS = {
    "onboard_started", "onboarded", "onboard_failed", "published", "contract_failed",
    "call_failed", "heal_started", "heal_saved", "heal_failed", "heal_skipped", "rolled_back",
    "change_detected", "schema_adjusted",
}


def _clean(value: Any, limit: int = 200) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    return SAFE_TEXT.sub("", str(value))[:limit]


class EventLog:
    def __init__(self, data_dir: Path | None = None, keep: int = 500):
        self._events: deque[dict[str, Any]] = deque(maxlen=keep)
        self._next = 1
        self._lock = threading.Lock()
        self._path = (data_dir / "events.jsonl") if data_dir else None
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, kind: str, *, system: str = "", tool: str = "", version: int | None = None,
            detail: str = "", **counts: int) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"unknown event kind {kind!r}")
        with self._lock:
            event = {
                "id": self._next,
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": kind,
                "system": _clean(system, 32),
                "tool": _clean(tool, 100),
                "version": version,
                "detail": _clean(detail),
                **{k: int(v) for k, v in counts.items()},
            }
            self._next += 1
            self._events.append(event)
            if self._path:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event) + "\n")
        return event

    def since(self, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._events if e["id"] > after][-limit:]
