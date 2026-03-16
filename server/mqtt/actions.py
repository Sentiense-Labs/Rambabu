"""MQTT command action enum — single source of truth for valid command actions."""

from enum import StrEnum


class Action(StrEnum):
    # Drive
    MOTOR_FRONT = "MOTOR_FRONT"
    MOTOR_BACK = "MOTOR_BACK"
    MOTOR_STOP = "MOTOR_STOP"

    # Steering (pulse — auto-resets after 0.5s)
    MOTOR_LEFT = "MOTOR_LEFT"
    MOTOR_RIGHT = "MOTOR_RIGHT"

    # Steering (hold — stays until steer_center)
    MOTOR_STEER_LEFT_HOLD = "MOTOR_STEER_LEFT_HOLD"
    MOTOR_STEER_RIGHT_HOLD = "MOTOR_STEER_RIGHT_HOLD"
    MOTOR_STEER_CENTER = "MOTOR_STEER_CENTER"

    # Compound: reverse + steering hold
    MOTOR_BACK_STEER_LEFT = "MOTOR_BACK_STEER_LEFT"
    MOTOR_BACK_STEER_RIGHT = "MOTOR_BACK_STEER_RIGHT"

    # Pan servo (absolute angle)
    SERVO_PAN_TO = "SERVO_PAN_TO"

    # Pan servo (relative)
    SERVO_PAN_LEFT = "SERVO_PAN_LEFT"
    SERVO_PAN_RIGHT = "SERVO_PAN_RIGHT"

    # Tilt servo (absolute angle)
    SERVO_TILT_TO = "SERVO_TILT_TO"

    # Tilt servo (relative)
    SERVO_TILT_UP = "SERVO_TILT_UP"
    SERVO_TILT_DOWN = "SERVO_TILT_DOWN"

    # Pan-tilt center
    SERVO_CENTER = "SERVO_CENTER"
