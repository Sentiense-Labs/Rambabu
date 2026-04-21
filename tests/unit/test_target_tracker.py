"""Unit tests for TargetTracker singleton."""

from __future__ import annotations

import time

import pytest

from agno_ai.lib.target_tracker import (
    TargetTracker,
    get_target_tracker,
    reset_target_tracker,
)


class TestTargetTrackerRecord:
    def setup_method(self):
        self.tracker = TargetTracker()

    def test_empty_tracker_has_no_sighting(self):
        assert self.tracker.has_sighting() is False

    def test_to_context_str_empty_when_no_sighting(self):
        assert self.tracker.to_context_str() == ""

    def test_record_sets_has_sighting(self):
        self.tracker.record("Where is the fridge?", "front", 0.9)
        assert self.tracker.has_sighting() is True

    def test_context_str_contains_direction(self):
        self.tracker.record("Where is the fridge?", "front", 0.9)
        ctx = self.tracker.to_context_str()
        assert "front" in ctx

    def test_context_str_contains_query(self):
        self.tracker.record("Where is the fridge?", "right", 0.8)
        ctx = self.tracker.to_context_str()
        assert "fridge" in ctx

    def test_context_str_contains_confidence(self):
        self.tracker.record("find the door", "left", 0.75)
        ctx = self.tracker.to_context_str()
        assert "0.75" in ctx

    def test_context_str_contains_orient_instruction(self):
        self.tracker.record("find the door", "right", 0.6)
        ctx = self.tracker.to_context_str()
        assert "Orient toward" in ctx

    def test_overwrite_replaces_previous_sighting(self):
        self.tracker.record("first query", "left", 0.5)
        self.tracker.record("second query", "right", 0.9)
        ctx = self.tracker.to_context_str()
        assert "right" in ctx
        assert "second query" in ctx
        assert "first query" not in ctx


class TestTargetTrackerReset:
    def test_reset_clears_sighting(self):
        tracker = TargetTracker()
        tracker.record("find fridge", "front", 0.9)
        tracker.reset()
        assert tracker.has_sighting() is False

    def test_reset_clears_context_str(self):
        tracker = TargetTracker()
        tracker.record("find fridge", "front", 0.9)
        tracker.reset()
        assert tracker.to_context_str() == ""


class TestTargetTrackerSingleton:
    def setup_method(self):
        reset_target_tracker()

    def test_get_returns_same_instance(self):
        a = get_target_tracker()
        b = get_target_tracker()
        assert a is b

    def test_reset_returns_fresh_instance(self):
        original = get_target_tracker()
        original.record("find fridge", "front", 0.9)
        new = reset_target_tracker()
        assert new.has_sighting() is False

    def test_get_after_reset_returns_new_instance(self):
        reset_target_tracker()
        tracker = get_target_tracker()
        assert tracker.has_sighting() is False

    def test_record_via_singleton_persists(self):
        get_target_tracker().record("find plant", "left", 0.7)
        assert get_target_tracker().has_sighting() is True
        assert "left" in get_target_tracker().to_context_str()
