#!/usr/bin/env python3
"""
Telemetry publisher — periodically sends car status to AWS IoT Core.
"""

import time
import threading

import config
from utils.logger import log_info, log_error


class TelemetryPublisher:
    """Publishes car telemetry to MQTT at a configurable interval."""

    def __init__(self, mqtt_client, motor=None, ultrasonic=None, pan_tilt=None):
        self._mqtt = mqtt_client
        self._motor = motor
        self._ultrasonic = ultrasonic
        self._pan_tilt = pan_tilt
        self._running = False
        self._thread = None
        self._interval = 5.0  # seconds between telemetry publishes

    def _build_telemetry(self) -> dict:
        """Build telemetry payload from current hardware state."""
        telemetry = {"timestamp": int(time.time())}

        if self._ultrasonic:
            distance = self._ultrasonic.get_distance()
            telemetry["distance_cm"] = round(distance, 1)
            telemetry["zone"] = self._ultrasonic.get_zone()
            telemetry["obstacle_detected"] = distance <= config.OBSTACLE_DETECTION_DISTANCE

        if self._motor:
            telemetry["motor_direction"] = self._motor._direction
            telemetry["motor_latched"] = self._motor._obstacle_latched

        if self._pan_tilt:
            telemetry["servo_angles"] = self._pan_tilt.get_angles()

        return telemetry

    def _publish_loop(self) -> None:
        """Background loop that publishes telemetry."""
        log_info(f"Telemetry: Publishing every {self._interval}s")
        while self._running:
            try:
                if self._mqtt.is_connected:
                    payload = self._build_telemetry()
                    self._mqtt.publish_telemetry(payload)
            except Exception as e:
                log_error(f"Telemetry: Publish error — {e}")
            time.sleep(self._interval)

    def start(self, interval: float = 5.0) -> dict:
        """Start telemetry publishing in a background thread."""
        if not self._running:
            self._interval = interval
            self._running = True
            self._thread = threading.Thread(target=self._publish_loop, daemon=True)
            self._thread.start()
            log_info("Telemetry: Started")
        return {"status": "ok", "action": "start", "interval": self._interval}

    def stop(self) -> dict:
        """Stop telemetry publishing."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        log_info("Telemetry: Stopped")
        return {"status": "ok", "action": "stop"}

    def cleanup(self) -> None:
        """Clean shutdown."""
        self.stop()
