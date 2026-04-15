#!/usr/bin/env python3
"""
Rambabu's brain — Gemini-powered LLM orchestrator.

Uses the cloud Gemini API (google.generativeai) to drive the rover by
calling the tools registered in brain/tools.py. Each turn, Gemini emits
function calls, we execute them against live hardware or subprocesses,
and feed results back until the model emits a final text-only reply.

After each session, a background Gemini call compresses the conversation
into observations and appends them to brain/memory/observations.md.

Usage:
    uv run python brain/brain.py "scout the room and tell me what you see"
    uv run python brain/brain.py --model gemini-2.5-flash "say hi"

Environment:
    GOOGLE_GENERATIVE_AI_API_KEY  required
"""

from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain.tools import (  # noqa: E402
    ToolResult,
    execute_tool,
    to_gemini_tools,
)
from brain.hardware_tools import HardwareContext  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
SOUL_FILE: Path = PROJECT_ROOT / "brain" / "SOUL.md"
OBSERVATIONS_FILE: Path = PROJECT_ROOT / "brain" / "memory" / "observations.md"

DEFAULT_MODEL: str = "gemini-2.5-flash"
COMPRESS_MODEL: str = "gemini-2.5-flash-lite"
DEFAULT_MAX_ITERATIONS: int = 100
DEFAULT_TEMPERATURE: float = 0.3
GOAL_CHECK_INTERVAL_S: float = 10.0

# Gemini occasionally returns 200 OK with no text and no tool calls — a
# transient model failure. We treat this as "try again" instead of "goal
# complete", up to MAX_EMPTY_RESPONSE_RETRIES per session.
MAX_EMPTY_RESPONSE_RETRIES: int = 3
_EMPTY_RESPONSE_NUDGE: str = (
    "You returned no text and no tool calls. That's not a valid reply. "
    "Re-read the goal and the current state, then call a tool — say(), "
    "look_around(), distance(), start_moving(direction), or stop_moving() "
    "if the goal is genuinely complete. Do not return empty content again."
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("brain")


# ---------------------------------------------------------------------------
# System prompt — SOUL.md + tool-calling addendum + observations
# ---------------------------------------------------------------------------

_TOOL_ADDENDUM: str = """
---

## How you call tools

You do not run shell commands — you emit tool calls. Available tools:

- `say(text)` — speak through the Bluetooth speaker. Use before and after meaningful decisions.
- `look_around(question?)` — capture a frame and describe / answer a question.
- `pan_tilt(action, degrees?)` — aim the camera (`pan_left`/`pan_right`/`tilt_up`/`tilt_down`/`center`/`angles`).
- `distance()` — read the forward sonar (cm + zone). When SonarGuard is running this returns the live cached value.
- `start_moving(direction, speed?)` — begin continuous motion. Returns instantly. Motor runs until you call `stop_moving` or SonarGuard intervenes.
- `stop_moving()` — halt all motion immediately. Always safe.
- `move(direction, seconds?)` — short discrete burst (legacy). Prefer `start_moving` for navigation.

## Event-driven control

After you call `start_moving`, the wheels keep turning while you do nothing.
A background **SonarGuard** watches the sonar at 10 Hz and will stop the motor
on its own if anything gets dangerously close. You will be woken by an
**EVENT** message in one of these forms:

- `EVENT: ZONE_CHANGE zone=clear→medium distance=128cm` — heads-up, decide whether to keep going.
- `EVENT: OBSTACLE zone=close distance=42cm` — motor was auto-stopped. Assess and replan.
- `EVENT: EMERGENCY_STOP distance=18cm` — motor already stopped by guard. Replan or back off.
- `EVENT: GOAL_CHECK elapsed=10.0s estimated_distance=560cm direction=forward` — periodic ping while moving; assess progress.

Reply to events with tool calls (look_around, distance, start_moving, stop_moving, say)
or with plain text. If you only return text and the motor is still moving,
you will be woken again on the next event. Return text and call `stop_moving`
(if not already stopped) when the goal is complete.
"""

_COMPRESS_PROMPT: str = """\
You are a memory compression agent for Rambabu, a small AI-powered RC rover.

Below is a transcript of what Rambabu did during one session. Your job is to \
extract a compact set of observations that will be useful in future sessions.

Include ONLY what is factually new and spatially useful:
- Physical locations visited or discovered
- Objects, furniture, landmarks, or room layouts seen
- Hazards or obstacles encountered
- Outcome of the goal (completed / failed / blocked / partial)

Output format — a compact bullet list (3–8 lines max):
- <fact>
- <fact>
...

If nothing spatially noteworthy was discovered (e.g. Rambabu only spoke a \
greeting, or the session was trivially short), output exactly one line:
(no new observations)

Do NOT repeat the goal. Do NOT include meta-commentary. Be terse and spatial.

TRANSCRIPT:
{transcript}
"""


def load_system_prompt() -> str:
    """Build the full system prompt: SOUL.md + tool addendum + past observations."""
    if not SOUL_FILE.exists():
        raise FileNotFoundError(f"SOUL.md missing at {SOUL_FILE}")
    soul = SOUL_FILE.read_text(encoding="utf-8")

    parts = [soul, _TOOL_ADDENDUM]

    if OBSERVATIONS_FILE.exists():
        observations = OBSERVATIONS_FILE.read_text(encoding="utf-8").strip()
        if observations:
            parts.append(
                "---\n\n## What you have observed in past sessions\n\n" + observations
            )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------


def check_gemini_key() -> None:
    """Fail fast if the Gemini API key is missing."""
    if not os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY"):
        raise RuntimeError(
            "GOOGLE_GENERATIVE_AI_API_KEY is not set. Add it to .env " "and try again."
        )


# ---------------------------------------------------------------------------
# Observational memory compression
# ---------------------------------------------------------------------------


def _compress_session(goal: str, transcript: list[str], model: str) -> None:
    """Summarize a completed session into observations; append to observations.md.

    Called in a background daemon thread after run_gemini_loop() returns so it
    does not delay the result being published back to the caller.
    """
    from google import genai  # type: ignore

    api_key = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
    if not api_key:
        logger.warning("compress_session: no API key — skipping")
        return

    transcript_text = "\n".join(transcript)
    prompt = _COMPRESS_PROMPT.format(transcript=transcript_text)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=COMPRESS_MODEL,
            contents=prompt,
        )
        observations = (response.text or "").strip()
    except Exception as exc:
        logger.warning(f"compress_session: Gemini call failed — {exc}")
        return

    if not observations or observations == "(no new observations)":
        logger.info("compress_session: no new observations to save")
        return

    timestamp = time.strftime("%Y-%m-%d %H:%M")
    entry = f"## [{timestamp}] {goal}\n{observations}\n\n"

    OBSERVATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not OBSERVATIONS_FILE.exists():
        OBSERVATIONS_FILE.write_text(
            "# Rambabu — Session Observations\n\nAutomatically generated after each session. Newest first.\n\n---\n\n",
            encoding="utf-8",
        )

    existing = OBSERVATIONS_FILE.read_text(encoding="utf-8")
    # Insert after the header block (first ---\n\n)
    marker = "---\n\n"
    idx = existing.find(marker)
    insert_at = idx + len(marker) if idx != -1 else len(existing)
    updated = existing[:insert_at] + entry + existing[insert_at:]
    OBSERVATIONS_FILE.write_text(updated, encoding="utf-8")
    logger.info(f"compress_session: saved {len(observations)} chars of observations")


# ---------------------------------------------------------------------------
# Event bus — bridges SonarGuard / MovementManager callbacks into the loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrainEvent:
    """A single asynchronous event that should wake the brain."""

    kind: str  # ZONE_CHANGE | OBSTACLE | EMERGENCY_STOP | GOAL_CHECK
    zone: str | None = None
    distance_cm: float | None = None
    extra: dict[str, Any] | None = None

    def to_user_message(self) -> str:
        if self.kind == "GOAL_CHECK":
            extra = self.extra or {}
            return (
                "EVENT: GOAL_CHECK "
                f"elapsed={extra.get('elapsed_s', 0):.1f}s "
                f"estimated_distance={extra.get('estimated_distance_cm', 0):.0f}cm "
                f"direction={extra.get('direction', 'unknown')}"
            )
        dist = f"{self.distance_cm:.0f}cm" if self.distance_cm is not None else "?"
        if self.kind == "ZONE_CHANGE":
            old = (self.extra or {}).get("old_zone", "?")
            return f"EVENT: ZONE_CHANGE zone={old}→{self.zone} distance={dist}"
        if self.kind == "OBSTACLE":
            return (
                f"EVENT: OBSTACLE zone={self.zone} distance={dist} "
                "(motor auto-stopped — assess and replan)"
            )
        if self.kind == "EMERGENCY_STOP":
            return (
                f"EVENT: EMERGENCY_STOP distance={dist} "
                "(motor already halted by SonarGuard)"
            )
        return f"EVENT: {self.kind}"


def _wire_event_bus(hw: HardwareContext | None) -> queue.Queue[BrainEvent] | None:
    """Hook MovementManager callbacks to a per-session queue."""
    if hw is None or hw.movement_manager is None:
        return None

    bus: queue.Queue[BrainEvent] = queue.Queue()

    def on_zone_change(old_zone: str, new_zone: str, distance: float) -> None:
        # MovementManager has already auto-stopped on close while moving fwd.
        kind = "OBSTACLE" if new_zone == "close" else "ZONE_CHANGE"
        bus.put(
            BrainEvent(
                kind=kind,
                zone=new_zone,
                distance_cm=distance,
                extra={"old_zone": old_zone},
            )
        )

    def on_emergency_stop(distance: float) -> None:
        bus.put(
            BrainEvent(
                kind="EMERGENCY_STOP",
                zone="critical",
                distance_cm=distance,
            )
        )

    hw.movement_manager._on_zone_change = on_zone_change  # noqa: SLF001
    hw.movement_manager._on_emergency_stop = on_emergency_stop  # noqa: SLF001
    return bus


def _drain_event_bus(bus: queue.Queue[BrainEvent]) -> None:
    while True:
        try:
            bus.get_nowait()
        except queue.Empty:
            return


def _drain_pending_events(bus: queue.Queue[BrainEvent]) -> list[BrainEvent]:
    """Pull every queued event without blocking. Returns them in arrival order."""
    drained: list[BrainEvent] = []
    while True:
        try:
            drained.append(bus.get_nowait())
        except queue.Empty:
            return drained


def _build_safety_halt_nudge(
    info: dict[str, Any],
    pending: list[BrainEvent],
    last_model_text: str,
) -> str:
    """Compose a blunt user message that forces a tool call after auto-stop."""
    reason = info.get("reason", "SAFETY_HALT")
    distance = info.get("distance_cm")
    dist_str = f"{distance:.0f}cm" if isinstance(distance, (int, float)) else "?"
    pending_summary = (
        " | ".join(ev.to_user_message() for ev in pending)
        if pending
        else "(no other events)"
    )
    last = last_model_text.strip() if last_model_text else "(no text)"
    return (
        f"EVENT: SAFETY_HALT reason={reason} distance={dist_str}\n"
        f"The motor is STOPPED. SonarGuard halted you because the path is "
        f'blocked. Your last reply was: "{last[:120]}" — but you did not '
        f"call a tool. You MUST now call a tool: look_around() to assess, "
        f"then start_moving(direction) to maneuver, or stop_moving() + a "
        f"final say() if the goal is over. Pending events: {pending_summary}"
    )


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


def _dispatch_calls(
    calls: list[tuple[str, dict[str, Any]]],
    hw: HardwareContext | None = None,
) -> list[ToolResult]:
    """Run a list of (name, args) tool calls and return their results."""
    results: list[ToolResult] = []
    for name, args in calls:
        logger.info(f"→ tool: {name}({args})")
        result = execute_tool(name, args, hw=hw)
        logger.info(
            f"← tool: {name} status={'ok' if result.ok else 'error'} "
            f"in {result.elapsed_s:.2f}s"
        )
        preview = result.output.strip().replace("\n", " | ")
        if len(preview) > 240:
            preview = preview[:240] + "…"
        logger.info(f"  output: {preview}")
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Gemini loop
# ---------------------------------------------------------------------------


def run_gemini_loop(
    goal: str,
    model: str,
    max_iterations: int,
    hw: HardwareContext | None = None,
) -> str:
    """Drive the chat loop using the Gemini API's native function calling.

    After the loop completes (or hits the iteration cap), fires a background
    thread to compress the session transcript into observations.
    """
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    api_key = os.environ["GOOGLE_GENERATIVE_AI_API_KEY"]
    client = genai.Client(api_key=api_key)

    system_prompt = load_system_prompt()
    tools = to_gemini_tools()

    logger.info(f"model={model} max_iterations={max_iterations}")
    logger.info(f"goal: {goal}")

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
        temperature=DEFAULT_TEMPERATURE,
    )
    chat = client.chats.create(model=model, config=config)

    event_bus = _wire_event_bus(hw)
    if event_bus is not None:
        _drain_event_bus(event_bus)

    try:
        response = chat.send_message(goal)
    except Exception as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc

    transcript: list[str] = [f"GOAL: {goal}"]
    final_text = ""
    empty_response_retries = 0

    for iteration in range(1, max_iterations + 1):
        logger.info(f"--- iteration {iteration}/{max_iterations} ---")

        function_calls, text = _split_response(response)
        if text:
            logger.info(f"assistant: {text[:400]}{'…' if len(text) > 400 else ''}")

        # Retry on empty Gemini responses (no tools + no text) — transient
        # model failures should not be mistaken for goal completion.
        if not function_calls and not text:
            if empty_response_retries < MAX_EMPTY_RESPONSE_RETRIES:
                empty_response_retries += 1
                logger.warning(
                    f"empty response from Gemini — retry "
                    f"{empty_response_retries}/{MAX_EMPTY_RESPONSE_RETRIES}"
                )
                transcript.append(f"EMPTY_RETRY: attempt={empty_response_retries}")
                try:
                    response = chat.send_message(_EMPTY_RESPONSE_NUDGE)
                except Exception as exc:
                    raise RuntimeError(
                        f"Gemini empty-response retry failed: {exc}"
                    ) from exc
                continue
            logger.error(
                f"empty response from Gemini after "
                f"{MAX_EMPTY_RESPONSE_RETRIES} retries — giving up"
            )
            transcript.append("ABORT: model returned empty content repeatedly")
            print("\n=== aborted (Gemini returned empty content repeatedly) ===")
            if hw is not None and hw.movement_manager is not None:
                hw.movement_manager.stop()
            break

        # Reset retry counter on any non-empty response.
        empty_response_retries = 0

        if function_calls:
            normalized: list[tuple[str, dict[str, Any]]] = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args) if getattr(fc, "args", None) else {}
                normalized.append((name, args))
                transcript.append(f"CALL: {name}({args})")

            results = _dispatch_calls(normalized, hw=hw)

            response_parts: list[Any] = []
            for (name, _), result in zip(normalized, results):
                preview = result.output.strip()[:300].replace("\n", " | ")
                transcript.append(f"RESULT {name}: {preview}")
                response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response={"result": result.to_text()},
                    )
                )

            try:
                response = chat.send_message(response_parts)
            except Exception as exc:
                raise RuntimeError(f"Gemini follow-up failed: {exc}") from exc
            continue

        # No tool calls. Three cases:
        #   (a) wheels still turning → wait for the next event
        #   (b) wheels stopped because SonarGuard halted us → do NOT exit;
        #       force the model to acknowledge with a tool call
        #   (c) wheels stopped and motor was idle by intent → goal complete
        moving = (
            hw is not None
            and hw.movement_manager is not None
            and hw.movement_manager.is_moving
        )
        safety_stopped = (
            hw is not None
            and hw.movement_manager is not None
            and hw.movement_manager.was_safety_stopped
        )

        if not moving and safety_stopped and event_bus is not None:
            # Case (b) — drain pending events, then nudge the model with a
            # blunt SAFETY_HALT prompt that demands a tool call.
            pending = _drain_pending_events(event_bus)
            for ev in pending:
                transcript.append(ev.to_user_message())

            info = hw.movement_manager.safety_stop_info or {}
            nudge = _build_safety_halt_nudge(info, pending, text)
            transcript.append(nudge)
            logger.info(f"→ {nudge}")
            try:
                response = chat.send_message(nudge)
            except Exception as exc:
                raise RuntimeError(f"Gemini safety-halt nudge failed: {exc}") from exc
            continue

        if not moving or event_bus is None:
            # Case (c) — true goal-complete.
            final_text = text or ""
            transcript.append(f"FINAL: {final_text[:300]}")
            logger.info("no function calls and not moving — goal complete")
            print("\n=== final ===")
            print(final_text or "(model returned empty content)")
            break

        # Case (a) — keep waiting for the next event.
        event = _wait_for_event(event_bus, hw, GOAL_CHECK_INTERVAL_S)
        event_msg = event.to_user_message()
        transcript.append(event_msg)
        logger.info(f"→ {event_msg}")
        try:
            response = chat.send_message(event_msg)
        except Exception as exc:
            raise RuntimeError(f"Gemini event-feed failed: {exc}") from exc

    else:
        logger.warning(f"hit iteration cap of {max_iterations} — stopping")
        # Safety: ensure motor is not left running past the iteration cap.
        if hw is not None and hw.movement_manager is not None:
            hw.movement_manager.stop()
        print("\n=== stopped (iteration cap reached) ===")

    # Final safety net: never leave the motor running once the loop exits.
    if (
        hw is not None
        and hw.movement_manager is not None
        and hw.movement_manager.is_moving
    ):
        hw.movement_manager.stop()

    # Compress session in background — does not delay the caller
    threading.Thread(
        target=lambda: _compress_session(goal, transcript, model),
        daemon=True,
        name="brain-compress",
    ).start()

    return final_text


def _split_response(response: Any) -> tuple[list[Any], str]:
    """Pull (function_calls, text) out of a Gemini response."""
    function_calls: list[Any] = []
    text_chunks: list[str] = []
    try:
        parts = response.candidates[0].content.parts or []
    except (AttributeError, IndexError):
        parts = []
    for part in parts:
        fc = getattr(part, "function_call", None)
        if fc is not None and getattr(fc, "name", ""):
            function_calls.append(fc)
        else:
            text_value = getattr(part, "text", "")
            if text_value:
                text_chunks.append(text_value)
    return function_calls, "".join(text_chunks).strip()


def _wait_for_event(
    bus: queue.Queue[BrainEvent],
    hw: HardwareContext | None,
    timeout_s: float,
) -> BrainEvent:
    """Block until an event arrives or synthesize a GOAL_CHECK on timeout."""
    try:
        return bus.get(timeout=timeout_s)
    except queue.Empty:
        snapshot = (
            hw.movement_manager.snapshot()
            if hw is not None and hw.movement_manager is not None
            else {}
        )
        return BrainEvent(kind="GOAL_CHECK", extra=snapshot)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Rambabu's brain on a goal")
    parser.add_argument(
        "goal",
        nargs="+",
        help="The goal for Rambabu, e.g. 'scout the kitchen'",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=f"Max tool-call rounds (default: {DEFAULT_MAX_ITERATIONS})",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    args = parse_args()
    goal = " ".join(args.goal).strip()
    if not goal:
        print("error: empty goal", file=sys.stderr)
        sys.exit(2)

    try:
        check_gemini_key()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        run_gemini_loop(goal, args.model, args.max_iterations)
    except KeyboardInterrupt:
        logger.warning("interrupted — sending stop")
        execute_tool("move", {"direction": "stop"})
        sys.exit(130)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
