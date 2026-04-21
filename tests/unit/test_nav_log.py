"""Unit tests for NavLog — no hardware, no network."""

from __future__ import annotations

import pytest

from agno_ai.lib.nav_log import (
    MAX_ENTRIES,
    NavLog,
    get_nav_log,
    reset_nav_log,
)


class TestNavLogRecord:
    def test_empty_log_returns_no_context(self):
        log = NavLog()
        assert log.to_context_str() == ""

    def test_empty_log_returns_no_transcript(self):
        log = NavLog()
        assert log.to_transcript_str() == ""

    def test_single_done_entry(self):
        log = NavLog()
        log.record("forward", 20.0, 20.0, "done", None, 0.5)
        out = log.to_context_str()
        assert "forward" in out
        assert "20" in out
        assert "✓" in out

    def test_blocked_entry_shows_symbol(self):
        log = NavLog()
        log.record("right", 15.0, 0.0, "blocked", "shelf", 0.0)
        out = log.to_context_str()
        assert "✗" in out
        assert "shelf" in out

    def test_sonar_stop_shows_partial_distance(self):
        log = NavLog()
        log.record("forward", 40.0, 12.0, "sonar_stop", "obstacle ahead", 1.1)
        out = log.to_context_str()
        assert "⚠" in out
        assert "12" in out
        assert "40" in out

    def test_capped_entry(self):
        log = NavLog()
        log.record("forward", 60.0, 30.0, "capped", None, 1.0)
        out = log.to_context_str()
        assert "↓" in out

    def test_index_increments_per_entry(self):
        log = NavLog()
        log.record("forward", 10.0, 10.0, "done")
        log.record("back", 10.0, 10.0, "done")
        out = log.to_context_str()
        assert "#01" in out
        assert "#02" in out

    def test_rolling_window_caps_at_max(self):
        log = NavLog()
        for i in range(MAX_ENTRIES + 3):
            log.record("forward", float(i), float(i), "done")
        # deque is capped — only MAX_ENTRIES entries remain
        out = log.to_context_str()
        assert out.count("✓") == MAX_ENTRIES

    def test_index_keeps_incrementing_past_max(self):
        log = NavLog()
        for i in range(MAX_ENTRIES + 2):
            log.record("forward", 10.0, 10.0, "done")
        out = log.to_context_str()
        # oldest entry scrolled off, highest index still present
        assert f"#{MAX_ENTRIES + 2:02d}" in out

    def test_transcript_includes_all_fields(self):
        log = NavLog()
        log.record("left", 15.0, 10.0, "sonar_stop", "wall", 0.8)
        t = log.to_transcript_str()
        assert "left" in t
        assert "sonar_stop" in t
        assert "wall" in t

    def test_context_header_present(self):
        log = NavLog()
        log.record("forward", 5.0, 5.0, "done")
        assert "NAV LOG" in log.to_context_str()

    def test_transcript_header_present(self):
        log = NavLog()
        log.record("forward", 5.0, 5.0, "done")
        assert "Session moves" in log.to_transcript_str()


class TestNavLogReset:
    def test_reset_clears_entries(self):
        log = NavLog()
        log.record("forward", 10.0, 10.0, "done")
        log.reset()
        assert log.to_context_str() == ""

    def test_reset_restarts_index(self):
        log = NavLog()
        log.record("forward", 10.0, 10.0, "done")
        log.reset()
        log.record("back", 5.0, 5.0, "done")
        assert "#01" in log.to_context_str()


class TestNavLogSingleton:
    def test_get_nav_log_returns_same_instance(self):
        a = get_nav_log()
        b = get_nav_log()
        assert a is b

    def test_reset_nav_log_returns_new_instance(self):
        a = get_nav_log()
        b = reset_nav_log()
        c = get_nav_log()
        assert b is not a
        assert c is b

    def test_reset_clears_singleton_entries(self):
        log = get_nav_log()
        log.record("forward", 20.0, 20.0, "done")
        reset_nav_log()
        assert get_nav_log().to_context_str() == ""
