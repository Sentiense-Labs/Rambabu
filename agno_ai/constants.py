"""
Central constants for Rambabu's Agno brain.

Pulled from: brain/brain.py, brain/hardware_tools.py,
brain/sonar_guard.py, brain/movement_manager.py.
"""

# ── Sonar zones ────────────────────────────────────────────────────────────────

ZONE_CRITICAL_CM: float = 25.0
ZONE_CLOSE_CM: float = 70.0
ZONE_MEDIUM_CM: float = 150.0

# ── Motion ────────────────────────────────────────────────────────────────────

DEFAULT_SPEED: int = 60
DRIVE_SPEED: int = 80
REVERSE_HARD_CAP_S: float = 0.5

# Measured cruising speed at DRIVE_SPEED (80 duty) — calibrated 2026-04-17.
# Forward — hard floor: sonar confirmed 111 cm in 1.88 s cruise → 59 cm/s
#   NOTE: surface-dependent (carpet ~44 cm/s, hard floor ~59 cm/s)
# Reverse: formula gave 1.205 s → 30 cm actual → V = 30/(1.205-0.25) = 31.4 cm/s
# Startup dead-time (motor on, wheels not yet moving): 0.25 s.
BASE_SPEED_CM_PER_S: float = 50.0           # straight forward effective avg (cruise ~59, accel drags to ~50)
REVERSE_SPEED_CM_PER_S: float = 44.0        # straight back at 80% duty (calibrated)
REVERSE_SPEED_100_CM_PER_S: float = 55.0    # straight back at 100% duty (estimated ~1.25× from 80% baseline; recalibrate if needed)
REVERSE_DUTY: int = 100                     # motor duty cycle for all reverse moves
TURN_LEFT_SPEED_CM_PER_S: float = 19.0   # left arc (calibrated: ~32 cm in 1.75 s cruise)
TURN_RIGHT_SPEED_CM_PER_S: float = 19.0  # right arc (not yet calibrated — mirror of left)
TURN_BACK_SPEED_CM_PER_S: float = 19.0   # back_left / back_right arc (not yet calibrated)
BASE_SPEED_DUTY: float = 80.0

# Dead-time added to every move to compensate for motor startup inertia.
# The motor takes ~0.25 s to break static friction and begin moving.
# During this window, displacement is ~0 cm.
MOTOR_STARTUP_OFFSET_S: float = 0.40    # observed dead-time from sonar profile (wheels don't move until ~0.40s)

# Active braking (movement_manager.py)
BRAKE_DUTY: int = 70
BRAKE_DURATION_S: float = 0.08

# Pre-flight burst
PREFLIGHT_BURST_COUNT: int = 5
PREFLIGHT_BURST_SPACING_S: float = 0.05

# ── Vision ────────────────────────────────────────────────────────────────────

GEMINI_VISION_MODEL: str = "gemini-2.5-flash-lite"
MAX_IMAGE_DIM: int = 512
JPEG_QUALITY: int = 80

# ── Agent defaults ─────────────────────────────────────────────────────────────

DEFAULT_MODEL: str = "gemini-2.5-flash"
COMPRESS_MODEL: str = "gemini-2.5-flash-lite"
DEFAULT_MAX_ITERATIONS: int = 100
DEFAULT_TEMPERATURE: float = 0.3
GOAL_CHECK_INTERVAL_S: float = 10.0

# Empty response retry (brain.py)
MAX_EMPTY_RESPONSE_RETRIES: int = 3

# ── Maneuvers ─────────────────────────────────────────────────────────────────

TURNING_RADIUS_CM: float = 65.0
TURNING_DIAMETER_CM: float = 130.0
SPEED_CM_PER_S_AT_80: float = 50.0
DEG_PER_SEC_OF_ARC: float = 31.0

UTURN_SINGLE_ARC_S: float = 5.8
UTURN_FRONT_CLEARANCE_CM: float = 85.0
UTURN_SIDE_CLEARANCE_CM: float = 140.0

TPT_ARC_PER_LEG_S: float = 1.0
TPT_REVERSE_PER_LEG_S: float = 1.5
TPT_FINAL_STRAIGHT_S: float = 0.5
TPT_TARGET_ARC_TIME_S: float = 6.0
TPT_MAX_LEGS: int = 8
TPT_INTRA_STEP_PAUSE_S: float = 0.1

DISENGAGE_BACK_S: float = 0.5
DISENGAGE_THRESHOLD_CM: float = 60.0

STEER_LOCK_SETTLE_S: float = 0.25

_CORRECTION_SECONDS: dict[str, float] = {
    "light": 0.2,
    "medium": 0.4,
    "strong": 0.6,
}

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_ROOT_PATH: str = "/Users/mrpurple/Wavefuel/rambabu_rc"
SOUL_FILE_PATH: str = f"{PROJECT_ROOT_PATH}/brain/SOUL.md"
OBSERVATIONS_FILE_PATH: str = f"{PROJECT_ROOT_PATH}/brain/memory/observations.md"

# ── API key validation ──────────────────────────────────────────────────────


def check_gemini_key() -> None:
    import os

    if not os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY"):
        raise RuntimeError(
            "GOOGLE_GENERATIVE_AI_API_KEY is not set. Add it to .env and try again."
        )


# ── Tool timeouts (seconds) ─────────────────────────────────────────────────────

TIMEOUT_DISTANCE: float = 15.0
TIMEOUT_PAN_TILT: float = 15.0
TIMEOUT_LOOK_AROUND: float = 30.0
TIMEOUT_VISUAL_SURVEY: float = 75.0
TIMEOUT_MOVE: float = 30.0
TIMEOUT_START_MOVING: float = 5.0
TIMEOUT_STOP_MOVING: float = 5.0
TIMEOUT_REVERSE_STEER: float = 10.0
TIMEOUT_THREE_POINT_TURN: float = 30.0
TIMEOUT_ALIGN_TO_PATH: float = 10.0

# ── Visual Survey ──────────────────────────────────────────────────────────────

# Pan angles (degrees) swept left→right during visual_survey.
# PAN_MIN=55, PAN_CENTER=110, PAN_MAX=165 — these hit those limits
# plus two intermediate positions for a 5-panel panorama.
# PAN_DIRECTION=-1 means the servo is physically inverted:
#   lower angle value → physically facing RIGHT
#   higher angle value → physically facing LEFT
# Sweep right→left in angle space so the collage reads left→right physically.
SURVEY_PAN_ANGLES: list[int] = [165, 138, 110, 82, 55]
SURVEY_PAN_LABELS: list[str] = ["HARD LEFT", "LEFT", "FRONT", "RIGHT", "HARD RIGHT"]

# Tilt angles swept top→bottom per pan column.
# TILT_DIRECTION=-1 means the servo is physically inverted:
#   lower angle value → physically looking UP
#   higher angle value → physically looking DOWN
# Three tilt levels — top row is slightly elevated (not full ceiling).
# 55° is halfway between 25° (full ceiling) and 80° (level horizon).
SURVEY_TILT_ANGLES: list[int] = [55, 80, 130]
SURVEY_TILT_LABELS: list[str] = ["UP", "LEVEL", "DOWN"]

SURVEY_SETTLE_PAN_S: float = 0.35   # seconds inside pan_snap for servo to arrive + initial settle
SURVEY_SETTLE_TILT_S: float = 0.35  # seconds inside tilt_snap for servo to arrive
SURVEY_CAPTURE_SETTLE_S: float = 0.15  # extra wait after snap before capture (vibration die-down)
SURVEY_SETTLE_S: float = 0.20          # legacy fallback
SURVEY_TILE_W: int = 320       # pixels per tile in collage
SURVEY_TILE_H: int = 240
SURVEY_LABEL_H: int = 28       # direction banner height in pixels
