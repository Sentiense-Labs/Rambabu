"""
Integration test: do agno_memories and agno_learnings get written after a real agent run?

Requires: GOOGLE_GENERATIVE_AI_API_KEY in environment (real Gemini call).
No hardware needed — all hw is mocked to return safe dummy values.

TWO SEPARATE MEMORY SYSTEMS:
  agno_learnings  — ObservationalMemory: spatial/environmental facts extracted from the
                    rover's transcript (what it saw, where it went). Written on flush().
  agno_memories   — agno MemoryManager: facts about the USER who gave commands (e.g.
                    "user prefers the rover avoids the kitchen"). Only populated when
                    the user message contains factual personal information to store.
                    A simple "say hello" goal will NOT trigger it — that's correct behaviour.

Run with:
    uv run python tests/test_memory_integration.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock
from dotenv import load_dotenv

load_dotenv()

# ── Mock hardware before any agno_ai import ──────────────────────────────────
sys.modules.setdefault("RPi", MagicMock())
sys.modules.setdefault("RPi.GPIO", MagicMock())
sys.modules.setdefault("picamera2", MagicMock())
sys.modules.setdefault("pyttsx3", MagicMock())
sys.modules.setdefault("cv2", MagicMock())

import agno_ai
from agno_ai.types.context import HardwareContext

_mock_motor = MagicMock()
_mock_motor.is_moving_forward = False
_mock_motor.is_moving_backward = False

_mock_sonar = MagicMock()
_mock_sonar.get_distance.return_value = 200.0

_mock_sonar_guard = MagicMock()
_mock_sonar_guard.is_running = True
_mock_sonar_guard.snapshot.return_value = (200.0, "clear")

_hw = HardwareContext(
    motor=_mock_motor,
    ultrasonic=_mock_sonar,
    rear_ultrasonic=_mock_sonar,
    sonar_guard=_mock_sonar_guard,
)
agno_ai.set_hw(_hw)


# ── Run the agent ─────────────────────────────────────────────────────────────

import tempfile
from agno.db.sqlite import SqliteDb
from agno_ai.agents.goal_driven import GoalDrivenAgent

db_file = tempfile.mktemp(suffix=".db")
print(f"Using temp DB: {db_file}")

db = SqliteDb(db_file=db_file)
agent = GoalDrivenAgent(hw=_hw, os_db=db, model_preset="FAST")

print("Starting goal...")
agent.start("Say hello and report that you are ready.")

# Wait for the agent session thread to finish (poll the thread)
session_thread = agent._session._thread
if session_thread:
    session_thread.join(timeout=120)

# flush forces ObservationalMemory to write even if token threshold wasn't reached
agent.stop()
# Wait for background_executor futures (memory/learning extraction) to complete.
executor = agent._agent.background_executor
if executor is not None:
    executor.shutdown(wait=True, cancel_futures=False)
time.sleep(2)  # let any remaining daemon threads finish


# ── Check both tables ─────────────────────────────────────────────────────────

import sqlite3

conn = sqlite3.connect(db_file)

tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

learnings = (
    conn.execute("SELECT learning_id, learning_type, content FROM agno_learnings").fetchall()
    if "agno_learnings" in tables else []
)
memories = (
    conn.execute("SELECT memory_id, memory, user_id FROM agno_memories").fetchall()
    if "agno_memories" in tables else []
)
conn.close()
print(f"Tables in DB: {sorted(tables)}")

print(f"\n{'='*60}")
print(f"agno_learnings rows: {len(learnings)}")
for row in learnings:
    lid, ltype, content = row
    print(f"  [{ltype}] {str(content)[:120]}")

print(f"\nagno_memories rows: {len(memories)}")
for row in memories:
    mid, memory, uid = row
    print(f"  user={uid} | {str(memory)[:120]}")

print(f"{'='*60}")

ok = True

# agno_learnings: MUST have rows — ObservationalMemory is the primary rover memory
if len(learnings) == 0:
    print("FAIL: agno_learnings is empty — ObservationalMemory did not write")
    ok = False
else:
    print("PASS: agno_learnings has rows (ObservationalMemory working)")

# agno_memories: only fills when user messages contain personal/preference facts.
# "Say hello" contains no such facts, so empty is CORRECT here.
# It will fill during real sessions when users share preferences or constraints.
if len(memories) == 0:
    print("OK:   agno_memories is empty — correct for a goal with no user facts")
else:
    print("PASS: agno_memories has rows (MemoryManager found user facts to store)")

sys.exit(0 if ok else 1)
