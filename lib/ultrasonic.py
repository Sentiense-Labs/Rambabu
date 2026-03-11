#!/usr/bin/env python3
"""
Ultrasonic class for AI RC Car
Measures distance using HC-SR04 sensor
"""

import RPi.GPIO as GPIO
import time
import threading
import config


class Ultrasonic:
    """Ultrasonic distance sensor with background measurement"""

    def __init__(self):
        """Initialize ultrasonic sensor with background thread"""
        # GPIO.setmode() is handled by main.py before creating this object
        # Do NOT call it here to avoid "unknown handle" errors
        GPIO.setwarnings(False)

        # Get GPIO pins from config
        self.trig_pin = config.ULTRASONIC_TRIG
        self.echo_pin = config.ULTRASONIC_ECHO

        GPIO.setup(self.trig_pin, GPIO.OUT)
        GPIO.setup(self.echo_pin, GPIO.IN)

        # Initial distance (safe default - far away)
        self.last_distance = 999.0
        self.lock = threading.Lock()
        self.running = False
        self.thread = None

        # Start background measurement thread
        self.start()

    def _measure_distance(self) -> float:
        """Single distance measurement with timeout handling"""
        # Send 10us pulse
        GPIO.output(self.trig_pin, True)
        time.sleep(0.00001)
        GPIO.output(self.trig_pin, False)

        # Wait for echo with timeout
        timeout = time.time() + 0.1  # 100ms timeout

        # Wait for echo start
        pulse_start = time.time()
        while GPIO.input(self.echo_pin) == 0:
            pulse_start = time.time()
            if pulse_start > timeout:
                return self.last_distance  # Return last known distance

        # Wait for echo end
        pulse_end = time.time()
        while GPIO.input(self.echo_pin) == 1:
            pulse_end = time.time()
            if pulse_end > timeout:
                return self.last_distance

        # Calculate distance
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150  # Speed of sound = 34300 cm/s
        distance = round(distance, 2)

        # Sanity check (2cm - 400cm valid range)
        if 2 <= distance <= 400:
            return distance

        return self.last_distance

    def _measurement_loop(self):
        """Background thread for continuous measurement at 20Hz"""
        while self.running:
            try:
                distance = self._measure_distance()

                # Thread-safe update of last distance
                with self.lock:
                    self.last_distance = distance

                time.sleep(0.05)  # 20Hz = 50ms interval
            except Exception as e:
                # Silently log errors to prevent spam
                pass

    def start(self):
        """Start background measurement thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._measurement_loop, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop background measurement thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def wait_for_reading(self, timeout: float = 2.0) -> bool:
        """Wait for a valid sensor reading (not the initial 999.0)"""
        start = time.time()
        while time.time() - start < timeout:
            with self.lock:
                if self.last_distance < 999.0:  # We have a valid reading
                    return True
            time.sleep(0.05)
        return False

    def get_distance(self) -> float:
        """Returns last measured distance in cm (thread-safe)"""
        with self.lock:
            return self.last_distance

    def is_clear(self, threshold: int = 30) -> bool:
        """Returns True if path is clear (distance > threshold)"""
        return self.get_distance() > threshold

    def is_blocked(self, threshold: int = 20) -> bool:
        """Returns True if obstacle detected (distance < threshold)"""
        return self.get_distance() < threshold

    def get_zone(self) -> str:
        """Returns distance zone: 'safe', 'warning', 'danger'"""
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
        GPIO.cleanup()
