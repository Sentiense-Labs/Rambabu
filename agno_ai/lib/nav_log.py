"""
NavLog — lightweight in-session navigation history.

Records every move_cm outcome (direction, requested vs actual distance,
status, obstacle). Bounded to MAX_ENTRIES via a deque. Reset at the start
of each new goal session.

to_context_str() → compact human-readable block injected into each agent turn
to_transcript_str() → fuller record appended to ObservationalMemory on complete
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

MAX_ENTRIES = 8

Outcome = Literal["done", "blocked", "sonar_stop", "capped", "error"]

_OUTCOME_SYMBOL: dict[str, str] = {
    "done":       "✓",
    "sonar_stop": "⚠",
    "blocked":    "✗",
    "capped":     "↓",
    "error":      "?",
}


@dataclass(frozen=True)
class NavEntry:
    index: int
    direction: str
    requested_cm: float
    actual_cm: float
    outcome: Outcome
    obstacle: str | None
    elapsed_s: float


class NavLog:
    def __init__(self) -> None:
        self._entries: deque[NavEntry] = deque(maxlen=MAX_ENTRIES)
        self._lock = threading.Lock()
        self._counter = 0

    def record(
        self,
        direction: str,
        requested_cm: float,
        actual_cm: float,
        outcome: Outcome,
        obstacle: str | None = None,
        elapsed_s: float = 0.0,
    ) -> None:
        with self._lock:
            self._counter += 1
            self._entries.append(NavEntry(
                index=self._counter,
                direction=direction,
                requested_cm=requested_cm,
                actual_cm=actual_cm,
                outcome=outcome,
                obstacle=obstacle,
                elapsed_s=elapsed_s,
            ))

    def to_context_str(self) -> str:
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return ""
        lines = ["NAV LOG (this session, oldest→newest):"]
        for e in entries:
            sym = _OUTCOME_SYMBOL.get(e.outcome, "?")
            if e.outcome == "done":
                body = f"{e.direction:<11} {e.actual_cm:.0f} cm  {sym}"
            elif e.outcome == "sonar_stop":
                body = f"{e.direction:<11} {e.actual_cm:.0f}/{e.requested_cm:.0f} cm  {sym} sonar stopped early"
            elif e.outcome == "capped":
                body = f"{e.direction:<11} {e.actual_cm:.0f}/{e.requested_cm:.0f} cm  {sym} capped by obstacle buffer"
            else:
                obs = f" [{e.obstacle}]" if e.obstacle else ""
                body = f"{e.direction:<11} 0/{e.requested_cm:.0f} cm  {sym} blocked{obs}"
            lines.append(f"  #{e.index:02d}  {body}")
        return "\n".join(lines)

    def to_transcript_str(self) -> str:
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return ""
        parts = [f"Session moves ({len(entries)} recorded, max {MAX_ENTRIES}):"]
        for e in entries:
            obs = f", obstacle={e.obstacle}" if e.obstacle else ""
            parts.append(
                f"  {e.direction} {e.requested_cm:.0f}cm → {e.outcome} "
                f"(actual {e.actual_cm:.0f}cm, {e.elapsed_s:.1f}s{obs})"
            )
        return "\n".join(parts)

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()
            self._counter = 0


# ── Module-level singleton ─────────────────────────────────────────────────────

_singleton: NavLog | None = None
_singleton_lock = threading.Lock()


def get_nav_log() -> NavLog:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = NavLog()
        return _singleton


def reset_nav_log() -> NavLog:
    """Create a fresh NavLog for a new session. Returns the new instance."""
    global _singleton
    with _singleton_lock:
        _singleton = NavLog()
        return _singleton
