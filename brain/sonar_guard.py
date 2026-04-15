"""
SonarGuard — autonomous safety watchdog for the forward ultrasonic sensor.

Runs a daemon thread that polls the (already-filtered) HC-SR04 distance every
100ms, classifies it into zones, and fires:

  * an emergency motor.stop() the moment the zone enters CRITICAL,
  * a zone_change_callback whenever the zone transitions between levels.

Zones (cm):
    critical: < 20       close: 20-50       medium: 50-150       clear: > 150

The guard is the *single reader* of the sonar while autonomous mode is active.
The Ultrasonic class itself maintains its own filtering thread; SonarGuard
samples its cached, thread-safe value — no GPIO access happens here.

All exceptions are caught and logged so the guard never crashes the brain.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable

logger = logging.getLogger("brain.sonar_guard")

POLL_INTERVAL_S: float = 0.1

ZONE_CRITICAL: str = "critical"
ZONE_CLOSE: str = "close"
ZONE_MEDIUM: str = "medium"
ZONE_CLEAR: str = "clear"

# Bumped from 50 → 70 to give the rover more brake room. Combined with the
# 80 ms reverse pulse in MovementManager, physical stop now lands ~50 cm
# from the obstacle instead of ~30 cm.
_THRESHOLD_CRITICAL_CM: float = 25.0
_THRESHOLD_CLOSE_CM: float = 70.0
_THRESHOLD_MEDIUM_CM: float = 150.0

# Asymmetric hysteresis. When safety is degrading (zone moves toward
# CRITICAL) we react instantly. When safety is improving (zone moves away
# from CRITICAL) we require this many consecutive confirmations before
# flipping — protects against a single ghost reading saying "all clear" in
# the middle of a sustained close obstacle.
_SAFE_FLIP_CONFIRM_COUNT: int = 3

# How many recent samples SonarGuard tracks for its own MIN computation.
# 8 samples × 100 ms tick = 800 ms of recent history.
_GUARD_WINDOW_SIZE: int = 8

_ZONE_RANK: dict[str, int] = {
    ZONE_CRITICAL: 0,
    ZONE_CLOSE: 1,
    ZONE_MEDIUM: 2,
    ZONE_CLEAR: 3,
}


def classify_zone(distance_cm: float) -> str:
    """Map a distance in cm to a zone label."""
    if distance_cm < _THRESHOLD_CRITICAL_CM:
        return ZONE_CRITICAL
    if distance_cm < _THRESHOLD_CLOSE_CM:
        return ZONE_CLOSE
    if distance_cm < _THRESHOLD_MEDIUM_CM:
        return ZONE_MEDIUM
    return ZONE_CLEAR


class SonarGuard:
    """Background sonar reader + emergency motor cutoff.

    The guard does not block the motor — it observes and reacts. Callers
    drive the motor independently and listen for zone_change_callback to
    decide what to do next.
    """

    def __init__(
        self,
        ultrasonic,
        motor,
        zone_change_callback: Callable[[str, str, float], None] | None = None,
    ) -> None:
        """
        Args:
            ultrasonic: lib.ultrasonic.Ultrasonic — must expose get_distance().
            motor: lib.motor.MotorController — used for emergency stop only.
            zone_change_callback: called as fn(old_zone, new_zone, distance_cm)
                whenever the classified zone transitions. Always invoked from
                the guard's daemon thread.
        """
        self._ultrasonic = ultrasonic
        self._motor = motor
        self._on_zone_change = zone_change_callback

        self._lock = threading.Lock()
        self._distance_cm: float = 999.0  # display: latest median read
        self._safety_distance_cm: float = 999.0  # safety: pessimistic min
        self._zone: str = ZONE_CLEAR  # safety zone (post-hysteresis)
        self._pending_safer_zone: str | None = None
        self._safer_confirm_count: int = 0
        self._window: deque[float] = deque(maxlen=_GUARD_WINDOW_SIZE)
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    # ── lifecycle ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin polling. Idempotent — calling twice has no effect."""
        if self._running.is_set():
            return
        self._running.set()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="sonar-guard",
        )
        self._thread.start()
        logger.info("SonarGuard: started")

    def stop(self) -> None:
        """Signal the loop to exit. Returns once the thread has joined (≤1s)."""
        if not self._running.is_set():
            return
        self._running.clear()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        self._thread = None
        logger.info("SonarGuard: stopped")

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    # ── reads ────────────────────────────────────────────────────────────

    def get_distance(self) -> float:
        """Latest cached distance in cm (median-filtered, for display)."""
        with self._lock:
            return self._distance_cm

    def get_safety_distance(self) -> float:
        """Pessimistic safety distance — minimum of the recent window."""
        with self._lock:
            return self._safety_distance_cm

    def get_zone(self) -> str:
        """Current SAFETY zone (post-hysteresis, conservative)."""
        with self._lock:
            return self._zone

    def snapshot(self) -> tuple[float, str]:
        """Atomic (display_distance_cm, safety_zone) read."""
        with self._lock:
            return self._distance_cm, self._zone

    # ── internal ─────────────────────────────────────────────────────────

    def _loop(self) -> None:
        """Polling loop. Never raises — every iteration is wrapped."""
        while self._running.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.warning(f"SonarGuard: tick failed — {exc}")
            time.sleep(POLL_INTERVAL_S)

    def _tick(self) -> None:
        # Two reads: median (display) and min (safety). If the underlying
        # Ultrasonic class lacks get_min_distance (older API), fall back to
        # using the median for both — degraded mode but still functional.
        median = float(self._ultrasonic.get_distance())
        try:
            ultra_min = float(self._ultrasonic.get_min_distance())
        except AttributeError:
            ultra_min = median

        # Maintain the guard's own rolling window of safety reads. This
        # gives us a wider effective filter (8 ticks × 100 ms = 800 ms)
        # than the Ultrasonic class alone, layered on top.
        self._window.append(ultra_min)
        safety_distance = min(self._window)
        observed_zone = classify_zone(safety_distance)

        with self._lock:
            old_zone = self._zone
            self._distance_cm = median
            self._safety_distance_cm = safety_distance

            new_zone = self._apply_hysteresis(old_zone, observed_zone)
            self._zone = new_zone

        if new_zone == ZONE_CRITICAL and old_zone != ZONE_CRITICAL:
            self._emergency_stop(safety_distance)

        if new_zone != old_zone:
            self._fire_zone_change(old_zone, new_zone, safety_distance)

    def _apply_hysteresis(self, old_zone: str, observed_zone: str) -> str:
        """Asymmetric: degrade instantly, improve only after N confirmations.

        Caller must already hold self._lock.
        """
        old_rank = _ZONE_RANK[old_zone]
        observed_rank = _ZONE_RANK[observed_zone]

        if observed_rank <= old_rank:
            # Same zone or moving toward danger — flip immediately, reset
            # the pending safer-zone counter.
            self._pending_safer_zone = None
            self._safer_confirm_count = 0
            return observed_zone

        # observed_rank > old_rank — we're seeing a SAFER zone than current.
        # Require N consecutive confirmations before believing it.
        if self._pending_safer_zone == observed_zone:
            self._safer_confirm_count += 1
        else:
            self._pending_safer_zone = observed_zone
            self._safer_confirm_count = 1

        if self._safer_confirm_count >= _SAFE_FLIP_CONFIRM_COUNT:
            confirmed = self._pending_safer_zone
            self._pending_safer_zone = None
            self._safer_confirm_count = 0
            return confirmed
        return old_zone

    def _emergency_stop(self, distance: float) -> None:
        try:
            self._motor.stop()
            logger.warning(f"SonarGuard: EMERGENCY STOP — distance={distance:.1f}cm")
        except Exception as exc:
            logger.error(f"SonarGuard: emergency stop failed — {exc}")

    def _fire_zone_change(self, old_zone: str, new_zone: str, distance: float) -> None:
        callback = self._on_zone_change
        if callback is None:
            return
        try:
            callback(old_zone, new_zone, distance)
        except Exception as exc:
            logger.warning(f"SonarGuard: zone callback raised — {exc}")
