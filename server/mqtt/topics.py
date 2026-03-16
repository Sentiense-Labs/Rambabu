#!/usr/bin/env python3
"""
MQTT topic constants — re-exported from config for convenience.
"""

import config

TELEMETRY = config.MQTT_TELEMETRY_TOPIC
COMMANDS = config.MQTT_COMMANDS_TOPIC
DETECTIONS = config.MQTT_DETECTIONS_TOPIC
ALERTS = config.MQTT_ALERTS_TOPIC
CAMERA_CONTROL = config.MQTT_CAMERA_CONTROL_TOPIC