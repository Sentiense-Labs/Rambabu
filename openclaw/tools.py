#!/usr/bin/env python3
"""
OpenClaw function-calling tools for Ramu's RC car hardware.

Each tool is a dict conforming to the OpenAI/Anthropic function-calling schema.
Hardware execution is handled by `execute()` which routes tool calls to
the appropriate lib/ methods.

Usage:
    from openclaw.tools import TOOLS, execute

    # Pass TOOLS list to your LLM's tool_choice / tools parameter
    # When the LLM returns a tool_call, run:
    result = execute(tool_name, tool_args, motor=motor, pan_tilt=pan_tilt, ultrasonic=ultrasonic)
"""

from typing import Any


# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    # ── Motor: drive ──────────────────────────────────────────────────────
    {
        "name": "motor_forward",
        "description": "Drive the car forward. Stops automatically if an obstacle is detected.",
        "input_schema": {
            "type": "object",
            "properties": {
                "speed": {
                    "type": "integer",
                    "description": "Speed 0-100 (default 70).",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "motor_backward",
        "description": "Drive the car backward. Clears any obstacle latch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "speed": {
                    "type": "integer",
                    "description": "Speed 0-100 (default 70).",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "motor_stop",
        "description": "Stop all motors immediately.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ── Motor: steering ───────────────────────────────────────────────────
    {
        "name": "steer_left",
        "description": "Pulse steering left for 0.5s then auto-center.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "steer_right",
        "description": "Pulse steering right for 0.5s then auto-center.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "steer_left_hold",
        "description": "Hold steering left until steer_center is called.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "steer_right_hold",
        "description": "Hold steering right until steer_center is called.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "steer_center",
        "description": "Return steering to center position.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ── Motor: compound (reverse + steer) ─────────────────────────────────
    {
        "name": "reverse_steer_left",
        "description": "Drive backward while steering left.",
        "input_schema": {
            "type": "object",
            "properties": {
                "speed": {
                    "type": "integer",
                    "description": "Reverse speed 0-100 (default 70).",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "reverse_steer_right",
        "description": "Drive backward while steering right.",
        "input_schema": {
            "type": "object",
            "properties": {
                "speed": {
                    "type": "integer",
                    "description": "Reverse speed 0-100 (default 70).",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },

    # ── Camera pan/tilt: absolute ─────────────────────────────────────────
    {
        "name": "camera_pan_to",
        "description": "Pan the camera to an absolute angle (30-140 degrees).",
        "input_schema": {
            "type": "object",
            "properties": {
                "angle": {
                    "type": "integer",
                    "description": "Target pan angle in degrees.",
                    "minimum": 30,
                    "maximum": 140,
                },
            },
            "required": ["angle"],
        },
    },
    {
        "name": "camera_tilt_to",
        "description": "Tilt the camera to an absolute angle (35-105 degrees).",
        "input_schema": {
            "type": "object",
            "properties": {
                "angle": {
                    "type": "integer",
                    "description": "Target tilt angle in degrees.",
                    "minimum": 35,
                    "maximum": 105,
                },
            },
            "required": ["angle"],
        },
    },

    # ── Camera pan/tilt: relative step ────────────────────────────────────
    {
        "name": "camera_pan_left",
        "description": "Pan the camera left by a number of degrees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "degrees": {
                    "type": "integer",
                    "description": "Degrees to pan left (default 10).",
                    "minimum": 1,
                    "maximum": 90,
                },
            },
            "required": [],
        },
    },
    {
        "name": "camera_pan_right",
        "description": "Pan the camera right by a number of degrees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "degrees": {
                    "type": "integer",
                    "description": "Degrees to pan right (default 10).",
                    "minimum": 1,
                    "maximum": 90,
                },
            },
            "required": [],
        },
    },
    {
        "name": "camera_tilt_up",
        "description": "Tilt the camera up by a number of degrees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "degrees": {
                    "type": "integer",
                    "description": "Degrees to tilt up (default 10).",
                    "minimum": 1,
                    "maximum": 90,
                },
            },
            "required": [],
        },
    },
    {
        "name": "camera_tilt_down",
        "description": "Tilt the camera down by a number of degrees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "degrees": {
                    "type": "integer",
                    "description": "Degrees to tilt down (default 10).",
                    "minimum": 1,
                    "maximum": 90,
                },
            },
            "required": [],
        },
    },

    # ── Camera pan/tilt: continuous joystick ──────────────────────────────
    {
        "name": "camera_move_start",
        "description": "Start continuous camera movement in a direction. Call camera_move_stop to halt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "Movement direction.",
                    "enum": [
                        "up", "down", "left", "right",
                        "up_left", "up_right", "down_left", "down_right",
                    ],
                },
            },
            "required": ["direction"],
        },
    },
    {
        "name": "camera_move_stop",
        "description": "Stop continuous camera movement and hold current position.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "camera_center",
        "description": "Return camera to center position (pan and tilt).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "camera_get_angles",
        "description": "Get current camera pan and tilt angles.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ── Ultrasonic sensor ─────────────────────────────────────────────────
    {
        "name": "get_distance",
        "description": "Get the current obstacle distance in centimeters from the ultrasonic sensor.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "is_path_clear",
        "description": "Check if the path ahead is clear of obstacles.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# ── Continuous movement direction map ─────────────────────────────────────────

_CAMERA_DIRECTION_MAP: dict[str, str] = {
    "up": "tilt_up_start",
    "down": "tilt_down_start",
    "left": "pan_left_start",
    "right": "pan_right_start",
    "up_left": "up_left_start",
    "up_right": "up_right_start",
    "down_left": "down_left_start",
    "down_right": "down_right_start",
}


# ── Executor ──────────────────────────────────────────────────────────────────

def execute(
    tool_name: str,
    tool_args: dict[str, Any],
    motor: Any = None,
    pan_tilt: Any = None,
    ultrasonic: Any = None,
) -> dict:
    """Execute a tool call and return the result dict.

    Args:
        tool_name: Name from the TOOLS list.
        tool_args: Arguments from the LLM's tool call.
        motor: MotorController instance.
        pan_tilt: PanTilt instance.
        ultrasonic: Ultrasonic instance.

    Returns:
        Result dict with at least a "status" key.
    """

    # ── Motor: drive ──────────────────────────────────────────────────────
    if tool_name == "motor_forward":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        speed = tool_args.get("speed")
        return motor.front(speed) if speed is not None else motor.front()

    if tool_name == "motor_backward":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        speed = tool_args.get("speed")
        return motor.back(speed) if speed is not None else motor.back()

    if tool_name == "motor_stop":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        return motor.stop()

    # ── Motor: steering ───────────────────────────────────────────────────
    if tool_name == "steer_left":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        return motor.left()

    if tool_name == "steer_right":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        return motor.right()

    if tool_name == "steer_left_hold":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        return motor.steer_left_hold()

    if tool_name == "steer_right_hold":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        return motor.steer_right_hold()

    if tool_name == "steer_center":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        return motor.steer_center()

    # ── Motor: compound ───────────────────────────────────────────────────
    if tool_name == "reverse_steer_left":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        motor.steer_left_hold()
        speed = tool_args.get("speed")
        return motor.back(speed) if speed is not None else motor.back()

    if tool_name == "reverse_steer_right":
        if not motor:
            return {"status": "error", "message": "motor not available"}
        motor.steer_right_hold()
        speed = tool_args.get("speed")
        return motor.back(speed) if speed is not None else motor.back()

    # ── Camera: absolute ──────────────────────────────────────────────────
    if tool_name == "camera_pan_to":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        return pan_tilt.pan_to(tool_args["angle"])

    if tool_name == "camera_tilt_to":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        return pan_tilt.tilt_to(tool_args["angle"])

    # ── Camera: relative step ─────────────────────────────────────────────
    if tool_name == "camera_pan_left":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        deg = tool_args.get("degrees", 10)
        return pan_tilt.pan_left(deg)

    if tool_name == "camera_pan_right":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        deg = tool_args.get("degrees", 10)
        return pan_tilt.pan_right(deg)

    if tool_name == "camera_tilt_up":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        deg = tool_args.get("degrees", 10)
        return pan_tilt.tilt_up(deg)

    if tool_name == "camera_tilt_down":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        deg = tool_args.get("degrees", 10)
        return pan_tilt.tilt_down(deg)

    # ── Camera: continuous ────────────────────────────────────────────────
    if tool_name == "camera_move_start":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        direction = tool_args["direction"]
        method_name = _CAMERA_DIRECTION_MAP.get(direction)
        if not method_name:
            return {"status": "error", "message": f"unknown direction: {direction}"}
        method = getattr(pan_tilt, method_name)
        return method()

    if tool_name == "camera_move_stop":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        return pan_tilt.servo_stop()

    if tool_name == "camera_center":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        return pan_tilt.center()

    if tool_name == "camera_get_angles":
        if not pan_tilt:
            return {"status": "error", "message": "pan_tilt not available"}
        return {"status": "ok", **pan_tilt.get_angles()}

    # ── Ultrasonic ────────────────────────────────────────────────────────
    if tool_name == "get_distance":
        if not ultrasonic:
            return {"status": "error", "message": "ultrasonic not available"}
        distance = ultrasonic.get_distance()
        return {
            "status": "ok",
            "distance_cm": distance,
            "zone": ultrasonic.get_zone(),
        }

    if tool_name == "is_path_clear":
        if not ultrasonic:
            return {"status": "error", "message": "ultrasonic not available"}
        distance = ultrasonic.get_distance()
        return {
            "status": "ok",
            "clear": ultrasonic.is_clear(),
            "distance_cm": distance,
            "zone": ultrasonic.get_zone(),
        }

    return {"status": "error", "message": f"unknown tool: {tool_name}"}
