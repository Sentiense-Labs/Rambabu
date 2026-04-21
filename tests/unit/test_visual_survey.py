"""
Unit tests for visual_survey tool.

Tests image helpers, grid assembly, and sweep mechanics
without hardware or Gemini API.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from agno_ai import constants as C
import json

from agno_ai.tools.perception.visual_survey import (
    _Pos,
    _annotate_tile,
    _bgr_to_pil,
    _build_grid,
    _build_prompt,
    _PATH_KEYS,
    _PAN,
    _TILT,
    NUM_PAN,
    NUM_TILT,
    PathClearance,
    SurveyPaths,
    SurveyResult,
    _TILT_UP_ROW,
    _TILT_LEVEL_ROW,
    _TILT_DOWN_ROW,
    _TARGET_DETECTION_GUIDE,
)


def _make_rgb_image(w: int = 320, h: int = 240, color=(100, 150, 200)) -> Image.Image:
    arr = np.full((h, w, 3), color, dtype=np.uint8)
    return Image.fromarray(arr, "RGB")


def _make_bgr_frame(w: int = 320, h: int = 240, color=(200, 150, 100)) -> np.ndarray:
    return np.full((h, w, 3), color, dtype=np.uint8)


def _front_level_pos() -> _Pos:
    return _Pos(pan_deg=110, pan_label="FRONT", tilt_deg=80, tilt_label="LEVEL")


class TestAnnotateTile:
    def test_adds_label_height(self):
        img = _make_rgb_image(320, 240)
        result = _annotate_tile(img, _front_level_pos())
        assert result.size == (320, 240 + C.SURVEY_LABEL_H)

    def test_label_banner_is_dark(self):
        img = _make_rgb_image(320, 240, color=(200, 200, 200))
        result = _annotate_tile(img, _front_level_pos())
        r, g, b = result.getpixel((0, 0))
        assert r < 50 and g < 50 and b < 50

    def test_original_image_preserved_below_banner(self):
        img = _make_rgb_image(320, 240, color=(200, 100, 50))
        result = _annotate_tile(img, _front_level_pos())
        r, g, b = result.getpixel((160, C.SURVEY_LABEL_H + 5))
        assert r > 150


class TestBuildGrid:
    def _make_tile(self) -> Image.Image:
        return _make_rgb_image(C.SURVEY_TILE_W, C.SURVEY_TILE_H + C.SURVEY_LABEL_H)

    def test_grid_width(self):
        tiles = [[self._make_tile() for _ in range(NUM_PAN)] for _ in range(NUM_TILT)]
        grid = _build_grid(tiles)
        assert grid.size[0] == C.SURVEY_TILE_W * NUM_PAN

    def test_grid_height(self):
        tiles = [[self._make_tile() for _ in range(NUM_PAN)] for _ in range(NUM_TILT)]
        grid = _build_grid(tiles)
        assert grid.size[1] == (C.SURVEY_TILE_H + C.SURVEY_LABEL_H) * NUM_TILT

    def test_grid_is_pil_image(self):
        tiles = [[self._make_tile() for _ in range(NUM_PAN)] for _ in range(NUM_TILT)]
        assert isinstance(_build_grid(tiles), Image.Image)


class TestBuildPrompt:
    def test_default_prompt_contains_all_pan_labels(self):
        prompt = _build_prompt(None)
        for _, label in _PAN:
            assert label in prompt

    def test_custom_question_embedded(self):
        prompt = _build_prompt("is the doorway clear?")
        assert "is the doorway clear?" in prompt

    def test_prompt_mentions_grid(self):
        prompt = _build_prompt(None)
        assert "grid" in prompt.lower()


class TestSweepConstants:
    def test_five_pan_positions(self):
        assert NUM_PAN == 5

    def test_three_tilt_positions(self):
        assert NUM_TILT == 3

    def test_tilt_labels_are_up_level_down(self):
        labels = [label for _, label in _TILT]
        assert labels == ["UP", "LEVEL", "DOWN"]

    def test_up_tilt_is_not_full_ceiling(self):
        up_deg = C.SURVEY_TILT_ANGLES[_TILT_UP_ROW]
        assert up_deg > 30, "UP tilt should not point straight at ceiling"
        assert up_deg < C.SURVEY_TILT_ANGLES[_TILT_LEVEL_ROW], "UP must be above LEVEL"

    def test_pan_labels_ordered_left_to_right(self):
        labels = [label for _, label in _PAN]
        assert labels[0] == "HARD LEFT"
        assert labels[-1] == "HARD RIGHT"
        assert labels[NUM_PAN // 2] == "FRONT"

    def test_up_row_index(self):
        assert _TILT[_TILT_UP_ROW][1] == "UP"

    def test_level_row_index(self):
        assert _TILT[_TILT_LEVEL_ROW][1] == "LEVEL"

    def test_down_row_index(self):
        assert _TILT[_TILT_DOWN_ROW][1] == "DOWN"


def _make_clearance(level: str = "far", clear: bool = True) -> dict:
    return {"clear": clear, "clearance": level, "obstacle": None, "confidence": 0.9}


def _make_paths_dict(level: str = "far") -> dict:
    return {k: _make_clearance(level) for k in _PATH_KEYS}


class TestSurveySchema:
    def test_path_clearance_valid(self):
        pc = PathClearance(clear=True, clearance="far", obstacle=None, confidence=0.9)
        assert pc.clear is True
        assert pc.clearance == "far"

    def test_path_clearance_blocked_has_obstacle(self):
        pc = PathClearance(clear=False, clearance="blocked", obstacle="wall", confidence=1.0)
        assert pc.obstacle == "wall"

    def test_clear_false_when_obstacle_present(self):
        pc = PathClearance(clear=False, clearance="near", obstacle="shelf", confidence=0.9)
        assert pc.clear is False
        assert pc.obstacle == "shelf"

    def test_survey_result_roundtrip(self):
        raw = json.dumps({"scene": "clear room", "best_path": "front", "paths": _make_paths_dict()})
        result = SurveyResult.model_validate_json(raw)
        assert result.best_path == "front"
        assert result.paths.front.clearance == "far"

    def test_survey_result_serializes_to_json(self):
        pc = PathClearance(**_make_clearance("near"))
        sr = SurveyResult(
            scene="A wall ahead.",
            best_path="left",
            paths=SurveyPaths(hard_left=pc, left=pc, front=pc, right=pc, hard_right=pc),
        )
        out = json.loads(sr.model_dump_json())
        assert out["paths"]["front"]["clearance"] == "near"

    def test_survey_paths_has_all_five_directions(self):
        pc = PathClearance(**_make_clearance())
        sp = SurveyPaths(hard_left=pc, left=pc, front=pc, right=pc, hard_right=pc)
        dumped = json.loads(sp.model_dump_json())
        assert set(dumped.keys()) == set(_PATH_KEYS)

    def test_target_seen_default_false(self):
        raw = json.dumps({"scene": "clear", "best_path": "front", "paths": _make_paths_dict()})
        result = SurveyResult.model_validate_json(raw)
        assert result.target_seen is False
        assert result.target_direction is None
        assert result.target_confidence == 0.0

    def test_target_direction_optional(self):
        raw = json.dumps({
            "scene": "clear", "best_path": "front",
            "paths": _make_paths_dict(),
            "target_seen": False,
            "target_direction": None,
            "target_confidence": 0.0,
        })
        result = SurveyResult.model_validate_json(raw)
        assert result.target_direction is None

    def test_target_seen_with_direction(self):
        raw = json.dumps({
            "scene": "I see a fridge ahead.",
            "best_path": "right",
            "paths": _make_paths_dict(),
            "target_seen": True,
            "target_direction": "front",
            "target_confidence": 0.9,
        })
        result = SurveyResult.model_validate_json(raw)
        assert result.target_seen is True
        assert result.target_direction == "front"
        assert result.target_confidence == pytest.approx(0.9)

    def test_prompt_includes_target_detection_for_question(self):
        prompt = _build_prompt("Where is the fridge?")
        assert "TARGET DETECTION" in prompt

    def test_prompt_omits_target_detection_for_general(self):
        prompt = _build_prompt(None)
        assert "TARGET DETECTION" not in prompt


class TestVisualSurveyTool:
    def test_returns_error_when_no_hardware(self):
        with patch("agno_ai.tools.perception.visual_survey.get_hw", return_value=None):
            from agno_ai.tools.perception.visual_survey import visual_survey
            result = visual_survey()
        assert "error" in result

    def test_returns_error_when_no_camera(self):
        hw = MagicMock()
        hw.camera = None
        with patch("agno_ai.tools.perception.visual_survey.get_hw", return_value=hw):
            from agno_ai.tools.perception.visual_survey import visual_survey
            result = visual_survey()
        assert "camera not available" in result

    def test_returns_error_when_no_pan_tilt(self):
        hw = MagicMock()
        hw.camera = MagicMock()
        hw.pan_tilt = None
        with patch("agno_ai.tools.perception.visual_survey.get_hw", return_value=hw):
            from agno_ai.tools.perception.visual_survey import visual_survey
            result = visual_survey()
        assert "pan_tilt not available" in result

    def test_centers_after_frame_error(self):
        hw = MagicMock()
        hw.camera.get_frame.return_value = None
        with patch("agno_ai.tools.perception.visual_survey.get_hw", return_value=hw):
            from agno_ai.tools.perception.visual_survey import visual_survey
            visual_survey()
        hw.pan_tilt.center.assert_called_once()

    def _make_survey_json(self) -> str:
        return json.dumps({
            "scene": "I see a clear room ahead.",
            "best_path": "front",
            "paths": _make_paths_dict("far"),
        })

    def test_snap_call_counts(self):
        """3 tilt_snaps (one per row) + 15 pan_snaps (5 per row × 3 rows)."""
        hw = MagicMock()
        hw.camera.get_frame.return_value = np.zeros((240, 320, 3), dtype=np.uint8)

        mock_response = MagicMock()
        mock_response.text = self._make_survey_json()

        tile = _make_rgb_image(C.SURVEY_TILE_W, C.SURVEY_TILE_H + C.SURVEY_LABEL_H)

        with (
            patch("agno_ai.tools.perception.visual_survey.get_hw", return_value=hw),
            patch("agno_ai.tools.perception.visual_survey.time.sleep"),
            patch("agno_ai.tools.perception.visual_survey._bgr_to_pil", return_value=_make_rgb_image()),
            patch("agno_ai.tools.perception.visual_survey._annotate_tile", return_value=tile),
            patch("agno_ai.tools.perception.visual_survey.google_genai.Client") as mock_client,
        ):
            mock_client.return_value.models.generate_content.return_value = mock_response

            from agno_ai.tools.perception.visual_survey import visual_survey
            result = visual_survey()

        assert hw.pan_tilt.tilt_snap.call_count == NUM_TILT       # 3
        assert hw.pan_tilt.pan_snap.call_count == NUM_PAN * NUM_TILT  # 15
        parsed = json.loads(result)
        assert "scene" in parsed
        assert "paths" in parsed
        assert "best_path" in parsed

    def test_result_contains_all_path_keys(self):
        hw = MagicMock()
        hw.camera.get_frame.return_value = np.zeros((240, 320, 3), dtype=np.uint8)

        mock_response = MagicMock()
        mock_response.text = self._make_survey_json()

        tile = _make_rgb_image(C.SURVEY_TILE_W, C.SURVEY_TILE_H + C.SURVEY_LABEL_H)

        with (
            patch("agno_ai.tools.perception.visual_survey.get_hw", return_value=hw),
            patch("agno_ai.tools.perception.visual_survey.time.sleep"),
            patch("agno_ai.tools.perception.visual_survey._bgr_to_pil", return_value=_make_rgb_image()),
            patch("agno_ai.tools.perception.visual_survey._annotate_tile", return_value=tile),
            patch("agno_ai.tools.perception.visual_survey.google_genai.Client") as mock_client,
        ):
            mock_client.return_value.models.generate_content.return_value = mock_response
            from agno_ai.tools.perception.visual_survey import visual_survey
            result = visual_survey()

        parsed = json.loads(result)
        assert set(parsed["paths"].keys()) == set(_PATH_KEYS)
