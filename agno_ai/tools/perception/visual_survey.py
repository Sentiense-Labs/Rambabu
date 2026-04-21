"""
visual_survey — panoramic camera sweep with Gemini Vision analysis.

Sweeps the camera across 5 pan angles × 3 tilt levels (UP / LEVEL / DOWN)
and assembles the captures into a labelled 5-column × 3-row tiled collage,
then sends it to Gemini Vision for spatial analysis.

Use this instead of multiple look_around + pan_tilt calls whenever full
spatial awareness is needed.
"""

from __future__ import annotations

import io
import json
import os
import time
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai import constants as C
from agno_ai.lib.target_tracker import get_target_tracker
from google import genai as google_genai
from google.genai import types

# ── Sweep definitions ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Pos:
    pan_deg: int
    pan_label: str
    tilt_deg: int
    tilt_label: str

    @property
    def tile_label(self) -> str:
        return f"{self.pan_label} / {self.tilt_label}"

    @property
    def angle_hint(self) -> str:
        return f"({self.pan_deg}\u00b0, {self.tilt_deg}\u00b0)"


_PAN = list(zip(C.SURVEY_PAN_ANGLES, C.SURVEY_PAN_LABELS, strict=True))
_TILT = list(zip(C.SURVEY_TILT_ANGLES, C.SURVEY_TILT_LABELS, strict=True))

NUM_PAN = len(_PAN)
NUM_TILT = len(_TILT)

_TILT_UP_ROW = 0
_TILT_LEVEL_ROW = 1
_TILT_DOWN_ROW = 2

# ── Layout ─────────────────────────────────────────────────────────────────────

_TILE_W = C.SURVEY_TILE_W
_TILE_H = C.SURVEY_TILE_H
_LABEL_H = C.SURVEY_LABEL_H

# ── Response schema ────────────────────────────────────────────────────────────

class PathClearance(BaseModel):
    """Estimated clearance for one pan direction."""
    clear: bool
    clearance: Literal["blocked", "near", "medium", "far"]
    """
    blocked = obstacle fills the path (<30 cm estimated);
    near    = obstacle present but some space (~30–80 cm);
    medium  = clear for a while (~80–200 cm);
    far     = wide open (>200 cm or no visible obstacle).
    """
    obstacle: str | None = None
    confidence: float


class SurveyPaths(BaseModel):
    """Per-direction path clearance for all 5 pan columns."""
    hard_left: PathClearance
    left: PathClearance
    front: PathClearance
    right: PathClearance
    hard_right: PathClearance


class SurveyResult(BaseModel):
    """Full structured result from a visual survey."""
    scene: str
    """2–3 sentence first-person description of surroundings."""
    best_path: Literal["hard left", "left", "front", "right", "hard right", "none - back up"]
    paths: SurveyPaths
    target_seen: bool = False
    """True if the goal object mentioned in the question is visible anywhere in the collage."""
    target_direction: Literal["hard_left", "left", "front", "right", "hard_right"] | None = None
    """Column where the target object appears (matches paths keys). Null if target_seen=false."""
    target_confidence: float = 0.0
    """Certainty of the target sighting (0.0–1.0)."""


# ── Prompts ────────────────────────────────────────────────────────────────────

_PERSONA = "You are Rambabu, a small AI-powered RC rover (~25 cm wide, ~15 cm tall). "

_LAYOUT_DESCRIPTION = (
    f"This image is a {NUM_PAN}-column × {NUM_TILT}-row tiled grid of camera frames.\n"
    "Columns (left→right): HARD LEFT, LEFT, FRONT, RIGHT, HARD RIGHT.\n"
    "Rows (top→bottom): UP (overhead view), LEVEL (eye-level, ~15 cm off ground), DOWN (floor view).\n"
    "Each tile has a labelled direction banner at its top edge.\n"
    "\n"
    "ROW PRIORITY FOR NAVIGATION:\n"
    "  LEVEL row — primary: judge obstacles and clearance from this row.\n"
    "  DOWN row  — confirm the floor surface is clear of debris or drops.\n"
    "  UP row    — context only; ignore for path clearance.\n"
)

_PATH_KEYS = ["hard_left", "left", "front", "right", "hard_right"]

_CLEARANCE_GUIDE = (
    "For each of the 5 pan columns, judge clearance from the LEVEL tile:\n"
    "  blocked = obstacle occupies >60% of tile width, or fills the path — rover cannot pass.\n"
    "  near    = obstacle present and within ~30–80 cm (occupies 30–60% of tile width).\n"
    "  medium  = path clear for ~80–200 cm (obstacle small or near tile edge).\n"
    "  far     = wide open, >200 cm or no obstacle visible.\n"
    "\n"
    "CLEAR RULE: set clear=true ONLY when clearance is 'medium' or 'far' AND obstacle is null. "
    "If obstacle is non-null (any string), clear MUST be false — no exceptions.\n"
    "\n"
    "BRIGHT/OVEREXPOSED areas (white or blown-out) in a tile indicate a window or open "
    "doorway — treat as 'far' clearance ONLY if the floor in the DOWN tile for that "
    "column also shows open space. Otherwise treat as unknown (clearance='medium', "
    "confidence ≤ 0.6).\n"
)

_DEFAULT_TASK = (
    "Describe your surroundings — first person, present tense, 2-3 sentences max. "
    "Name key obstacles and open corridors by direction. Be concise. "
    "Then estimate path clearance for each of the 5 directions.\n\n"
    "Set target_seen=false (no specific target to find).\n\n"
) + _CLEARANCE_GUIDE

_TARGET_DETECTION_GUIDE = (
    "TARGET DETECTION:\n"
    "Read the QUESTION carefully. If it mentions a specific object to find "
    "(fridge, door, person, plant, etc.):\n"
    "  - Set target_seen=true if that object is visible anywhere in the collage.\n"
    "  - Set target_direction to the COLUMN where it appears: "
    "hard_left / left / front / right / hard_right.\n"
    "  - Set target_confidence to your certainty (0.0–1.0).\n"
    "  - A partial view (object at a tile edge) counts — "
    "set target_seen=true with lower confidence.\n"
    "If the question is general ('what is around me?') set target_seen=false.\n\n"
    "SCENE FIELD RULE — strictly enforced:\n"
    "  The `scene` field must describe ONLY what you observe visually: "
    "objects, their locations by column name, room features, and obstacles. "
    "NEVER write phrases like 'the path to it is right', 'navigate via X', "
    "'the clearest route to the target is Y', or any navigation recommendation "
    "inside `scene`. Those belong ONLY in `best_path` and `target_direction`.\n"
    "  CORRECT: 'The fridge is visible in the FRONT column at eye level.'\n"
    "  WRONG:   'The fridge is in FRONT but the clearest path to it is to the right.'\n"
    "The rover's agent reads `scene` for situational awareness and `target_direction` "
    "for where to go. Mixing them causes the agent to navigate away from the target.\n\n"
)


def _build_prompt(question: str | None) -> str:
    if question and question.strip():
        task = (
            f'The user asked: "{question.strip()}"\n'
            "Answer using the full grid. First person, present tense, 2-3 sentences max. "
            "Be concise — name what you see and where. "
            "Also estimate path clearance for all 5 directions.\n\n"
        ) + _TARGET_DETECTION_GUIDE + _CLEARANCE_GUIDE
    else:
        task = _DEFAULT_TASK
    return f"{_PERSONA}{_LAYOUT_DESCRIPTION}\n{task}"


# ── Image helpers ──────────────────────────────────────────────────────────────

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _annotate_tile(img: Image.Image, pos: _Pos) -> Image.Image:
    """Return new image with a direction banner prepended at the top."""
    w, h = img.size
    canvas = Image.new("RGB", (w, h + _LABEL_H))
    canvas.paste(img, (0, _LABEL_H))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([(0, 0), (w - 1, _LABEL_H - 1)], fill=(20, 20, 20))
    text = f"{pos.tile_label}  {pos.angle_hint}"
    font = _load_font(11)
    bbox = draw.textbbox((0, 0), text, font=font)
    x = max(0, (w - (bbox[2] - bbox[0])) // 2)
    y = max(0, (_LABEL_H - (bbox[3] - bbox[1])) // 2)
    draw.text((x, y), text, fill=(255, 220, 0), font=font)
    return canvas


def _bgr_to_pil(frame: np.ndarray, w: int = _TILE_W, h: int = _TILE_H) -> Image.Image:
    resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LANCZOS4)
    return Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))


def _build_grid(tiles: list[list[Image.Image]]) -> Image.Image:
    """Paste a NUM_TILT-row × NUM_PAN-column tile grid into one image."""
    tw, th = tiles[0][0].size
    grid = Image.new("RGB", (tw * NUM_PAN, th * NUM_TILT))
    for row_idx, row in enumerate(tiles):
        for col_idx, tile in enumerate(row):
            grid.paste(tile, (col_idx * tw, row_idx * th))
    return grid


# ── Tool ───────────────────────────────────────────────────────────────────────


@with_logging
@with_timeout(seconds=C.TIMEOUT_VISUAL_SURVEY)
def visual_survey(question: str | None = None, run_context=None) -> str:
    """
    Sweep the camera across 5 pan angles × 3 tilt levels (UP/LEVEL/DOWN),
    assemble the 15 frames into a labelled 5×3 tiled collage, then send to
    Gemini Vision for structured spatial analysis.

    Returns JSON with:
      scene      — 4-6 sentence first-person description of surroundings
      best_path  — recommended direction
      paths      — per-direction clearance: hard_left, left, front, right, hard_right
                   each with: clear (bool), clearance (blocked/near/medium/far),
                   obstacle (str|null), confidence (0-1)

    Use this for full spatial awareness — replaces multiple look_around +
    pan_tilt calls with a single vision inference.
    """
    hw = get_hw()
    if hw is None:
        return '{"status": "error", "message": "hardware not available"}'
    if hw.camera is None:
        return '{"status": "error", "message": "camera not available"}'
    if hw.pan_tilt is None:
        return '{"status": "error", "message": "pan_tilt not available"}'

    # tiles[tilt_row][pan_col] = annotated PIL tile
    tiles: list[list[Image.Image | None]] = [
        [None] * NUM_PAN for _ in range(NUM_TILT)
    ]

    try:
        for tilt_row, (tilt_deg, tilt_label) in enumerate(_TILT):
            hw.pan_tilt.tilt_snap(tilt_deg, settle_s=C.SURVEY_SETTLE_TILT_S)

            pan_order = _PAN if tilt_row % 2 == 0 else list(reversed(_PAN))

            for scan_idx, (pan_deg, pan_label) in enumerate(pan_order):
                pan_col = scan_idx if tilt_row % 2 == 0 else (NUM_PAN - 1 - scan_idx)
                hw.pan_tilt.pan_snap(pan_deg, settle_s=C.SURVEY_SETTLE_PAN_S)
                time.sleep(C.SURVEY_CAPTURE_SETTLE_S)

                frame = hw.camera.get_frame()
                if frame is None:
                    return '{"status": "error", "message": "camera returned no frame"}'

                pos = _Pos(pan_deg, pan_label, tilt_deg, tilt_label)
                tiles[tilt_row][pan_col] = _annotate_tile(_bgr_to_pil(frame), pos)

    finally:
        try:
            hw.pan_tilt.center()
        except Exception:
            pass

    for row in tiles:
        if any(t is None for t in row):
            return '{"status": "error", "message": "incomplete sweep — missing frames"}'

    collage = _build_grid(tiles)  # type: ignore[arg-type]

    buf = io.BytesIO()
    collage.save(buf, format="JPEG", quality=C.JPEG_QUALITY)

    api_key = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
    client = google_genai.Client(api_key=api_key)
    image_part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")

    try:
        response = client.models.generate_content(
            model=C.GEMINI_VISION_MODEL,
            contents=[image_part, _build_prompt(question)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SurveyResult,
            ),
        )
    except Exception as exc:
        return f'{{"status": "error", "message": "Gemini Vision failed: {exc}"}}'

    raw = (response.text or "").strip()
    if not raw:
        return '{"status": "error", "message": "Gemini returned empty response"}'

    try:
        result = SurveyResult.model_validate_json(raw)
        if result.target_seen and result.target_direction and question:
            get_target_tracker().record(question, result.target_direction, result.target_confidence)
        return result.model_dump_json()
    except Exception:
        # Gemini occasionally returns valid prose instead of JSON — surface it as-is
        return json.dumps({"status": "ok", "scene": raw, "paths": {}, "best_path": ""})
