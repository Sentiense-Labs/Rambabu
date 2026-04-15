#!/usr/bin/env python3
"""
Ultrasonic class for AI RC Car
Measures distance using HC-SR04 sensor.

Filtering strategy — median of rolling window + streak on median:
  - Median of 5 rejects up to 2 noise spikes (needs 3/5 agreement)
  - Streak tracks consecutive median readings below threshold (not raw)
  - Emergency fast-path at <10cm for imminent collision
  - Single noise spike cannot false-stop the car
  - Real obstacles confirmed within ~150ms
"""

import RPi.GPIO as GPIO
import time
import threading
from collections import deque
import config
from utils.logger import log_warning, log_debug

# Rolling window size for median filter.
# 9 readings at 20Hz = 450ms window. Median needs 5/9 to agree — wider
# than the original 5/250ms because indoor multipath echoes were producing
# sustained 3-sample ghost streaks that won the median.
_WINDOW_SIZE: int = 9

# Consecutive median readings below threshold to confirm obstacle.
_CONFIRM_COUNT: int = 2

# Emergency: below this distance, a single plausible reading triggers stop.
_EMERGENCY_DISTANCE: float = 10.0

# Max plausible distance drop per sample (cm). At 2 m/s, 50ms = 10cm.
# 25cm allows margin for sensor jitter on real approaches.
_MAX_DELTA_PER_SAMPLE: float = 25.0


class Ultrasonic:
    """Ultrasonic distance sensor with median-filtered background measurement."""

    def __init__(
        self,
        trig_pin: int = config.ULTRASONIC_TRIG,
        echo_pin: int = config.ULTRASONIC_ECHO,
        detection_distance: int = config.OBSTACLE_DETECTION_DISTANCE,
    ):
        """Initialize ultrasonic sensor with background thread.

        Args:
            trig_pin: GPIO BCM pin for the trigger signal (default: front sensor pin).
            echo_pin: GPIO BCM pin for the echo return (default: front sensor pin).
            detection_distance: Distance threshold (cm) for obstacle confirmation.
                Use REAR_OBSTACLE_DETECTION_DISTANCE for the rear sensor.
        """
        GPIO.setwarnings(False)

        self.trig_pin = trig_pin
        self.echo_pin = echo_pin
        self._detection_distance = detection_distance

        GPIO.setup(self.trig_pin, GPIO.OUT)
        GPIO.setup(self.echo_pin, GPIO.IN)

        self.last_distance = 999.0
        self._window: deque[float] = deque(maxlen=_WINDOW_SIZE)
        self._close_streak: int = 0
        self._emergency: bool = False
        self.lock = threading.Lock()
        self.running = False
        self.thread = None

        self.start()

    def _measure_distance(self) -> float:
        """Single distance measurement with timeout handling."""
        GPIO.output(self.trig_pin, True)
        time.sleep(0.00001)
        GPIO.output(self.trig_pin, False)

        timeout = time.time() + 0.1

        pulse_start = time.time()
        while GPIO.input(self.echo_pin) == 0:
            pulse_start = time.time()
            if pulse_start > timeout:
                return self.last_distance

        pulse_end = time.time()
        while GPIO.input(self.echo_pin) == 1:
            pulse_end = time.time()
            if pulse_end > timeout:
                return self.last_distance

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        distance = round(distance, 2)

        if 2 <= distance <= 400:
            return distance

        return self.last_distance

    def _median(self) -> float:
        """Return median of the rolling window."""
        if not self._window:
            return 999.0
        sorted_values = sorted(self._window)
        mid = len(sorted_values) // 2
        if len(sorted_values) % 2 == 0:
            return (sorted_values[mid - 1] + sorted_values[mid]) / 2
        return sorted_values[mid]

    def _is_plausible_close(self, raw: float, current_median: float) -> bool:
        """True if a close reading is physically plausible given recent median.

        If we're already near an obstacle, any close reading is plausible.
        From far away, a sudden drop bigger than _MAX_DELTA_PER_SAMPLE is noise.
        """
        if current_median <= self._detection_distance * 1.5:
            return True
        delta = current_median - raw
        return delta <= _MAX_DELTA_PER_SAMPLE

    def _measurement_loop(self):
        """Background thread: measure at 20Hz, update median-filtered distance."""
        while self.running:
            try:
                raw = self._measure_distance()

                with self.lock:
                    old_median = self._median()

                    self._window.append(raw)
                    median_distance = self._median()
                    self.last_distance = median_distance

                    # Streak on MEDIAN — noise can't build a streak
                    if median_distance <= self._detection_distance:
                        self._close_streak += 1
                    else:
                        self._close_streak = 0

                    # Emergency: imminent collision, single plausible reading
                    self._emergency = (
                        raw <= _EMERGENCY_DISTANCE
                        and self._is_plausible_close(raw, old_median)
                    )

                    log_debug(
                        f"Ultrasonic: raw={raw:.1f} median={median_distance:.1f} "
                        f"streak={self._close_streak} emergency={self._emergency}"
                    )

                time.sleep(config.ULTRASONIC_POLL_INTERVAL)
            except Exception as e:
                log_warning(f"Ultrasonic measurement error (SENSOR_TIMEOUT): {e}")
                time.sleep(0.1)

    def start(self) -> dict:
        """Start background measurement thread."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._measurement_loop, daemon=True)
            self.thread.start()
        return {"status": "ok", "action": "start"}

    def stop(self) -> dict:
        """Stop background measurement thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        return {"status": "ok", "action": "stop"}

    def wait_for_reading(self, timeout: float = 2.0) -> bool:
        """Wait for a valid sensor reading (not the initial 999.0)."""
        start = time.time()
        while time.time() - start < timeout:
            with self.lock:
                if self.last_distance < 999.0:
                    return True
            time.sleep(0.05)
        return False

    def get_distance(self) -> float:
        """Returns median-filtered distance in cm (thread-safe)."""
        with self.lock:
            return self.last_distance

    def get_min_distance(self) -> float:
        """Pessimistic safety read — minimum of the rolling window.

        Multipath echoes off far walls can dominate the median and hide a
        closer obstacle. The minimum catches the closest reading in the
        window, which is what we want for safety decisions.

        Returns 999.0 if the window is empty.
        """
        with self.lock:
            if not self._window:
                return 999.0
            return min(self._window)

    def is_obstacle_confirmed(self) -> bool:
        """True when filtered evidence confirms a real obstacle.

        Two paths:
        1. Normal: 2+ consecutive median readings <= OBSTACLE_DETECTION_DISTANCE
        2. Emergency: single raw <= 10cm AND plausible given recent median
        """
        with self.lock:
            return self._emergency or self._close_streak >= _CONFIRM_COUNT

    def is_clear(self, threshold: int = config.SAFE_DISTANCE) -> bool:
        """Returns True if path is clear (distance > threshold)."""
        return self.get_distance() > threshold

    def is_blocked(self, threshold: int = config.STOP_DISTANCE) -> bool:
        """Returns True if obstacle detected (distance < threshold)."""
        return self.get_distance() < threshold

    def get_zone(self) -> str:
        """Returns distance zone: 'safe', 'warning', 'danger'."""
        distance = self.get_distance()

        if distance > config.SAFE_DISTANCE:
            return "safe"
        elif distance > config.STOP_DISTANCE:
            return "warning"
        else:
            return "danger"

    def cleanup(self) -> None:
        """Clean shutdown."""
        self.stop()
