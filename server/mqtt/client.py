#!/usr/bin/env python3
"""
MQTT client for AWS IoT Core.
Handles connection, publishing, subscribing, and auto-reconnect.
"""

import json
import ssl
import threading
from pathlib import Path
from typing import Callable, Optional

import paho.mqtt.client as mqtt

import config
from utils.logger import log_info, log_error, log_warning


class MqttClient:
    """AWS IoT Core MQTT client using paho-mqtt v2."""

    def __init__(self):
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.AWS_IOT_CLIENT_ID,
        )
        self._connected = False
        self._lock = threading.Lock()
        self._command_callback: Optional[Callable[[str, dict], None]] = None

        self._setup_tls()
        self._setup_callbacks()

    # ── TLS setup ──────────────────────────────────────────────────────────

    def _setup_tls(self) -> None:
        """Configure mutual TLS with AWS IoT Core certificates."""
        cert_path = Path(config.AWS_IOT_CERT_PATH)
        key_path = Path(config.AWS_IOT_KEY_PATH)
        ca_path = Path(config.AWS_IOT_ROOT_CA_PATH)

        for path, label in [
            (cert_path, "Device certificate"),
            (key_path, "Private key"),
            (ca_path, "Root CA"),
        ]:
            if not path.exists():
                raise FileNotFoundError(f"{label} not found: {path}")
            if path.stat().st_size == 0:
                raise ValueError(f"{label} is empty: {path}")

        self._client.tls_set(
            ca_certs=str(ca_path),
            certfile=str(cert_path),
            keyfile=str(key_path),
            tls_version=ssl.PROTOCOL_TLSv1_2,
        )

    # ── Callbacks ──────────────────────────────────────────────────────────

    def _setup_callbacks(self) -> None:
        """Wire paho-mqtt v2 callbacks."""
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log_info("MQTT: Connected to AWS IoT Core")
            with self._lock:
                self._connected = True
            # Subscribe to command topics on every (re)connect
            client.subscribe(config.MQTT_COMMANDS_TOPIC, qos=1)
            log_info(f"MQTT: Subscribed to {config.MQTT_COMMANDS_TOPIC}")
            client.subscribe(config.MQTT_CAMERA_CONTROL_TOPIC, qos=1)
            log_info(f"MQTT: Subscribed to {config.MQTT_CAMERA_CONTROL_TOPIC}")
        else:
            log_error(f"MQTT: Connection failed — reason code {reason_code}")
            with self._lock:
                self._connected = False

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        with self._lock:
            self._connected = False
        if reason_code == 0:
            log_info("MQTT: Disconnected cleanly")
        else:
            log_warning(f"MQTT: Unexpected disconnect — reason code {reason_code}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = msg.payload.decode(errors="replace")

        log_info(f"MQTT: Received [{topic}] {payload}")

        if self._command_callback:
            try:
                self._command_callback(topic, payload)
            except Exception as e:
                log_error(f"MQTT: Command callback error — {e}")

    # ── Public API ─────────────────────────────────────────────────────────

    def set_command_callback(self, callback: Callable[[str, dict], None]) -> None:
        """Register a callback for incoming command messages.
        callback(topic: str, payload: dict) -> None
        """
        self._command_callback = callback

    def connect(self) -> dict:
        """Connect to AWS IoT Core. Starts background network loop."""
        try:
            log_info(
                f"MQTT: Connecting to {config.AWS_IOT_ENDPOINT}:{config.AWS_IOT_PORT} "
                f"as {config.AWS_IOT_CLIENT_ID}"
            )
            self._client.connect(
                host=config.AWS_IOT_ENDPOINT,
                port=config.AWS_IOT_PORT,
                keepalive=config.AWS_IOT_KEEPALIVE,
            )
            self._client.loop_start()
            return {"status": "ok", "action": "connect"}
        except Exception as e:
            log_error(f"MQTT: Connect failed — {e}")
            return {"status": "error", "error_code": "MQTT_CONNECT_FAILED", "message": str(e)}

    def disconnect(self) -> dict:
        """Disconnect from AWS IoT Core and stop network loop."""
        try:
            self._client.loop_stop()
            self._client.disconnect()
            with self._lock:
                self._connected = False
            log_info("MQTT: Disconnected")
            return {"status": "ok", "action": "disconnect"}
        except Exception as e:
            log_error(f"MQTT: Disconnect error — {e}")
            return {"status": "error", "message": str(e)}

    def publish(self, topic: str, payload: dict, qos: int = 1) -> dict:
        """Publish a JSON message to a topic."""
        if not self.is_connected:
            return {"status": "error", "error_code": "MQTT_NOT_CONNECTED", "message": "Not connected"}

        try:
            message = json.dumps(payload)
            result = self._client.publish(topic, message, qos=qos)
            log_info(f"MQTT: Published [{topic}] mid={result.mid}")
            return {"status": "ok", "topic": topic, "mid": result.mid}
        except Exception as e:
            log_error(f"MQTT: Publish failed — {e}")
            return {"status": "error", "error_code": "MQTT_PUBLISH_FAILED", "message": str(e)}

    def publish_telemetry(self, data: dict) -> dict:
        """Publish to the telemetry topic."""
        return self.publish(config.MQTT_TELEMETRY_TOPIC, data)

    def publish_alert(self, data: dict) -> dict:
        """Publish to the alerts topic."""
        return self.publish(config.MQTT_ALERTS_TOPIC, data)

    def publish_detection(self, data: dict) -> dict:
        """Publish to the detections topic."""
        return self.publish(config.MQTT_DETECTIONS_TOPIC, data)

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def cleanup(self) -> None:
        """Clean shutdown."""
        self.disconnect()
