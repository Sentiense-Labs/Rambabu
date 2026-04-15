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

# MovementManager estimated speed
BASE_SPEED_CM_PER_S: float = 56.0
BASE_SPEED_DUTY: float = 80.0

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
SPEED_CM_PER_S_AT_80: float = 67.0
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
TIMEOUT_MOVE: float = 30.0
TIMEOUT_SAY: float = 30.0
TIMEOUT_START_MOVING: float = 5.0
TIMEOUT_STOP_MOVING: float = 5.0
TIMEOUT_REVERSE_STEER: float = 10.0
TIMEOUT_THREE_POINT_TURN: float = 30.0
TIMEOUT_ALIGN_TO_PATH: float = 10.0
