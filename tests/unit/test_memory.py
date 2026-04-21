"""Unit tests for ObservationalMemory DB writes (no hardware, no real LLM)."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from agno.db.sqlite import SqliteDb

from agno_ai.lib.memory import ObservationalMemory


@pytest.fixture()
def tmp_db(tmp_path):
    db_file = str(tmp_path / "test_memory.db")
    db = SqliteDb(db_file=db_file)
    db._get_table(table_type="learnings", create_table_if_not_found=True)
    return db


def _row_count(db: SqliteDb, learning_type: str) -> int:
    table = db._get_table(table_type="learnings")
    with db.Session() as sess, sess.begin():
        result = sess.execute(
            table.select().where(table.c.learning_type == learning_type)
        )
        return len(result.fetchall())


class TestObservationalMemorySave:
    def test_save_learning_commits_to_db(self, tmp_db):
        """_save_learning must persist a row (previously broke due to missing sess.begin())."""
        mem = ObservationalMemory(db=tmp_db, session_id="test-session")
        mem._save_learning("observation", {"text": "saw a chair", "goal": "explore"})
        assert _row_count(tmp_db, "observation") == 1

    def test_delete_learning_commits_to_db(self, tmp_db):
        mem = ObservationalMemory(db=tmp_db, session_id="test-session")
        mem._save_learning("observation", {"text": "saw a table", "goal": "explore"})
        assert _row_count(tmp_db, "observation") == 1

        table = tmp_db._get_table(table_type="learnings")
        with tmp_db.Session() as sess, sess.begin():
            row = sess.execute(table.select()).fetchone()
        learning_id = row[0]

        mem._delete_learnings([learning_id])
        assert _row_count(tmp_db, "observation") == 0

    def test_get_observations_returns_saved_text(self, tmp_db):
        mem = ObservationalMemory(db=tmp_db, session_id="test-session")
        mem._save_learning("observation", {"text": "sofa in living room", "goal": "explore"})
        obs = mem.get_observations()
        assert "sofa in living room" in obs

    def test_get_default_compress_model_exists(self, tmp_db):
        """Previously missing on ObservationalMemory — caused AttributeError in _run_observe."""
        mem = ObservationalMemory(db=tmp_db, session_id="test-session")
        model = mem._get_default_compress_model()
        assert model is not None
        assert hasattr(model, "id")

    def test_flush_writes_via_observe(self, tmp_db):
        """flush() should trigger _run_observe and persist an observation row."""
        mem = ObservationalMemory(db=tmp_db, session_id="test-session")

        fake_response = MagicMock()
        fake_response.text = "- Chair spotted near door\n- Clear path to kitchen"

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = fake_response

        with (
            patch.dict("os.environ", {"GOOGLE_GENERATIVE_AI_API_KEY": "fake-key"}),
            patch("google.genai.Client", return_value=fake_client),
        ):
            mem.flush(
                goal="explore the room",
                messages=["GOAL: explore", "AGENT: moving forward", "TOOL: distance 150cm"],
            )

        assert _row_count(tmp_db, "observation") == 1

    def test_flush_no_op_when_llm_returns_no_observations(self, tmp_db):
        mem = ObservationalMemory(db=tmp_db, session_id="test-session")

        fake_response = MagicMock()
        fake_response.text = "(no new observations)"

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = fake_response

        with (
            patch.dict("os.environ", {"GOOGLE_GENERATIVE_AI_API_KEY": "fake-key"}),
            patch("google.genai.Client", return_value=fake_client),
        ):
            mem.flush(goal="greet user", messages=["GOAL: greet", "AGENT: Hello!"])

        assert _row_count(tmp_db, "observation") == 0
