"""Send-only status texts to the project owner (FR-12).

- Outbound only: there is no inbound handler anywhere in the backend.
- Messages come from fixed templates. Only validated identifiers and numbers are
  filled in, never source code, model output, error text, secrets or customer data.
- Numbers come from REPLIC8_NOTIFY_NUMBERS (E.164), never from the repo or a request.
- A failed send is logged and swallowed: it never blocks a conversion or repair.
- Each send is given `timeout_s`; the transport must give up after that long.
- At most `max_queue` texts wait at once; extra ones are dropped and logged.
- Repeats of the same event for the same system inside the window are grouped.

The Photon API itself is unverified (PRD section 8), so the transport is pluggable
and defaults to logging only.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from enum import Enum
from typing import Protocol

from .config import E164

log = logging.getLogger("replic8.notify")
IDENT = re.compile(r"^[a-z][a-z0-9_.]{0,96}$")
MAX_LEN = 300


class Event(str, Enum):
    onboarded = "onboarded"
    published = "published"
    failure = "failure"
    heal_started = "heal_started"
    heal_saved = "heal_saved"
    heal_failed = "heal_failed"


TEMPLATES = {
    Event.onboarded: "replic8: {system} onboarded.",
    Event.published: "replic8: {system} v{version} published with {count} operation(s).",
    Event.failure: "replic8: {system} contract tests failing ({count} operation(s)).",
    Event.heal_started: "replic8: self-heal started for {system}.",
    Event.heal_saved: "replic8: {system} repaired and saved as v{version}.",
    Event.heal_failed: "replic8: self-heal failed for {system}; still serving v{version}.",
}


class Transport(Protocol):
    def send(self, number: str, text: str, *, timeout: float) -> None:
        """Send one text. Must give up after `timeout` seconds (e.g. pass it to the HTTP client)."""
        ...


class LogTransport:
    def send(self, number: str, text: str, *, timeout: float) -> None:
        log.info("notify %s***: %s", number[:4], text)


class Notifier:
    def __init__(self, numbers: frozenset[str], transport: Transport | None = None,
                 group_window_s: float = 600.0, timeout_s: float = 10.0, max_queue: int = 50):
        self.numbers = frozenset(n for n in numbers if E164.match(n))
        self.transport = transport or LogTransport()
        self.group_window_s = group_window_s
        self.timeout_s = timeout_s
        self.max_queue = max_queue
        self.dropped = 0
        self._last: dict[tuple[Event, str], float] = {}
        self._suppressed: dict[tuple[Event, str], int] = {}
        self._pending: set[Future] = set()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notify")

    @staticmethod
    def render(event: Event, *, system: str, version: int = 0, count: int = 0) -> str:
        if not IDENT.match(system):
            system = "unknown-system"
        text = TEMPLATES[event].format(system=system, version=int(version), count=int(count))
        return text[:MAX_LEN]

    def notify(self, event: Event, *, system: str, version: int = 0, count: int = 0) -> bool:
        """Queue a text. Returns False if it was grouped with a recent identical event or the
        queue was full. Never raises."""
        try:
            key = (event, system)
            now = time.monotonic()
            with self._lock:
                last = self._last.get(key)
                if last is not None and now - last < self.group_window_s:
                    self._suppressed[key] = self._suppressed.get(key, 0) + 1
                    return False
                self._last[key] = now
                grouped = self._suppressed.pop(key, 0)
            text = self.render(event, system=system, version=version, count=count)
            if grouped:
                text = f"{text} (+{grouped} similar)"[:MAX_LEN]
            queued = [self._submit(number, text) for number in self.numbers]
            return all(queued)
        except Exception:  # noqa: BLE001 - notifications must never break the pipeline
            log.exception("notify failed before sending")
            return False

    def _submit(self, number: str, text: str) -> bool:
        with self._lock:
            if len(self._pending) >= self.max_queue:
                self.dropped += 1
                log.warning("notify queue full (%d waiting); dropped a text", self.max_queue)
                return False
            future = self._pool.submit(self._send_safely, number, text)
            self._pending.add(future)
        future.add_done_callback(self._done)
        return True

    def _done(self, future: Future) -> None:
        with self._lock:
            self._pending.discard(future)

    def _send_safely(self, number: str, text: str) -> None:
        started = time.monotonic()
        try:
            self.transport.send(number, text, timeout=self.timeout_s)
        except Exception as exc:  # noqa: BLE001
            log.warning("notify send failed: %s", type(exc).__name__)
        if time.monotonic() - started > self.timeout_s:
            log.warning("notify send took longer than %.1fs; transport is ignoring its timeout", self.timeout_s)

    def flush(self, timeout: float = 30.0) -> bool:
        """Wait up to `timeout` seconds for queued texts. Returns False if some were still
        unsent; those not yet started are cancelled. Never waits longer than `timeout`."""
        with self._lock:
            pending = set(self._pending)
            pool = self._pool
            self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="notify")
        _, not_done = wait(pending, timeout=timeout)
        pool.shutdown(wait=False, cancel_futures=True)
        return not not_done
