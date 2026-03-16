#!/usr/bin/env python3
"""Connect to AWS IoT Core MQTT and listen for commands."""

import signal
import sys
import time

from server.mqtt.client import MqttClient
from server.mqtt.command_handler import CommandHandler
from utils.logger import log_info


def main():
    mqtt_client = MqttClient()
    handler = CommandHandler()

    mqtt_client.set_command_callback(handler.handle)

    result = mqtt_client.connect()
    log_info(f"Connect result: {result}")

    if result["status"] != "ok":
        sys.exit(1)

    # Wait for connection to establish
    time.sleep(2)
    log_info(f"Connected: {mqtt_client.is_connected}")

    # Block until Ctrl+C
    def shutdown(sig, frame):
        log_info("Shutting down...")
        mqtt_client.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    log_info("Listening for commands. Press Ctrl+C to stop.")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
