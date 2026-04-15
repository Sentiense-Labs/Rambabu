#!/usr/bin/env python3
"""
run_agent_os.py — Start the rover agent via AgentOS dashboard.

Usage:
    uv run python run_agent_os.py

Then connect to https://os.agno.com → Add OS → Local → http://<pi-ip>:8000
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rambabu")

# ── Hardware init ────────────────────────────────────────────────────────────────
import RPi.GPIO as GPIO

from lib.motor import MotorController
from lib.ultrasonic import Ultrasonic
from lib.pan_tilt import PanTilt
from lib.camera import Camera
from lib.speaker import Speaker
from brain.sonar_guard import SonarGuard
from brain.movement_manager import MovementManager

GPIO.setmode(GPIO.BCM)

motor = MotorController()
ultrasonic = Ultrasonic()
pan_tilt = PanTilt()
camera = Camera()
speaker = Speaker()
sonar_guard = SonarGuard(ultrasonic=ultrasonic, motor=motor)
movement_manager = MovementManager(motor=motor, sonar_guard=sonar_guard)

from agno_ai.types.context import HardwareContext

hw = HardwareContext(
    motor=motor,
    ultrasonic=ultrasonic,
    pan_tilt=pan_tilt,
    camera=camera,
    speaker=speaker,
    sonar_guard=sonar_guard,
    movement_manager=movement_manager,
)

# ── Agent ─────────────────────────────────────────────────────────────────────
from agno_ai.service import create_agno_service

logger.info("Creating agent service...")
app = create_agno_service(hw=hw, enable_agent_os=True)

# ── Run ────────────────────────────────────────────────────────────────────────
import uvicorn

logger.info("AgentOS starting on http://0.0.0.0:8000")
logger.info("Connect to https://os.agno.com → Add OS → Local → http://<this-pi>:8000")
uvicorn.run(app, host="0.0.0.0", port=8000)
