#!/usr/bin/env python3
"""
MQTT command handler — routes incoming MQTT commands to hardware actions.
"""

from server.mqtt.actions import Action
from utils.logger import log_info, log_warning


class CommandHandler:
    """Routes MQTT command payloads to hardware methods."""

    def __init__(self, motor=None, pan_tilt=None, speaker=None):
        self._motor = motor
        self._pan_tilt = pan_tilt
        self._speaker = speaker

    def handle(self, topic: str, payload: dict) -> None:
        """Route a command payload to the appropriate hardware action.

        Expected payload format:
            {"action": "MOTOR_FRONT", "speed": 70}
            {"action": "MOTOR_STOP"}
            {"action": "MOTOR_BACK_STEER_LEFT", "speed": 50}
        """
        # IoT platform wraps commands in {"data": {...}}
        data = payload.get("data", payload)
        raw_action = data.get("action", "") or data.get("servoactions", "")
        log_info(f"CommandHandler: {raw_action} — {data}")

        try:
            action = Action(raw_action)
        except ValueError:
            log_warning(f"CommandHandler: Unknown action '{raw_action}'")
            return

        speed = data.get("speed")
        angle = data.get("angle")
        degrees = data.get("degrees", 10)

        match action:
            # Drive
            case Action.MOTOR_FRONT if self._motor:
                self._motor.front(speed) if speed else self._motor.front()
            case Action.MOTOR_BACK if self._motor:
                self._motor.back(speed) if speed else self._motor.back()
            case Action.MOTOR_STOP if self._motor:
                self._motor.stop()

            # Steering (pulse)
            case Action.MOTOR_LEFT if self._motor:
                self._motor.left()
            case Action.MOTOR_RIGHT if self._motor:
                self._motor.right()

            # Steering (hold)
            case Action.MOTOR_STEER_LEFT_HOLD if self._motor:
                self._motor.steer_left_hold()
            case Action.MOTOR_STEER_RIGHT_HOLD if self._motor:
                self._motor.steer_right_hold()
            case Action.MOTOR_STEER_CENTER if self._motor:
                self._motor.steer_center()

            # Compound: reverse + steering hold
            case Action.MOTOR_BACK_STEER_LEFT if self._motor:
                self._motor.steer_left_hold()
                self._motor.back(speed) if speed else self._motor.back()
            case Action.MOTOR_BACK_STEER_RIGHT if self._motor:
                self._motor.steer_right_hold()
                self._motor.back(speed) if speed else self._motor.back()

            # Pan servo (absolute)
            case Action.SERVO_PAN_TO if self._pan_tilt:
                if angle is not None:
                    self._pan_tilt.pan_to(int(angle))

            # Pan servo (relative)
            case Action.SERVO_PAN_LEFT if self._pan_tilt:
                self._pan_tilt.pan_left(int(degrees))
            case Action.SERVO_PAN_RIGHT if self._pan_tilt:
                self._pan_tilt.pan_right(int(degrees))

            # Tilt servo (absolute)
            case Action.SERVO_TILT_TO if self._pan_tilt:
                if angle is not None:
                    self._pan_tilt.tilt_to(int(angle))

            # Tilt servo (relative)
            case Action.SERVO_TILT_UP if self._pan_tilt:
                self._pan_tilt.tilt_up(int(degrees))
            case Action.SERVO_TILT_DOWN if self._pan_tilt:
                self._pan_tilt.tilt_down(int(degrees))

            # Pan-tilt center
            case Action.SERVO_CENTER if self._pan_tilt:
                self._pan_tilt.center()

            case _:
                log_warning(
                    f"CommandHandler: No handler for '{action}' "
                    "(missing hardware dependency?)"
                )
