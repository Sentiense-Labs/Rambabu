"""
Direct hardware tool implementations for Rambabu's brain.

When the brain runs inside main.py (where hardware is already initialised),
these functions are used instead of spawning subprocesses. They accept
live hardware objects and produce the same output format as the standalone
brain/*.py scripts so the LLM sees identical text.

Each function signature is:
    execute_<tool>(hw: HardwareContext, args: dict) -> ToolResult
"""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass
from typing import Any

import cv2
from PIL import Image

from brain.tools import ToolResult
from utils.elevenlabs import synthesize

# ---------------------------------------------------------------------------
# Hardware context
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HardwareContext:
    """Holds references to live hardware objects from main.py.

    Any field may be None if that peripheral failed to initialise —
    the corresponding tool will fall back to subprocess mode.
    """
    motor: Any = None             # lib.motor.MotorController
    ultrasonic: Any = None        # lib.ultrasonic.Ultrasonic
    pan_tilt: Any = None          # lib.pan_tilt.PanTilt
    camera: Any = None            # lib.camera.Camera
    speaker: Any = None           # lib.speaker.Speaker
    sonar_guard: Any = None       # brain.sonar_guard.SonarGuard
    movement_manager: Any = None  # brain.movement_manager.MovementManager


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _zone(distance_cm: float) -> str:
    if distance_cm < 20:
        return "critical"
    if distance_cm < 50:
        return "close"
    if distance_cm < 150:
        return "medium"
    return "clear"


_DRIVE_SPEED = 80
_SAFETY_DISTANCE_CM = 50.0
_GEMINI_VISION_MODEL = "gemini-2.5-flash-lite"
_MAX_IMAGE_DIM = 512
_JPEG_QUALITY = 80

_LOOK_AROUND_PERSONA = (
    "You are Rambabu, a small AI-powered RC rover with a camera. "
    "This image is what you can see right now."
)
_LOOK_AROUND_DEFAULT = (
    "Describe your surroundings in 2-3 short conversational sentences "
    "— first person, present tense. Mention specific objects you notice. "
    "Be curious and a little opinionated if something catches your eye. "
    "If the view is boring, say so honestly. "
    "End with one short sentence in this format: "
    "'Open path: left' or 'Open path: front' or 'Open path: right' or "
    "'Open path: none — back up'. Pick the most walkable lane based on "
    "what you see. If everything in view is blocked or cluttered, say "
    "'none — back up'."
)
_LOOK_AROUND_OUTPUT_RULES = (
    "Output only the spoken words — no brackets, no stage directions, "
    "no bullet points, no labels."
)


def _build_look_around_prompt(question: str | None) -> str:
    if question and question.strip():
        task = (
            f'The user just told you: "{question.strip()}"\n'
            "Respond to that request based on what you see in the image, "
            "in 2-3 short conversational sentences — first person, present "
            "tense. Stay in character as Rambabu."
        )
    else:
        task = _LOOK_AROUND_DEFAULT
    return f"{_LOOK_AROUND_PERSONA}\n\n{task}\n\n{_LOOK_AROUND_OUTPUT_RULES}"


# ---------------------------------------------------------------------------
# distance
# ---------------------------------------------------------------------------

def execute_distance(hw: HardwareContext, _args: dict[str, Any]) -> ToolResult:
    """Read forward ultrasonic distance.

    When SonarGuard is running it is the canonical sonar reader — we use its
    cached snapshot instead of touching the Ultrasonic directly. Otherwise
    we fall back to the raw ultrasonic instance.
    """
    started = time.time()
    try:
        if hw.sonar_guard is not None and hw.sonar_guard.is_running:
            distance_cm, zone = hw.sonar_guard.snapshot()
        else:
            distance_cm = hw.ultrasonic.get_distance()
            zone = _zone(distance_cm)
        output = f"distance_cm: {distance_cm:.1f}\nzone: {zone}"
        return ToolResult(
            name="distance",
            ok=True,
            output=output,
            elapsed_s=time.time() - started,
        )
    except Exception as exc:
        return ToolResult(
            name="distance",
            ok=False,
            output=f"status: error\nmessage: {exc}",
            elapsed_s=time.time() - started,
        )


# ---------------------------------------------------------------------------
# start_moving / stop_moving — continuous motion via MovementManager
# ---------------------------------------------------------------------------


def execute_start_moving(hw: HardwareContext, args: dict[str, Any]) -> ToolResult:
    """Begin continuous movement. Returns immediately — motor runs until
    stop_moving is called or SonarGuard intervenes.
    """
    started = time.time()
    direction = args.get("direction")
    speed = int(args.get("speed", 80))
    try:
        result = hw.movement_manager.go(direction, speed)
        ok = result.get("status") == "ok"
        return ToolResult(
            name="start_moving",
            ok=ok,
            output=str(result),
            elapsed_s=time.time() - started,
        )
    except Exception as exc:
        try:
            hw.motor.stop()
        except Exception:
            pass
        return ToolResult(
            name="start_moving",
            ok=False,
            output=str({"status": "error", "message": str(exc)}),
            elapsed_s=time.time() - started,
        )


def execute_maneuver(
    name: str, hw: HardwareContext, args: dict[str, Any]
) -> ToolResult:
    """Direct-mode dispatch for compound driving maneuvers."""
    from brain.maneuvers import (
        align_to_path,
        reverse_steer,
        three_point_turn,
    )

    started = time.time()
    try:
        if name == "reverse_steer":
            result = reverse_steer(
                hw,
                steer_direction=args.get("steer_direction", ""),
                seconds=float(args.get("seconds", 0.4)),
            )
        elif name == "three_point_turn":
            result = three_point_turn(
                hw, preferred_side=args.get("preferred_side", "right")
            )
        elif name == "align_to_path":
            result = align_to_path(
                hw,
                drift_direction=args.get("drift_direction", ""),
                correction_strength=args.get("correction_strength", "light"),
            )
        else:
            result = {"status": "error", "message": f"unknown maneuver: {name}"}

        return ToolResult(
            name=name,
            ok=result.get("status") != "error",
            output=str(result),
            elapsed_s=time.time() - started,
        )
    except Exception as exc:
        try:
            hw.motor.stop()
        except Exception:
            pass
        return ToolResult(
            name=name,
            ok=False,
            output=str({"status": "error", "message": str(exc)}),
            elapsed_s=time.time() - started,
        )


def execute_stop_moving(hw: HardwareContext, _args: dict[str, Any]) -> ToolResult:
    """Halt all motor movement immediately."""
    started = time.time()
    try:
        result = hw.movement_manager.stop()
        return ToolResult(
            name="stop_moving",
            ok=True,
            output=str(result),
            elapsed_s=time.time() - started,
        )
    except Exception as exc:
        try:
            hw.motor.stop()
        except Exception:
            pass
        return ToolResult(
            name="stop_moving",
            ok=False,
            output=str({"status": "error", "message": str(exc)}),
            elapsed_s=time.time() - started,
        )


# ---------------------------------------------------------------------------
# move
# ---------------------------------------------------------------------------

def execute_move(hw: HardwareContext, args: dict[str, Any]) -> ToolResult:
    """Drive the rover using live MotorController + Ultrasonic."""
    started = time.time()
    direction = args.get("direction", "stop")
    seconds = float(args.get("seconds", 0.5))
    seconds = min(seconds, 9.0)

    try:
        if direction == "stop":
            hw.motor.stop()
            output = str({"status": "ok", "action": "stop"})
            return ToolResult(name="move", ok=True, output=output,
                              elapsed_s=time.time() - started)

        # Safety check before any forward-direction move
        if direction in ("forward", "left", "right") and hw.ultrasonic is not None:
            dist = hw.ultrasonic.get_distance()
            if dist < _SAFETY_DISTANCE_CM:
                output = str({
                    "status": "blocked",
                    "reason": "obstacle_too_close",
                    "distance_cm": round(dist, 1),
                    "threshold_cm": _SAFETY_DISTANCE_CM,
                })
                return ToolResult(name="move", ok=False, output=output,
                                  elapsed_s=time.time() - started)

        if direction == "forward":
            hw.motor.front(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            final = hw.ultrasonic.get_distance() if hw.ultrasonic else 0.0
            output = str({
                "status": "ok",
                "direction": "forward",
                "duration_s": round(seconds, 2),
                "final_distance_cm": round(final, 1),
            })

        elif direction == "back":
            seconds = min(seconds, 0.5)  # hard cap — no rear sensor
            hw.motor.back(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            output = str({
                "status": "ok",
                "direction": "back",
                "duration_s": round(seconds, 2),
            })

        elif direction == "back_left":
            # During reverse, left steer swings the FRONT right, rear left.
            seconds = min(seconds, 0.5)
            hw.motor.steer_left_hold()
            hw.motor.back(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            hw.motor.steer_center()
            output = str({
                "status": "ok",
                "direction": "back_left",
                "duration_s": round(seconds, 2),
                "note": "front swung RIGHT, rear swung LEFT",
            })

        elif direction == "back_right":
            # During reverse, right steer swings the FRONT left, rear right.
            seconds = min(seconds, 0.5)
            hw.motor.steer_right_hold()
            hw.motor.back(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            hw.motor.steer_center()
            output = str({
                "status": "ok",
                "direction": "back_right",
                "duration_s": round(seconds, 2),
                "note": "front swung LEFT, rear swung RIGHT",
            })

        elif direction == "left":
            hw.motor.steer_left_hold()
            hw.motor.front(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            hw.motor.steer_center()
            final = hw.ultrasonic.get_distance() if hw.ultrasonic else 0.0
            output = str({
                "status": "ok",
                "direction": "left",
                "duration_s": round(seconds, 2),
                "final_distance_cm": round(final, 1),
            })

        elif direction == "right":
            hw.motor.steer_right_hold()
            hw.motor.front(_DRIVE_SPEED)
            time.sleep(seconds)
            hw.motor.stop()
            hw.motor.steer_center()
            final = hw.ultrasonic.get_distance() if hw.ultrasonic else 0.0
            output = str({
                "status": "ok",
                "direction": "right",
                "duration_s": round(seconds, 2),
                "final_distance_cm": round(final, 1),
            })

        else:
            output = str({"status": "error", "message": f"unknown direction: {direction}"})
            return ToolResult(name="move", ok=False, output=output,
                              elapsed_s=time.time() - started)

        return ToolResult(name="move", ok=True, output=output,
                          elapsed_s=time.time() - started)

    except Exception as exc:
        hw.motor.stop()
        return ToolResult(name="move", ok=False,
                          output=str({"status": "error", "message": str(exc)}),
                          elapsed_s=time.time() - started)


# ---------------------------------------------------------------------------
# pan_tilt
# ---------------------------------------------------------------------------

def execute_pan_tilt(hw: HardwareContext, args: dict[str, Any]) -> ToolResult:
    """Move camera servos using the live PanTilt instance."""
    started = time.time()
    action = args.get("action", "")
    degrees = int(args.get("degrees", 40))

    try:
        pt = hw.pan_tilt
        if action == "pan_left":
            result = pt.pan_left(degrees)
        elif action == "pan_right":
            result = pt.pan_right(degrees)
        elif action == "tilt_up":
            result = pt.tilt_up(degrees)
        elif action == "tilt_down":
            result = pt.tilt_down(degrees)
        elif action == "center":
            result = pt.center()
        elif action == "angles":
            result = pt.get_angles()
        else:
            result = {"status": "error", "message": f"unknown action: {action}"}

        return ToolResult(
            name="pan_tilt",
            ok=result.get("status") != "error",
            output=str(result),
            elapsed_s=time.time() - started,
        )
    except Exception as exc:
        return ToolResult(name="pan_tilt", ok=False,
                          output=str({"status": "error", "message": str(exc)}),
                          elapsed_s=time.time() - started)


# ---------------------------------------------------------------------------
# look_around
# ---------------------------------------------------------------------------

def execute_look_around(hw: HardwareContext, args: dict[str, Any]) -> ToolResult:
    """Capture a frame and describe it using Gemini Vision."""
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    started = time.time()
    question = (args.get("question") or "").strip() or None

    try:
        frame = hw.camera.get_frame()
        if frame is None:
            return ToolResult(name="look_around", ok=False,
                              output="error: camera returned no frame",
                              elapsed_s=time.time() - started)

        ok, jpeg_buf = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY]
        )
        if not ok:
            return ToolResult(name="look_around", ok=False,
                              output="error: JPEG encoding failed",
                              elapsed_s=time.time() - started)

        image = Image.open(io.BytesIO(jpeg_buf.tobytes()))
        image.thumbnail((_MAX_IMAGE_DIM, _MAX_IMAGE_DIM))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=_JPEG_QUALITY)

        image_part = types.Part.from_bytes(
            data=buf.getvalue(), mime_type="image/jpeg"
        )
        api_key = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
        client = genai.Client(api_key=api_key)
        prompt = _build_look_around_prompt(question)
        response = client.models.generate_content(
            model=_GEMINI_VISION_MODEL,
            contents=[image_part, prompt],
        )
        description = (response.text or "").strip()
        if not description:
            return ToolResult(name="look_around", ok=False,
                              output="error: Gemini returned empty description",
                              elapsed_s=time.time() - started)

        return ToolResult(name="look_around", ok=True, output=description,
                          elapsed_s=time.time() - started)

    except Exception as exc:
        return ToolResult(name="look_around", ok=False,
                          output=f"error: {exc}",
                          elapsed_s=time.time() - started)


# ---------------------------------------------------------------------------
# say
# ---------------------------------------------------------------------------

def execute_say(hw: HardwareContext, args: dict[str, Any]) -> ToolResult:
    """Speak text using the live Speaker instance."""
    started = time.time()
    text = (args.get("text") or "").strip()
    if not text:
        return ToolResult(name="say", ok=False,
                          output="status: error\nmessage: no text provided",
                          elapsed_s=time.time() - started)
    try:
        mp3 = synthesize(text)
        if mp3 is not None:
            hw.speaker.play_mp3_bytes(mp3)
            output = f"status: ok\nengine: elevenlabs\nbytes: {len(mp3)}"
        else:
            hw.speaker.speak_sync(text)
            output = "status: ok\nengine: pyttsx3"
        return ToolResult(name="say", ok=True, output=output,
                          elapsed_s=time.time() - started)
    except Exception as exc:
        return ToolResult(name="say", ok=False,
                          output=f"status: error\nmessage: {exc}",
                          elapsed_s=time.time() - started)
