#!/usr/bin/env python3
"""
MCP server for Ramu RC Car.
Exposes all hardware controls as MCP tools for LLM-driven operation.
"""

import sys

sys.path.insert(0, "/home/rambabu/rambabu_rc")

import os
import time
import threading

import cv2
import RPi.GPIO as GPIO

import config
from lib.motor import MotorController
from lib.camera import Camera
from lib.ultrasonic import Ultrasonic
from lib.pan_tilt import PanTilt
from lib.speaker import Speaker
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

# ---------------------------------------------------------------------------
# Lazy hardware init — deferred so MCP handshake completes immediately
# ---------------------------------------------------------------------------

_hw_lock = threading.Lock()
_hw_ready = False

motor: MotorController | None = None
ultra: Ultrasonic | None = None
pan_tilt: PanTilt | None = None
camera: Camera | None = None
speaker: Speaker | None = None


def _init_hardware() -> None:
    """Initialize all hardware. Called once on first tool invocation."""
    global _hw_ready, motor, ultra, pan_tilt, camera, speaker

    with _hw_lock:
        if _hw_ready:
            return

        # Suppress libcamera stderr noise during init
        stderr_fd = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)

        try:
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)

            motor = MotorController()
            ultra = Ultrasonic()
            ultra.wait_for_reading(timeout=2.0)

            motor.set_obstacle_check(
                check_fn=lambda: ultra.is_obstacle_confirmed(),
                clear_fn=lambda: ultra.get_distance() > config.OBSTACLE_CLEAR_DISTANCE,
            )

            time.sleep(0.5)
            try:
                pan_tilt = PanTilt()
            except Exception as e:
                print(
                    f"[WARN] PanTilt not available (PCA9685 not connected?): {e}",
                    file=sys.stderr,
                )
                pan_tilt = None

            camera = Camera()
            camera.start()
            time.sleep(1)

            try:
                speaker = Speaker()
            except Exception:
                speaker = None

            _hw_ready = True
        finally:
            # Restore stderr
            os.dup2(stderr_fd, 2)
            os.close(stderr_fd)
            os.close(devnull)


def _hw() -> None:
    """Ensure hardware is initialized. Call at start of every tool."""
    if not _hw_ready:
        _init_hardware()


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("Rambabu RC Car")


# ── Motor drive ───────────────────────────────────────────────────────────


@mcp.tool()
def motor_forward(speed: int = 60) -> str:
    """Drive the car forward at given speed (0-100). Capped at 70 for safety."""
    _hw()
    speed = min(max(speed, 0), 70)
    result = motor.front(speed)
    if result["status"] == "error":
        return f"Blocked: {result['message']}"
    return f"Moving forward at {speed}%"


@mcp.tool()
def motor_backward(speed: int = 60) -> str:
    """Drive the car backward at given speed (0-100). Capped at 70 for safety."""
    _hw()
    speed = min(max(speed, 0), 70)
    motor.back(speed)
    return f"Moving backward at {speed}%"


@mcp.tool()
def motor_stop() -> str:
    """Stop all motors immediately."""
    _hw()
    motor.stop()
    return "Stopped"


# ── Steering ──────────────────────────────────────────────────────────────


@mcp.tool()
def steer_left() -> str:
    """Steer left briefly then return to center."""
    _hw()
    motor.left()
    return "Steered left (pulse)"


@mcp.tool()
def steer_right() -> str:
    """Steer right briefly then return to center."""
    _hw()
    motor.right()
    return "Steered right (pulse)"


@mcp.tool()
def steer_left_hold() -> str:
    """Hold steering left until steer_center() is called."""
    _hw()
    motor.steer_left_hold()
    return "Steering held left"


@mcp.tool()
def steer_right_hold() -> str:
    """Hold steering right until steer_center() is called."""
    _hw()
    motor.steer_right_hold()
    return "Steering held right"


@mcp.tool()
def steer_center() -> str:
    """Return steering to center position."""
    _hw()
    motor.steer_center()
    return "Steering centered"


# ── Camera pan/tilt ───────────────────────────────────────────────────────


@mcp.tool()
def camera_pan_left(degrees: int = 20) -> str:
    """Pan camera left by given degrees."""
    _hw()
    if pan_tilt is None:
        return "PanTilt not available (PCA9685 not connected)"
    result = pan_tilt.pan_left(degrees)
    return f"Camera panned left {degrees}°. Pan angle: {result['pan']}°"


@mcp.tool()
def camera_pan_right(degrees: int = 20) -> str:
    """Pan camera right by given degrees."""
    _hw()
    if pan_tilt is None:
        return "PanTilt not available (PCA9685 not connected)"
    result = pan_tilt.pan_right(degrees)
    return f"Camera panned right {degrees}°. Pan angle: {result['pan']}°"


@mcp.tool()
def camera_tilt_up(degrees: int = 20) -> str:
    """Tilt camera up by given degrees."""
    _hw()
    if pan_tilt is None:
        return "PanTilt not available (PCA9685 not connected)"
    result = pan_tilt.tilt_up(degrees)
    return f"Camera tilted up {degrees}°. Tilt angle: {result['tilt']}°"


@mcp.tool()
def camera_tilt_down(degrees: int = 20) -> str:
    """Tilt camera down by given degrees."""
    _hw()
    if pan_tilt is None:
        return "PanTilt not available (PCA9685 not connected)"
    result = pan_tilt.tilt_down(degrees)
    return f"Camera tilted down {degrees}°. Tilt angle: {result['tilt']}°"


@mcp.tool()
def camera_center() -> str:
    """Center camera to forward-facing position."""
    _hw()
    if pan_tilt is None:
        return "PanTilt not available (PCA9685 not connected)"
    pan_tilt.center()
    return f"Camera centered at pan={config.PAN_CENTER}° tilt={config.TILT_CENTER}°"


@mcp.tool()
def camera_look_at(pan_angle: int, tilt_angle: int) -> str:
    """Point camera to specific pan and tilt angles."""
    _hw()
    if pan_tilt is None:
        return "PanTilt not available (PCA9685 not connected)"
    pan_result = pan_tilt.pan_to(pan_angle)
    tilt_result = pan_tilt.tilt_to(tilt_angle)
    return f"Camera at pan={pan_result['pan']}° tilt={tilt_result['tilt']}°"


@mcp.tool()
def get_camera_angles() -> str:
    """Get current camera pan and tilt angles."""
    _hw()
    if pan_tilt is None:
        return "PanTilt not available (PCA9685 not connected)"
    angles = pan_tilt.get_angles()
    return f"Pan: {angles['pan']}°, Tilt: {angles['tilt']}°"


# ── Ultrasonic sensor ────────────────────────────────────────────────────


@mcp.tool()
def get_distance() -> str:
    """Get ultrasonic distance reading and obstacle status."""
    _hw()
    distance = ultra.get_distance()
    zone = ultra.get_zone()
    obstacle = ultra.is_obstacle_confirmed()
    status = "OBSTACLE DETECTED" if obstacle else "Path clear"
    return f"Distance: {distance:.1f}cm | Zone: {zone} | {status}"


# ── Camera capture ────────────────────────────────────────────────────────


@mcp.tool()
def capture_image() -> Image:
    """Capture a JPEG image from the camera. Returns the image directly."""
    _hw()
    frame = camera.get_frame()
    if frame is None:
        raise ValueError("Camera not ready")
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return Image(data=jpeg.tobytes(), format="jpeg")


# ── Speaker ───────────────────────────────────────────────────────────────


@mcp.tool()
def speak(text: str) -> str:
    """Speak text through the Bluetooth speaker."""
    _hw()
    if speaker is None:
        return "Speaker not available"
    speaker.speak(text)
    return f"Spoke: {text}"


@mcp.tool()
def play_audio(file_path: str) -> str:
    """Play an audio file (MP3 or WAV) through the speaker."""
    _hw()
    if speaker is None:
        return "Speaker not available"
    if file_path.endswith(".mp3"):
        speaker.play_mp3_async(file_path)
    else:
        speaker.play_wav_async(file_path)
    return f"Playing: {file_path}"


# ── System status ─────────────────────────────────────────────────────────


@mcp.tool()
def get_status() -> str:
    """Get full system status: distance, camera angles, servo limits."""
    _hw()
    dist = ultra.get_distance()
    zone = ultra.get_zone()
    status = f"Distance: {dist:.1f}cm ({zone})"
    if pan_tilt is not None:
        angles = pan_tilt.get_angles()
        status += (
            f" | Pan: {angles['pan']}° [{config.PAN_MIN}-{config.PAN_MAX}]"
            f" | Tilt: {angles['tilt']}° [{config.TILT_MIN}-{config.TILT_MAX}]"
        )
    else:
        status += " | PanTilt: not connected"
    return status


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        mcp.run()
    except KeyboardInterrupt:
        if motor is not None:
            motor.stop()
        if pan_tilt is not None:
            pan_tilt.cleanup()
        if camera is not None:
            camera.cleanup()
        if ultra is not None:
            ultra.cleanup()
        if speaker is not None:
            speaker.cleanup()
        if _hw_ready:
            GPIO.cleanup()
