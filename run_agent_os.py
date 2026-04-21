#!/usr/bin/env python3
"""
run_agent_os.py — Start the rover agent via AgentOS dashboard.

Usage:
    uv run python run_agent_os.py

Then connect to https://os.agno.com → Add OS → Local → http://<pi-ip>:8000
"""

from __future__ import annotations

import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rambabu")

# ── Hardware init ────────────────────────────────────────────────────────────────
import RPi.GPIO as GPIO  # noqa: E402

from lib.motor import MotorController  # noqa: E402
from lib.ultrasonic import Ultrasonic  # noqa: E402
from lib.pan_tilt import PanTilt  # noqa: E402
from lib.camera import Camera  # noqa: E402
from lib.speaker import Speaker  # noqa: E402
from agno_ai.brain.sonar_guard import SonarGuard  # noqa: E402
import config  # noqa: E402

GPIO.setmode(GPIO.BCM)

motor = MotorController()
ultrasonic = Ultrasonic()
rear_ultrasonic = Ultrasonic(
    trig_pin=config.ULTRASONIC_REAR_TRIG,
    echo_pin=config.ULTRASONIC_REAR_ECHO,
    detection_distance=config.REAR_OBSTACLE_DETECTION_DISTANCE,
)
pan_tilt = PanTilt()
camera = Camera()
result = camera.start()
logger.info(f"Camera: {result}")
speaker = Speaker()
sonar_guard = SonarGuard(ultrasonic=ultrasonic, motor=motor)
sonar_guard.start()
logger.info("SonarGuard started")

motor.set_rear_obstacle_check(
    check_fn=rear_ultrasonic.is_obstacle_confirmed,
    clear_fn=lambda: rear_ultrasonic.get_distance() > config.REAR_OBSTACLE_CLEAR_DISTANCE,
)
logger.info(f"Rear obstacle check wired ({config.REAR_OBSTACLE_DETECTION_DISTANCE}cm)")

from agno_ai.types.context import HardwareContext  # noqa: E402

hw = HardwareContext(
    motor=motor,
    ultrasonic=ultrasonic,
    rear_ultrasonic=rear_ultrasonic,
    pan_tilt=pan_tilt,
    camera=camera,
    speaker=speaker,
    sonar_guard=sonar_guard,
)

from agno_ai import set_hw  # noqa: E402

set_hw(hw)

# ── Agent ─────────────────────────────────────────────────────────────────────
from agno_ai.service import create_agno_service  # noqa: E402

logger.info("Creating agent service...")
app = create_agno_service(hw=hw, enable_agent_os=True)

# ── Run ────────────────────────────────────────────────────────────────────────
import uvicorn  # noqa: E402

logger.info("AgentOS starting on http://0.0.0.0:8000")
logger.info("Connect to https://os.agno.com → Add OS → Local → http://<this-pi>:8000")
uvicorn.run(app, host="0.0.0.0", port=8000)
