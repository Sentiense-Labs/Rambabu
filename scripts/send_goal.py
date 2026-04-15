#!/usr/bin/env python3
"""
Publish a CONTROL_GOAL command to the car's MQTT command topic.

Usage:
    uv run python scripts/send_goal.py "Move forward along the dark cable"
    uv run python scripts/send_goal.py --stop
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

PUBLISHER_CLIENT_ID = "claude-cli-publisher"
CONNECT_TIMEOUT_S = 10.0
PUBLISH_TIMEOUT_S = 5.0


def publish_command(payload: dict) -> bool:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=PUBLISHER_CLIENT_ID,
    )
    client.tls_set(
        ca_certs=config.AWS_IOT_ROOT_CA_PATH,
        certfile=config.AWS_IOT_CERT_PATH,
        keyfile=config.AWS_IOT_KEY_PATH,
        tls_version=ssl.PROTOCOL_TLSv1_2,
    )

    published = {"ok": False, "rc": None}

    def on_connect(c, _u, _f, reason_code, _p):
        published["rc"] = reason_code
        if reason_code == 0:
            info = c.publish(
                config.MQTT_COMMANDS_TOPIC,
                json.dumps(payload),
                qos=1,
            )
            info.wait_for_publish(timeout=PUBLISH_TIMEOUT_S)
            published["ok"] = info.is_published()

    client.on_connect = on_connect
    client.connect(config.AWS_IOT_ENDPOINT, 8883, 30)
    client.loop_start()

    deadline = time.time() + CONNECT_TIMEOUT_S
    while time.time() < deadline and not published["ok"]:
        time.sleep(0.1)

    client.loop_stop()
    client.disconnect()

    if published["rc"] != 0:
        print(f"connect failed: rc={published['rc']}", file=sys.stderr)
        return False
    if not published["ok"]:
        print("publish timed out", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a brain goal via MQTT")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("goal", nargs="?", help="Goal text for the brain")
    group.add_argument("--stop", action="store_true", help="Send CONTROL_STOP")
    args = parser.parse_args()

    if args.stop:
        payload: dict = {"action": "CONTROL_STOP"}
    else:
        goal = args.goal.strip()
        if not goal:
            print("empty goal", file=sys.stderr)
            return 2
        payload = {"action": "CONTROL_GOAL", "goal": goal}

    ok = publish_command(payload)
    if ok:
        print(f"published → {config.MQTT_COMMANDS_TOPIC}")
        print(json.dumps(payload, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
