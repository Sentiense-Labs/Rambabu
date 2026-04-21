"""
MovementManager — continuous motor execution with SonarGuard integration.

The brain issues high-level intents — go("forward") / stop() — and the
manager keeps the motor running until either:

  * the brain calls stop(),
  * SonarGuard fires an emergency_stop (CRITICAL zone),
  * SonarGuard reports a zone transition into 'close' (auto-stop + report).

Other zone changes (clear→medium, medium→clear, etc.) are forwarded to the
brain via on_zone_change so it can decide whether to slow down, replan, or
keep going. The manager itself never restarts the motor — only the brain
does, by calling go() again after handling an event.

Distance estimation:
    Empirical: ~56 cm/sec at speed=80. Linearly scaled for other speeds.
    This is an estimate, not a measurement — used for goal-progress hints.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from agno_ai.brain.sonar_guard import (
    SonarGuard,
    ZONE_CLOSE,
    ZONE_CRITICAL,
)

logger = logging.getLogger("brain.movement_manager")

DEFAULT_SPEED: int = 60
_BASE_SPEED_CM_PER_S: float = 56.0
_BASE_SPEED_DUTY: float = 80.0

# Active braking — brief reverse pulse to dump momentum on auto-stops.
# Without this, motor.stop() just kills PWM and the rover coasts ~30cm at
# speed=80, easily overshooting the close-zone safety margin.
_BRAKE_DUTY: int = 70
_BRAKE_DURATION_S: float = 0.08

# Zone events fired while the motor has been idle for longer than this are
# treated as sonar noise (sensor jitter at zone boundaries) and suppressed.
_IDLE_EVENT_SUPPRESSION_S: float = 2.0

# Pre-flight burst sample count + spacing. Before engaging forward-family
# motion we read sonar BURST_COUNT times over ~BURST_SPACING_S * COUNT
# seconds and abort if ANY reading shows close/critical. Catches multipath
# ghosts that briefly report 'clear' between real close-distance reads.
_PREFLIGHT_BURST_COUNT: int = 5
_PREFLIGHT_BURST_SPACING_S: float = 0.05  # 5 × 50ms = 250ms total

VALID_DIRECTIONS: frozenset[str] = frozenset({"forward", "back", "left", "right"})
FORWARD_FAMILY: frozenset[str] = frozenset({"forward", "left", "right"})


class MovementManager:
    """Owns the motor during autonomous movement and bridges to SonarGuard."""

    def __init__(
        self,
        motor,
        sonar_guard: SonarGuard,
        on_zone_change: Callable[[str, str, float], None] | None = None,
        on_emergency_stop: Callable[[float], None] | None = None,
    ) -> None:
        """
        Args:
            motor: lib.motor.MotorController.
            sonar_guard: a SonarGuard instance. The manager registers itself
                as the guard's zone_change_callback by replacing whatever was
                set previously, then forwards events to the brain callbacks.
            on_zone_change: brain callback fn(old_zone, new_zone, distance_cm).
                Called from the guard's daemon thread.
            on_emergency_stop: brain callback fn(distance_cm). Called from
                the guard's daemon thread immediately after the motor has
                been stopped.
        """
        self._motor = motor
        self._guard = sonar_guard
        self._on_zone_change = on_zone_change
        self._on_emergency_stop = on_emergency_stop

        self._lock = threading.Lock()
        self._direction: str | None = None
        self._speed: int = 0
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        self._was_emergency_stopped: bool = False
        # Set when SonarGuard auto-stops us (close OR critical zone). Cleared
        # by the next user-initiated go() or stop(). The brain reads this to
        # tell "model said goal_complete" apart from "motor was halted by
        # safety while model was thinking."
        self._was_safety_stopped: bool = False
        self._safety_stop_reason: str | None = None
        self._safety_stop_distance_cm: float | None = None

        # Hook into the guard. We override any previous callback because the
        # manager is the canonical owner of motion-related events.
        self._guard._on_zone_change = self._handle_zone_change  # noqa: SLF001

    # ── public API ───────────────────────────────────────────────────────

    def go(self, direction: str, speed: int = DEFAULT_SPEED) -> dict:
        """Begin (or replace) continuous motion. Returns immediately.

        The motor runs in the background until stop() is called or SonarGuard
        intervenes. Calling go() while already moving stops first, then starts
        the new direction — useful for changing course after an obstacle.
        """
        if direction not in VALID_DIRECTIONS:
            return {"status": "error", "message": f"invalid direction: {direction!r}"}

        if not self._guard.is_running:
            self._guard.start()

        # Pre-flight: refuse forward-family moves when the path is already
        # blocked. Two layers:
        #   (1) check the guard's current safety zone (post-hysteresis)
        #   (2) burst-sample the sonar fresh — if ANY of N reads shows
        #       close/critical, refuse. Catches multipath ghosts that
        #       briefly report 'clear' between real close-distance reads.
        if direction in FORWARD_FAMILY:
            blocked = self._preflight_check()
            if blocked is not None:
                logger.info(
                    f"MovementManager: refused {direction} — "
                    f"{blocked['zone']} @ {blocked['distance_cm']}cm "
                    f"({blocked['source']})"
                )
                return {
                    "status": "blocked",
                    "reason": "obstacle_in_path",
                    "direction": direction,
                    "zone": blocked["zone"],
                    "distance_cm": blocked["distance_cm"],
                    "source": blocked["source"],
                    "message": (
                        f"Path is {blocked['zone']} "
                        f"({blocked['distance_cm']}cm, "
                        f"detected via {blocked['source']}). Cannot move "
                        f"{direction}. You must call move(back, 0.5) to "
                        "disengage, then look_around to find an open lane."
                    ),
                }

        speed = max(0, min(int(speed), 100))

        # Always stop first to clear PWM state cleanly between transitions.
        self._motor.stop()

        try:
            result = self._engage(direction, speed)
        except Exception as exc:
            self._motor.stop()
            self._reset_state()
            return {"status": "error", "message": f"motor failed: {exc}"}

        if result.get("status") != "ok":
            self._reset_state()
            return result

        with self._lock:
            self._direction = direction
            self._speed = speed
            self._started_at = time.time()
            self._was_emergency_stopped = False
            self._was_safety_stopped = False
            self._safety_stop_reason = None
            self._safety_stop_distance_cm = None

        logger.info(f"MovementManager: go {direction} @ speed={speed}")
        return {
            "status": "ok",
            "direction": direction,
            "speed": speed,
        }

    def go_timed(
        self, direction: str, seconds: float, speed: int = DEFAULT_SPEED
    ) -> dict:
        """Begin movement and auto-stop after seconds. Non-blocking.

        Starts movement via go(), then spawns a daemon thread to call stop()
        after the duration. Returns immediately so the session loop stays
        responsive to events.
        """
        result = self.go(direction, speed)
        if result.get("status") != "ok":
            return result

        def _stop_after():
            time.sleep(seconds)
            if self._direction == direction:
                self.stop()

        t = threading.Thread(target=_stop_after, daemon=True)
        t.start()
        return {
            "status": "ok",
            "direction": direction,
            "speed": speed,
            "duration_s": seconds,
            "note": "Background timer started — stop() will be called after duration.",
        }

    def stop(self) -> dict:
        """Halt all motion immediately. Always safe.

        User-initiated stop — clears the safety-stop flag so the brain
        treats the rover as 'idle by intention', not 'halted by sonar'.
        """
        try:
            self._motor.stop()
            try:
                self._motor.steer_center()
            except Exception:
                logger.warning("MovementManager: steer_center() failed")
        finally:
            self._reset_state()
            with self._lock:
                self._was_safety_stopped = False
                self._safety_stop_reason = None
                self._safety_stop_distance_cm = None
        logger.info("MovementManager: stop")
        return {"status": "ok", "direction": "stopped"}

    # ── observable state ────────────────────────────────────────────────

    @property
    def is_moving(self) -> bool:
        with self._lock:
            return self._direction is not None

    @property
    def current_direction(self) -> str | None:
        with self._lock:
            return self._direction

    @property
    def elapsed_seconds(self) -> float:
        with self._lock:
            if self._started_at is None:
                return 0.0
            return time.time() - self._started_at

    @property
    def was_safety_stopped(self) -> bool:
        """True when the last halt was triggered by SonarGuard, not by the user."""
        with self._lock:
            return self._was_safety_stopped

    @property
    def safety_stop_info(self) -> dict | None:
        """Snapshot of the last safety stop — (reason, distance_cm) or None."""
        with self._lock:
            if not self._was_safety_stopped:
                return None
            return {
                "reason": self._safety_stop_reason,
                "distance_cm": self._safety_stop_distance_cm,
            }

    @property
    def estimated_distance_cm(self) -> float:
        """Naive integration: speed-scaled time-on-motor estimate."""
        with self._lock:
            if self._started_at is None or self._speed <= 0:
                return 0.0
            elapsed = time.time() - self._started_at
            scale = self._speed / _BASE_SPEED_DUTY
            return elapsed * _BASE_SPEED_CM_PER_S * scale

    def snapshot(self) -> dict:
        """Atomic state read — useful for emitting to the brain."""
        with self._lock:
            elapsed = (
                time.time() - self._started_at if self._started_at is not None else 0.0
            )
            scale = (self._speed / _BASE_SPEED_DUTY) if self._speed else 0.0
            return {
                "is_moving": self._direction is not None,
                "direction": self._direction,
                "speed": self._speed,
                "elapsed_s": round(elapsed, 2),
                "estimated_distance_cm": round(
                    elapsed * _BASE_SPEED_CM_PER_S * scale, 1
                ),
            }

    # ── internal ─────────────────────────────────────────────────────────

    def _preflight_check(self) -> dict | None:
        """Two-layer pre-flight: cached safety zone + fresh sonar burst.

        Returns a dict describing the blockage if the path is unsafe,
        otherwise None. Uses the *minimum* of fresh samples — pessimistic
        about safety so a transient ghost reading can't sneak the rover
        through.
        """
        # Layer 1: cached safety zone (already pessimistic via SonarGuard
        # hysteresis + min-of-window).
        zone = self._guard.get_zone()
        if zone in (ZONE_CLOSE, ZONE_CRITICAL):
            distance = self._guard.get_safety_distance()
            return {
                "zone": zone,
                "distance_cm": round(distance, 1),
                "source": "cached_safety_zone",
            }

        # Layer 2: fresh burst sample. If ANY reading shows close/critical
        # (post-min computation), refuse. Catches multipath ghosts that
        # alternate between real-close and ghost-far values.
        try:
            samples: list[float] = []
            for _ in range(_PREFLIGHT_BURST_COUNT):
                try:
                    samples.append(
                        float(self._guard._ultrasonic.get_min_distance())
                    )  # noqa: SLF001
                except AttributeError:
                    samples.append(
                        float(self._guard._ultrasonic.get_distance())
                    )  # noqa: SLF001
                time.sleep(_PREFLIGHT_BURST_SPACING_S)
            burst_min = min(samples) if samples else 999.0
            burst_zone = (
                ZONE_CRITICAL
                if burst_min < 25.0
                else ZONE_CLOSE if burst_min < 70.0 else None
            )
            if burst_zone is not None:
                return {
                    "zone": burst_zone,
                    "distance_cm": round(burst_min, 1),
                    "source": f"preflight_burst_min_of_{len(samples)}",
                }
        except Exception as exc:
            logger.warning(f"MovementManager: preflight burst failed — {exc}")

        return None

    def _engage(self, direction: str, speed: int) -> dict:
        """Issue the actual motor commands for a direction."""
        if direction == "forward":
            return self._motor.front(speed)
        if direction == "back":
            return self._motor.back(speed)
        if direction == "left":
            steer = self._motor.steer_left_hold()
            if steer.get("status") != "ok":
                return steer
            return self._motor.front(speed)
        if direction == "right":
            steer = self._motor.steer_right_hold()
            if steer.get("status") != "ok":
                return steer
            return self._motor.front(speed)
        return {"status": "error", "message": f"unknown direction: {direction}"}

    def _reset_state(self) -> None:
        with self._lock:
            if self._direction is not None:
                self._stopped_at = time.time()
            self._direction = None
            self._speed = 0
            self._started_at = None

    def _brake_and_stop(self) -> None:
        """Active brake: brief reverse pulse to dump momentum, then stop.

        Without this, motor.stop() just zeroes PWM and the rover coasts.
        At speed=80 that's ~30cm of overshoot — enough to turn a close-zone
        auto-stop into a critical-zone collision.

        Skips the reverse pulse if the rear obstacle sensor confirms blockage —
        braking into a confirmed rear obstacle is worse than coasting forward.
        """
        rear_check = getattr(self._motor, "_rear_obstacle_check", None)
        rear_blocked = rear_check is not None and rear_check()

        if not rear_blocked:
            try:
                self._motor.back(_BRAKE_DUTY)
                time.sleep(_BRAKE_DURATION_S)
            except Exception as exc:
                logger.warning(f"MovementManager: brake pulse failed — {exc}")
        try:
            self._motor.stop()
        except Exception as exc:
            logger.error(f"MovementManager: post-brake stop failed — {exc}")

    def _handle_zone_change(
        self, old_zone: str, new_zone: str, distance: float
    ) -> None:
        """SonarGuard callback. Called from the guard's daemon thread.

        Suppresses callbacks to the brain when the motor has been idle for
        longer than _IDLE_EVENT_SUPPRESSION_S — sonar jitter at zone
        boundaries (e.g. distance flickering across 50cm) was producing
        spurious OBSTACLE/ZONE_CHANGE events that filled the brain's queue
        with noise.
        """
        logger.info(
            f"MovementManager: zone {old_zone}→{new_zone} "
            f"@ {distance:.1f}cm (moving={self.is_moving})"
        )

        forward_motion = self.current_direction in FORWARD_FAMILY

        # Suppress noise — only forward callbacks while motion is active or
        # was active very recently (so post-stop critical events still flow).
        with self._lock:
            stopped_at = self._stopped_at
        idle_seconds = (
            time.time() - stopped_at
            if stopped_at is not None and not forward_motion
            else 0.0
        )
        suppress = (
            not forward_motion
            and stopped_at is not None
            and idle_seconds > _IDLE_EVENT_SUPPRESSION_S
            and new_zone != ZONE_CRITICAL
        )

        # Critical: SonarGuard already stopped the motor. Add an active brake
        # pulse to dump residual momentum, then notify brain.
        if new_zone == ZONE_CRITICAL:
            if forward_motion:
                self._brake_and_stop()
                self._reset_state()
                with self._lock:
                    self._was_emergency_stopped = True
                    self._was_safety_stopped = True
                    self._safety_stop_reason = "EMERGENCY_STOP"
                    self._safety_stop_distance_cm = distance
            self._safe_call(self._on_emergency_stop, distance)
            return

        # Close while moving forward: slow down and continue cautiously.
        # Do NOT stop — let the LLM decide next action through normal reasoning.
        # This avoids unnecessary wake-ups and excessive API calls.
        if new_zone == ZONE_CLOSE and forward_motion:
            self._motor.set_speed(30)
            with self._lock:
                self._speed = 30
            logger.info(f"MovementManager: slowed to 30% — {distance:.1f}cm")

        if suppress:
            return

        self._safe_call(self._on_zone_change, old_zone, new_zone, distance)

    @staticmethod
    def _safe_call(fn: Callable | None, *args) -> None:
        if fn is None:
            return
        try:
            fn(*args)
        except Exception as exc:
            logger.warning(f"MovementManager: callback raised — {exc}")
