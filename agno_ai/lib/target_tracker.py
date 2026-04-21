"""
TargetTracker — session-scoped memory of the last target sighting from visual_survey.

Singleton reset at the start of each goal session. Records when visual_survey
spots the goal target and injects the sighting as context into subsequent
agent messages, preventing the agent from forgetting where the target was seen.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetSighting:
    query: str
    direction: str
    confidence: float
    timestamp: float


class TargetTracker:
    def __init__(self) -> None:
        self._sighting: TargetSighting | None = None
        self._lock = threading.Lock()

    def record(self, query: str, direction: str, confidence: float) -> None:
        with self._lock:
            self._sighting = TargetSighting(
                query=query,
                direction=direction,
                confidence=confidence,
                timestamp=time.monotonic(),
            )

    def has_sighting(self) -> bool:
        with self._lock:
            return self._sighting is not None

    def to_context_str(self) -> str:
        with self._lock:
            s = self._sighting
        if s is None:
            return ""
        age_s = time.monotonic() - s.timestamp
        return (
            f"TARGET SIGHTING (this session):\n"
            f"  Spotted: {s.direction} | confidence: {s.confidence:.2f} | {age_s:.0f}s ago\n"
            f'  Query: "{s.query}"\n'
            f"  \u2192 Orient toward {s.direction} and approach to medium zone (70\u2013150 cm)."
        )

    def reset(self) -> None:
        with self._lock:
            self._sighting = None


_singleton: TargetTracker | None = None
_singleton_lock = threading.Lock()


def get_target_tracker() -> TargetTracker:
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = TargetTracker()
        return _singleton


def reset_target_tracker() -> TargetTracker:
    global _singleton
    with _singleton_lock:
        _singleton = TargetTracker()
        return _singleton
