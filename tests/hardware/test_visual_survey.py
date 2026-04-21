#!/usr/bin/env python3
"""
Hardware test for visual_survey — runs the full sweep, saves the 5×3 tiled
collage to project root, then calls Gemini Vision.

Run on Pi:
    uv run python tests/hardware/test_visual_survey.py

Output:
    /home/rambabu/rambabu_rc/visual_survey_collage.jpg
"""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

import RPi.GPIO as GPIO

from lib.pan_tilt import PanTilt
from lib.camera import Camera

from agno_ai import constants as C
from agno_ai.tools.perception.visual_survey import (
    _Pos,
    _annotate_tile,
    _bgr_to_pil,
    _build_grid,
    _build_prompt,
    _PAN,
    _TILT,
    _TILT_UP_ROW,
    _TILT_LEVEL_ROW,
    _TILT_DOWN_ROW,
    NUM_PAN,
    NUM_TILT,
)
from PIL import Image

COLLAGE_PATH = Path("/home/rambabu/rambabu_rc/visual_survey_collage.jpg")

# ── Hardware init ──────────────────────────────────────────────────────────────

GPIO.setmode(GPIO.BCM)
pan_tilt = PanTilt()
camera = Camera()
camera.start()
print("Camera warming up …")
time.sleep(1.5)

# ── Sweep ──────────────────────────────────────────────────────────────────────

print(f"\nSweeping {NUM_PAN} pan × {NUM_TILT} tilt = {NUM_PAN * NUM_TILT} captures  (snake)")
print(f"  Pan    : {[deg for deg, _ in _PAN]}")
print(f"  Tilt   : {[deg for deg, _ in _TILT]}")
print(f"  Settle : snap={C.SURVEY_SETTLE_PAN_S}s pan, {C.SURVEY_SETTLE_TILT_S}s tilt")
print(f"  Capture: +{C.SURVEY_CAPTURE_SETTLE_S}s vibration settle before each frame\n")

# tiles[tilt_row][pan_col] = annotated PIL tile
tiles: list[list] = [[None] * NUM_PAN for _ in range(NUM_TILT)]

_sweep_start = time.perf_counter()

for tilt_row, (tilt_deg, tilt_label) in enumerate(_TILT):
    pan_tilt.tilt_snap(tilt_deg, settle_s=C.SURVEY_SETTLE_TILT_S)

    pan_order = _PAN if tilt_row % 2 == 0 else list(reversed(_PAN))

    for scan_idx, (pan_deg, pan_label) in enumerate(pan_order):
        pan_col = scan_idx if tilt_row % 2 == 0 else (NUM_PAN - 1 - scan_idx)
        pan_tilt.pan_snap(pan_deg, settle_s=C.SURVEY_SETTLE_PAN_S)
        time.sleep(C.SURVEY_CAPTURE_SETTLE_S)

        frame = camera.get_frame()
        if frame is None:
            print(f"  ERROR: no frame at pan={pan_deg}° tilt={tilt_deg}°")
            continue

        pos = _Pos(pan_deg, pan_label, tilt_deg, tilt_label)
        tiles[tilt_row][pan_col] = _annotate_tile(_bgr_to_pil(frame), pos)
        arrow = "→" if tilt_row % 2 == 0 else "←"
        print(f"  {arrow} [{pan_label:10s} / {tilt_label:5s}]  pan={pan_deg:3d}°  tilt={tilt_deg:3d}°  shape={frame.shape}")

pan_tilt.center()
_sweep_elapsed = time.perf_counter() - _sweep_start
print(f"\nSweep complete in {_sweep_elapsed:.2f}s  ({_sweep_elapsed / (NUM_PAN * NUM_TILT):.2f}s/frame)")

# ── Build collage ──────────────────────────────────────────────────────────────

collage = _build_grid(tiles)
collage.save(COLLAGE_PATH, format="JPEG", quality=C.JPEG_QUALITY)
size_kb = COLLAGE_PATH.stat().st_size / 1024
print(f"Collage saved → {COLLAGE_PATH}  ({collage.size[0]}×{collage.size[1]}px, {size_kb:.1f} KB)")

# ── Gemini Vision ──────────────────────────────────────────────────────────────

_vision_start = time.perf_counter()
print("\nSending to Gemini Vision …")

buf = io.BytesIO()
collage.save(buf, format="JPEG", quality=C.JPEG_QUALITY)

from google import genai as google_genai
from google.genai import types

api_key = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
client = google_genai.Client(api_key=api_key)
image_part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
response = client.models.generate_content(
    model=C.GEMINI_VISION_MODEL,
    contents=[image_part, _build_prompt(None)],
)
_vision_elapsed = time.perf_counter() - _vision_start

print("\n" + "─" * 60)
print("Gemini Vision response:")
print("─" * 60)
print((response.text or "").strip())
print("─" * 60)
print(f"\nTiming breakdown:")
print(f"  Sweep (servo + capture) : {_sweep_elapsed:.2f}s")
print(f"  Gemini Vision           : {_vision_elapsed:.2f}s")
print(f"  Total                   : {_sweep_elapsed + _vision_elapsed:.2f}s")

# ── Cleanup ────────────────────────────────────────────────────────────────────

camera.stop()
GPIO.cleanup()
