"""
ObservationalMemory — Mastra-style two-stage memory.

observations  = raw append-only buffer.
              When tokens >= token_threshold → _observe() → stores "observation" entry.
              Buffer is NOT cleared after observe.

observations (DB) = raw notes accumulated so far.
              When count >= observation_count_reflect → _reflect()
              → synthesises all observations into one "reflection"
              → clears all observation entries

reflections  = permanent condensed history. Never deleted by this module.

get_observations() returns: reflections + observations (both in goal context).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from agno.db.sqlite import SqliteDb
from agno.lib.prompts import COMPRESS_PROMPT
from agno.utils.string import generate_id

if TYPE_CHECKING:
    from agno.models.base import Model

logger = logging.getLogger("agno.memory")


# ── Thresholds ────────────────────────────────────────────────────────────────

TOKEN_OBSERVATION_THRESHOLD = 1500
OBSERVATION_COUNT_REFLECT = 3


class ObservationalMemory:
    NAMESPACE = "rambabu-observations"
    MAX_CHARS = 4000

    def __init__(
        self,
        db: SqliteDb,
        session_id: str,
        token_reflection_threshold: int = TOKEN_OBSERVATION_THRESHOLD,
        compress_model: "Model | None" = None,
    ) -> None:
        self._db = db
        self._session_id = session_id
        self._token_threshold = token_reflection_threshold
        self._compress_model = compress_model
        self._pending: list[str] = []
        self._pending_tokens = 0
        self._lock = threading.Lock()

    # ── public ────────────────────────────────────────────────────────────────

    def on_run_complete(self, goal: str, messages: list[str]) -> None:
        raw = "\n".join(messages)
        tokens = self._count_tokens(raw)
        with self._lock:
            self._pending.append(raw)
            self._pending_tokens += tokens

        if self._pending_tokens >= self._token_threshold:
            self._pending_tokens = 0
            pending_snapshot = list(self._pending)
            threading.Thread(
                target=self._run_observe,
                args=(goal, pending_snapshot),
                daemon=True,
                name="agno-observe",
            ).start()

    def flush(self, goal: str, messages: list[str]) -> None:
        if messages:
            raw = "\n".join(messages)
            with self._lock:
                self._pending.append(raw)
        self._flush_all(goal)

    def get_observations(self) -> str:
        parts = []
        for lt in ("reflection", "observation"):
            try:
                rows = self._db.get_learnings(
                    namespace=self.NAMESPACE,
                    session_id=self._session_id,
                    learning_type=lt,
                )
            except Exception as exc:
                logger.warning(f"ObservationalMemory: load failed — {exc}")
                continue
            for row in rows:
                content = row.get("content") or {}
                text = self._extract_text(content)
                if text:
                    parts.append(text)

        combined = "\n".join(parts)
        if len(combined) > self.MAX_CHARS:
            combined = combined[: self.MAX_CHARS] + "\n... (truncated)"
        return combined

    # ── internal ───────────────────────────────────────────────────────────

    @staticmethod
    def _count_tokens(text: str) -> int:
        return len(text) // 4

    def _flush_all(self, goal: str) -> None:
        with self._lock:
            pending_snapshot = list(self._pending)
            self._pending.clear()
            self._pending_tokens = 0
        if pending_snapshot:
            self._run_observe(goal, pending_snapshot)
        self._check_reflect()

    def _run_observe(self, goal: str, pending: list[str]) -> None:
        if not pending:
            return

        api_key = self._get_api_key()
        if not api_key:
            return

        from google import genai as google_genai

        transcript = "\n".join(pending[-20:])
        prompt = COMPRESS_PROMPT.replace("{transcript}", transcript)

        try:
            model = self._compress_model or self._get_default_compress_model()
            client = google_genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model.id if hasattr(model, "id") else str(model),
                contents=prompt,
            )
            text = (response.text or "").strip()
        except Exception as exc:
            logger.warning(f"ObservationalMemory: observe failed — {exc}")
            return

        if not text or text == "(no new observations)":
            return

        self._save_learning(
            learning_type="observation",
            content={
                "text": f"## [{time.strftime('%Y-%m-%d %H:%M')}] {goal}\n{text}",
                "goal": goal,
            },
        )
        logger.info(f"ObservationalMemory: observed {len(text)} chars")
        self._check_reflect()

    def _check_reflect(self) -> None:
        threading.Thread(
            target=self._run_reflect,
            daemon=True,
            name="agno-reflect",
        ).start()

    def _run_reflect(self) -> None:
        try:
            rows = self._db.get_learnings(
                namespace=self.NAMESPACE,
                session_id=self._session_id,
                learning_type="observation",
            )
        except Exception as exc:
            logger.warning(f"ObservationalMemory: reflect load failed — {exc}")
            return

        if not rows or len(rows) < OBSERVATION_COUNT_REFLECT:
            return

        api_key = self._get_api_key()
        if not api_key:
            return

        from google import genai as google_genai

        observations_text = "\n".join(
            self._extract_text(row.get("content")) for row in rows
        )
        prompt = (
            "You are a spatial reasoning assistant for an autonomous rover. "
            "From the following accumulated observation notes, synthesise a structured "
            "reflection capturing patterns, causation, and practical navigation insights.\n\n"
            "Format your response as markdown bullets under these headings:\n"
            "## Patterns\n"
            "## Causation\n"
            "## Recommendations\n\n"
            f"Observations:\n{observations_text}"
        )

        try:
            model = self._compress_model or self._get_default_compress_model()
            client = google_genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model.id if hasattr(model, "id") else str(model),
                contents=prompt,
            )
            text = (response.text or "").strip()
        except Exception as exc:
            logger.warning(f"ObservationalMemory: reflect failed — {exc}")
            return

        if not text:
            return

        self._save_learning(
            learning_type="reflection",
            content={
                "text": f"## [{time.strftime('%Y-%m-%d %H:%M')}]\n{text}",
            },
        )

        obs_ids = [row["learning_id"] for row in rows]
        self._delete_learnings(obs_ids)
        logger.info(
            f"ObservationalMemory: reflected {len(text)} chars, "
            f"deleted {len(obs_ids)} observations"
        )

    def _extract_text(self, content: Any) -> str:
        if not content:
            return ""
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                return content
        if isinstance(content, dict):
            return content.get("text", json.dumps(content, ensure_ascii=False))
        return str(content)

    def _save_learning(
        self,
        learning_type: str,
        content: dict[str, Any],
    ) -> None:
        try:
            table = self._db._get_table(table_type="learnings")
            with self._db.Session() as sess:
                sess.execute(
                    table.insert().values(
                        learning_id=generate_id(),
                        learning_type=learning_type,
                        namespace=self.NAMESPACE,
                        session_id=self._session_id,
                        content=json.dumps(content),
                        agent_id="rambabu",
                        created_at=int(time.time()),
                    )
                )
        except Exception as exc:
            logger.warning(f"ObservationalMemory: save failed — {exc}")

    def _delete_learnings(self, learning_ids: list[str]) -> None:
        if not learning_ids:
            return
        try:
            table = self._db._get_table(table_type="learnings")
            with self._db.Session() as sess:
                sess.execute(
                    table.delete().where(table.c.learning_id.in_(learning_ids))
                )
        except Exception as exc:
            logger.warning(f"ObservationalMemory: delete failed — {exc}")

    @staticmethod
    def _get_api_key() -> str:
        import os

        return os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")


# ── SessionCompactor ────────────────────────────────────────────────────────────


MAX_SESSION_RUNS = 20


class SessionCompactor:
    """Compacts old runs in agno_sessions by summarising and trimming.

    After MAX_SESSION_RUNS accumulate in a session, the oldest runs are
    LLM-summarised and stored as a session_summary in agno_learnings,
    then trimmed from the session so the DB stays bounded.
    """

    def __init__(
        self,
        db: SqliteDb,
        session_id: str,
        max_session_runs: int = MAX_SESSION_RUNS,
        compress_model: "Model | None" = None,
    ) -> None:
        self._db = db
        self._session_id = session_id
        self._max_runs = max_session_runs
        self._compress_model = compress_model
        self._lock = threading.Lock()

    def on_run_complete(self) -> None:
        with self._lock:
            if self._should_compact():
                threading.Thread(
                    target=self._compact,
                    daemon=True,
                    name="agno-session-compact",
                ).start()

    def _should_compact(self) -> bool:
        try:
            from agno.db.base import SessionType

            session = self._db.get_session(
                session_id=self._session_id,
                session_type=SessionType.AGENT,
            )
            if session is None:
                return False
            runs = getattr(session, "runs", None) or []
            return len(runs) > self._max_runs
        except Exception:
            return False

    def _compact(self) -> None:
        try:
            from agno.db.base import SessionType

            session = self._db.get_session(
                session_id=self._session_id,
                session_type=SessionType.AGENT,
            )
            if session is None:
                return

            runs: list = getattr(session, "runs", None) or []
            if len(runs) <= self._max_runs:
                return

            to_compact = runs[: -self._max_runs]
            remaining = runs[-self._max_runs :]

            summary_text = self._summarise_runs(to_compact)
            if summary_text:
                self._save_summary(summary_text, len(to_compact))

            self._trim_session(remaining)
            logger.info(
                f"SessionCompactor: compacted {len(to_compact)} runs, "
                f"kept {len(remaining)} for session {self._session_id[:20]}"
            )
        except Exception as exc:
            logger.warning(f"SessionCompactor: failed — {exc}")

    def _summarise_runs(self, runs: list) -> str:
        api_key = self._get_api_key()
        if not api_key:
            return ""

        from google import genai as google_genai

        parts = []
        for run in runs:
            msgs = getattr(run, "messages", None) or []
            for msg in msgs:
                role = getattr(msg, "role", "user")
                content = getattr(msg, "content", "") or ""
                if content:
                    parts.append(f"[{role}] {content}")
        if not parts:
            return ""

        transcript = "\n".join(parts[-50:])
        prompt = (
            "Summarise the following agent conversation runs into a concise memory "
            "bullet list capturing goals, decisions, and outcomes:\n\n" + transcript
        )

        model = self._compress_model or self._get_default_compress_model()
        try:
            client = google_genai.Client(api_key=api_key)
            resp = client.models.generate_content(
                model=model.id if hasattr(model, "id") else str(model),
                contents=prompt,
            )
            return (resp.text or "").strip()
        except Exception as exc:
            logger.warning(f"SessionCompactor: summarisation failed — {exc}")
            return ""

    def _save_summary(self, text: str, run_count: int) -> None:
        if not text:
            return
        try:
            table = self._db._get_table(table_type="learnings")
            with self._db.Session() as sess:
                sess.execute(
                    table.insert().values(
                        learning_id=generate_id(),
                        learning_type="session_summary",
                        namespace="rambabu-sessions",
                        session_id=self._session_id,
                        content=json.dumps(
                            {
                                "text": f"## Session Summary ({run_count} runs)\n{text}",
                                "run_count": run_count,
                            }
                        ),
                        agent_id="rambabu",
                        created_at=int(time.time()),
                    )
                )
        except Exception as exc:
            logger.warning(f"SessionCompactor: summary save failed — {exc}")

    def _trim_session(self, remaining_runs: list) -> None:
        try:
            table = self._db._get_table(table_type="sessions")
            with self._db.Session() as sess:
                sess.execute(
                    table.update()
                    .where(table.c.session_id == self._session_id)
                    .values(runs=json.dumps([r.to_dict() for r in remaining_runs]))
                )
        except Exception as exc:
            logger.warning(f"SessionCompactor: trim failed — {exc}")

    @staticmethod
    def _get_api_key() -> str:
        import os

        return os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")

    def _get_default_compress_model(self):
        from agno.models.google import Gemini

        return Gemini(id="gemini-2.5-flash-lite")
