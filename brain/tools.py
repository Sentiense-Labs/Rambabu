"""
Tool registry for Rambabu's brain.

Each tool is a thin shell around an existing one-shot brain/*.py script
(or, in the case of `remember`, a direct write to the memory file). The
schemas use Ollama's OpenAI-compatible function-calling format.

Design notes:
- Subprocess-based: zero refactor of existing brain scripts, robust
  isolation, hardware cleanup guaranteed by the child process.
- Each tool has its own timeout based on expected hardware cost.
- Result format is plain text: a one-line status header followed by
  the child's stdout. Small models follow this much more reliably than
  nested JSON.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
BRAIN_DIR: Path = PROJECT_ROOT / "brain"
PYTHON_BIN: str = sys.executable  # use the same interpreter as brain.py

# Per-tool timeouts (seconds). Generous on top of expected hardware cost.
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


# ---------------------------------------------------------------------------
# Tool schemas (Ollama / OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "distance",
            "description": (
                "Read the forward ultrasonic distance sensor (HC-SR04). "
                "Returns distance in centimeters and a zone label "
                "(critical/close/medium/clear). Takes ~3 seconds. "
                "Call this before any forward, left, or right move."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pan_tilt",
            "description": (
                "Aim the camera by panning left/right or tilting up/down. "
                "Use this BEFORE look_around to scout flanks. "
                "Always call action='center' when finished scouting."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "pan_left",
                            "pan_right",
                            "tilt_up",
                            "tilt_down",
                            "center",
                            "angles",
                        ],
                        "description": "Which servo motion to perform",
                    },
                    "degrees": {
                        "type": "integer",
                        "description": (
                            "How many degrees to move (default 40 — use "
                            "40-55° for real scouts, smaller only for fine "
                            "aim). Max 55 for pan, 65 for tilt. Ignored for "
                            "'center' and 'angles'."
                        ),
                        "minimum": 1,
                        "maximum": 65,
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look_around",
            "description": (
                "Capture a frame from the camera and describe what you see. "
                "Pass an optional question to ask about the scene. "
                "Takes ~6 seconds. The vision model is Gemini Flash, not you, "
                "so phrase the question clearly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "Optional question about the scene, e.g. "
                            "'is the path clear?' or 'count the chairs'. "
                            "Omit for a general 2-3 sentence scene description."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": (
                "Drive the rover briefly. Forward/left/right are speed-safety-"
                "checked and will refuse if forward distance is below 50 cm. "
                "'back' has NO rear sensor — only use it when you are certain "
                "the space behind you is clear. 'stop' is always safe."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": [
                            "forward", "back", "left", "right", "stop",
                            "back_left", "back_right",
                        ],
                        "description": (
                            "back_left/back_right reverse with steering bias. "
                            "Reminder: in reverse, left steer swings the FRONT "
                            "right and the rear left (and vice-versa)."
                        ),
                    },
                    "seconds": {
                        "type": "number",
                        "description": (
                            "Duration in seconds (0.3-9.0). "
                            "Prefer 0.3-0.8 second steps. "
                            "Reverse-family directions are hard-capped at 0.5s. "
                            "Ignored for 'stop'."
                        ),
                        "minimum": 0.1,
                        "maximum": 9.0,
                    },
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_moving",
            "description": (
                "Begin continuous movement in a direction. The motor runs in "
                "the background until you call stop_moving or SonarGuard "
                "intervenes (close/critical zone). Returns immediately. Use "
                "this for open-path navigation instead of move(). The brain "
                "will be woken on zone changes, obstacles, and periodic "
                "goal-checks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["forward", "back", "left", "right"],
                    },
                    "speed": {
                        "type": "integer",
                        "description": "Motor duty cycle 0-100 (default 80).",
                        "minimum": 0,
                        "maximum": 100,
                    },
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reverse_steer",
            "description": (
                "Reverse while steering to reposition. Combines back movement "
                "with left or right steer. Remember: during reverse, left "
                "steer swings your FRONT right and rear left — opposite of "
                "forward steering. Hard capped at 0.5 seconds for safety "
                "(no rear sensor)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steer_direction": {
                        "type": "string",
                        "enum": ["left", "right"],
                    },
                    "seconds": {
                        "type": "number",
                        "description": "Duration in seconds (max 0.5).",
                        "minimum": 0.05,
                        "maximum": 0.5,
                    },
                },
                "required": ["steer_direction", "seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "three_point_turn",
            "description": (
                "Execute a three-point turn to reverse direction in limited "
                "space. Sequences a forward-arc, a reverse-arc, then a "
                "forward straighten. Always look_around first to confirm "
                "you have room."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "preferred_side": {
                        "type": "string",
                        "enum": ["left", "right"],
                        "description": (
                            "Which way to arc on the first forward step."
                        ),
                    },
                },
                "required": ["preferred_side"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "align_to_path",
            "description": (
                "Make a small steering correction to re-center on a path. "
                "Use when you can see you have drifted from the line you "
                "intended to follow."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "drift_direction": {
                        "type": "string",
                        "enum": ["left", "right"],
                        "description": "Which way you have drifted.",
                    },
                    "correction_strength": {
                        "type": "string",
                        "enum": ["light", "medium", "strong"],
                        "description": "light=0.2s, medium=0.4s, strong=0.6s.",
                    },
                },
                "required": ["drift_direction", "correction_strength"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_moving",
            "description": (
                "Stop all motor movement immediately. Use when replanning, "
                "at goal completion, or when an obstacle requires assessment. "
                "Always safe to call."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "say",
            "description": (
                "Speak text aloud through the Bluetooth speaker. "
                "Call this BEFORE and AFTER every action — narration is "
                "mandatory. Keep it to 1-2 short conversational sentences "
                "in first person, present tense. No markdown, no brackets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The words to speak (1-2 sentences)",
                    }
                },
                "required": ["text"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolResult:
    """Outcome of a single tool invocation, frozen to enforce immutability."""

    name: str
    ok: bool
    output: str
    elapsed_s: float

    def to_text(self) -> str:
        """Render to a flat string for the model to consume."""
        status = "ok" if self.ok else "error"
        header = f"[{self.name}] status={status} elapsed={self.elapsed_s:.2f}s"
        body = self.output.strip() or "(no output)"
        return f"{header}\n{body}"


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------


def _run_script(
    name: str, argv: list[str], timeout: float
) -> ToolResult:
    """Run a brain/*.py script as a subprocess and capture its output."""
    cmd = [PYTHON_BIN, *argv]
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            name=name,
            ok=False,
            output=f"timed out after {timeout:.0f}s",
            elapsed_s=time.time() - started,
        )
    except FileNotFoundError as exc:
        return ToolResult(
            name=name,
            ok=False,
            output=f"script not found: {exc}",
            elapsed_s=time.time() - started,
        )

    elapsed = time.time() - started
    output = proc.stdout
    if proc.returncode != 0:
        # Include stderr only on failure to keep success output clean.
        stderr_tail = (proc.stderr or "").strip().splitlines()[-5:]
        if stderr_tail:
            output = f"{output}\n--stderr--\n" + "\n".join(stderr_tail)
    return ToolResult(
        name=name,
        ok=(proc.returncode == 0),
        output=output,
        elapsed_s=elapsed,
    )


# ---------------------------------------------------------------------------
# Per-tool argument builders (each returns a list of CLI args)
# ---------------------------------------------------------------------------


def _build_distance(_args: dict[str, Any]) -> list[str]:
    return [str(BRAIN_DIR / "distance.py")]


def _build_pan_tilt(args: dict[str, Any]) -> list[str]:
    action = args.get("action")
    if action not in {
        "pan_left", "pan_right", "tilt_up", "tilt_down", "center", "angles",
    }:
        raise ValueError(f"invalid pan_tilt action: {action!r}")

    script = str(BRAIN_DIR / "pan_tilt.py")
    if action in {"center", "angles"}:
        return [script, action]

    verb, direction = action.split("_", 1)  # pan_left -> ("pan", "left")
    degrees = int(args.get("degrees", 40))
    return [script, verb, direction, str(degrees)]


def _build_look_around(args: dict[str, Any]) -> list[str]:
    cmd = [str(BRAIN_DIR / "look_around.py"), "--print-only"]
    question = (args.get("question") or "").strip()
    if question:
        cmd.extend(["-i", question])
    return cmd


def _build_move(args: dict[str, Any]) -> list[str]:
    direction = args.get("direction")
    if direction not in {
        "forward", "back", "left", "right", "stop",
        "back_left", "back_right",
    }:
        raise ValueError(f"invalid move direction: {direction!r}")
    cmd = [str(BRAIN_DIR / "move.py"), direction]
    if direction != "stop":
        seconds = float(args.get("seconds", 0.5))
        cmd.append(f"{seconds:.2f}")
    return cmd


def _build_reverse_steer(args: dict[str, Any]) -> list[str]:
    steer = args.get("steer_direction")
    if steer not in {"left", "right"}:
        raise ValueError(f"invalid steer_direction: {steer!r}")
    seconds = max(0.05, min(float(args.get("seconds", 0.4)), 0.5))
    direction = "back_left" if steer == "left" else "back_right"
    return [str(BRAIN_DIR / "move.py"), direction, f"{seconds:.2f}"]


def _build_three_point_turn(args: dict[str, Any]) -> list[str]:
    side = args.get("preferred_side")
    if side not in {"left", "right"}:
        raise ValueError(f"invalid preferred_side: {side!r}")
    # No standalone CLI for compound maneuvers — fallback degrades to a
    # single short forward arc, which is the best a subprocess can do.
    return [str(BRAIN_DIR / "move.py"), side, "0.8"]


def _build_align_to_path(args: dict[str, Any]) -> list[str]:
    drift = args.get("drift_direction")
    strength = args.get("correction_strength", "light")
    if drift not in {"left", "right"}:
        raise ValueError(f"invalid drift_direction: {drift!r}")
    seconds_map = {"light": 0.2, "medium": 0.4, "strong": 0.6}
    seconds = seconds_map.get(strength)
    if seconds is None:
        raise ValueError(f"invalid correction_strength: {strength!r}")
    correction_side = "right" if drift == "left" else "left"
    return [str(BRAIN_DIR / "move.py"), correction_side, f"{seconds:.2f}"]


def _build_start_moving(args: dict[str, Any]) -> list[str]:
    direction = args.get("direction")
    if direction not in {"forward", "back", "left", "right"}:
        raise ValueError(f"invalid start_moving direction: {direction!r}")
    seconds = max(0.5, min(float(args.get("seconds", 1.0)), 2.0))
    # Subprocess fallback degrades to a short discrete move via brain/move.py.
    return [str(BRAIN_DIR / "move.py"), direction, f"{seconds:.2f}"]


def _build_stop_moving(_args: dict[str, Any]) -> list[str]:
    return [str(BRAIN_DIR / "move.py"), "stop"]


def _build_say(args: dict[str, Any]) -> list[str]:
    text = (args.get("text") or "").strip()
    if not text:
        raise ValueError("say requires non-empty 'text'")
    return [str(BRAIN_DIR / "say.py"), text]


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Dispatch:
    builder: Callable[[dict[str, Any]], list[str]]
    timeout: float


_DISPATCH: dict[str, _Dispatch] = {
    "distance": _Dispatch(_build_distance, TIMEOUT_DISTANCE),
    "pan_tilt": _Dispatch(_build_pan_tilt, TIMEOUT_PAN_TILT),
    "look_around": _Dispatch(_build_look_around, TIMEOUT_LOOK_AROUND),
    "move": _Dispatch(_build_move, TIMEOUT_MOVE),
    "say": _Dispatch(_build_say, TIMEOUT_SAY),
    "start_moving": _Dispatch(_build_start_moving, TIMEOUT_START_MOVING),
    "stop_moving": _Dispatch(_build_stop_moving, TIMEOUT_STOP_MOVING),
    "reverse_steer": _Dispatch(_build_reverse_steer, TIMEOUT_REVERSE_STEER),
    "three_point_turn": _Dispatch(_build_three_point_turn, TIMEOUT_THREE_POINT_TURN),
    "align_to_path": _Dispatch(_build_align_to_path, TIMEOUT_ALIGN_TO_PATH),
}


def execute_tool(
    name: str,
    args: dict[str, Any] | None,
    hw: Any = None,  # HardwareContext | None — avoids circular import
) -> ToolResult:
    """Validate, dispatch, and run a single tool call.

    If ``hw`` is a HardwareContext with the required peripheral, the tool
    runs directly (no subprocess). Otherwise falls back to subprocess mode.
    """
    args = args or {}

    # Direct mode — use live hardware objects when available.
    if hw is not None:
        result = _try_direct(name, args, hw)
        if result is not None:
            return result

    # Subprocess fallback.
    entry = _DISPATCH.get(name)
    if entry is None:
        return ToolResult(
            name=name,
            ok=False,
            output=f"unknown tool: {name!r}",
            elapsed_s=0.0,
        )

    try:
        argv = entry.builder(args)
    except (ValueError, TypeError) as exc:
        return ToolResult(
            name=name,
            ok=False,
            output=f"invalid arguments: {exc}",
            elapsed_s=0.0,
        )

    return _run_script(name, argv, entry.timeout)


def _try_direct(name: str, args: dict[str, Any], hw: Any) -> ToolResult | None:
    """Attempt direct (no-subprocess) execution. Returns None to signal fallback."""
    # Import lazily to avoid circular dependency at module load time.
    from brain.hardware_tools import (
        execute_distance,
        execute_look_around,
        execute_move,
        execute_pan_tilt,
        execute_say,
        execute_start_moving,
        execute_stop_moving,
    )

    if name == "distance" and hw.ultrasonic is not None:
        return execute_distance(hw, args)
    if name == "move" and hw.motor is not None:
        return execute_move(hw, args)
    if name == "pan_tilt" and hw.pan_tilt is not None:
        return execute_pan_tilt(hw, args)
    if name == "look_around" and hw.camera is not None:
        return execute_look_around(hw, args)
    if name == "say" and hw.speaker is not None:
        return execute_say(hw, args)
    if name == "start_moving" and hw.movement_manager is not None:
        return execute_start_moving(hw, args)
    if name == "stop_moving" and hw.movement_manager is not None:
        return execute_stop_moving(hw, args)
    if name in {"reverse_steer", "three_point_turn", "align_to_path"} and hw.motor is not None:
        from brain.hardware_tools import execute_maneuver
        return execute_maneuver(name, hw, args)
    return None  # peripheral missing — fall back to subprocess


# ---------------------------------------------------------------------------
# Prompt-driven tool call parser (for models without native tool support)
# ---------------------------------------------------------------------------

# Match a fenced code block whose content is a JSON object. The optional
# language tag accepts ```json, ```JSON, or no tag at all. DOTALL lets
# the body span newlines so multi-line argument strings still match.
_FENCED_JSON_RE: re.Pattern[str] = re.compile(
    r"```(?:json|JSON)?\s*(\{.*?\})\s*```",
    re.DOTALL,
)


def parse_tool_calls_from_text(text: str) -> list[dict[str, Any]]:
    """Extract tool calls from a model response that uses fenced JSON blocks.

    Each call is normalized to ``{"name": str, "arguments": dict}``. Blocks
    that fail to parse, lack a string ``name``, or are not objects are
    silently skipped — the loop will treat the response as a final answer
    if no valid calls are found.
    """
    calls: list[dict[str, Any]] = []
    if not text:
        return calls

    for match in _FENCED_JSON_RE.finditer(text):
        snippet = match.group(1).strip()
        try:
            obj = json.loads(snippet)
        except json.JSONDecodeError:
            continue

        if not isinstance(obj, dict):
            continue

        name = obj.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        # Accept both "arguments" and "parameters" for robustness — different
        # documentation conventions use different field names.
        raw_args = obj.get("arguments")
        if raw_args is None:
            raw_args = obj.get("parameters")
        if not isinstance(raw_args, dict):
            raw_args = {}

        calls.append({"name": name.strip(), "arguments": raw_args})

    return calls


# ---------------------------------------------------------------------------
# Gemini tool schema conversion
# ---------------------------------------------------------------------------

# Gemini's Schema is a strict subset of JSON Schema / OpenAPI. These fields
# are valid in OpenAI tool schemas but rejected by the Gemini proto. They
# are validation hints only — stripping them does not change tool behavior.
_GEMINI_UNSUPPORTED_SCHEMA_KEYS: frozenset[str] = frozenset({
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "additionalProperties",
    "default",
})


def _scrub_for_gemini(node: Any) -> Any:
    """Recursively strip schema fields Gemini's proto cannot parse.

    Returns a new structure — never mutates the input. Lists and dicts are
    rebuilt; primitives pass through unchanged.
    """
    if isinstance(node, dict):
        return {
            key: _scrub_for_gemini(value)
            for key, value in node.items()
            if key not in _GEMINI_UNSUPPORTED_SCHEMA_KEYS
        }
    if isinstance(node, list):
        return [_scrub_for_gemini(item) for item in node]
    return node


def to_gemini_tools() -> list[dict[str, Any]]:
    """Convert TOOL_SCHEMAS (Ollama / OpenAI format) to Gemini function declarations.

    Gemini's google.generativeai SDK accepts a list of tool entries, each
    containing one or more ``function_declarations``. The inner declaration
    shape (``name``, ``description``, ``parameters``) is OpenAI-style, but
    Gemini's Schema rejects validation-hint fields like ``minimum``, so we
    scrub them out before passing the tools across.
    """
    declarations = [_scrub_for_gemini(tool["function"]) for tool in TOOL_SCHEMAS]
    return [{"function_declarations": declarations}]
