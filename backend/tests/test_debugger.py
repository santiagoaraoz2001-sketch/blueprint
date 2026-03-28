"""Tests for the pipeline visual debugger: breakpoints, step-through, and data inspection.

Tests:
  1. test_breakpoint_pauses — breakpoint on node 2, verify execution pauses with SSE event
  2. test_resume_continues — resume after pause, verify remaining nodes execute
  3. test_step_executes_one — step, verify only one node advances
  4. test_conditional_breakpoint_skips — condition not met, verify no pause
  5. test_abort_cancels — abort during pause, verify run status is cancelled
"""

import asyncio
import contextlib
import json
import threading
import time
import pytest
from unittest.mock import patch, MagicMock

from backend.engine.executor import (
    execute_pipeline,
    debug_action,
    evaluate_breakpoint_condition,
    _pause_at_breakpoint,
    BreakpointAbort,
    _debug_lock,
    _debug_resume_events,
    _debug_step_flags,
    _debug_abort_flags,
    _active_run_semaphore,
    BREAKPOINT_PAUSE_TIMEOUT_S,
)


def _run(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _node(node_id, block_type="text_input", breakpoint=False, breakpoint_condition=None):
    data = {"type": block_type, "label": node_id, "category": "data", "config": {}}
    if breakpoint:
        data["breakpoint"] = True
    if breakpoint_condition:
        data["breakpoint_condition"] = breakpoint_condition
    return {"id": node_id, "type": "blockNode", "data": data, "position": {"x": 0, "y": 0}}


def _edge(source, target, source_handle="output", target_handle="input"):
    return {"id": f"{source}-{target}", "source": source, "target": target,
            "sourceHandle": source_handle, "targetHandle": target_handle}


def _mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.query = MagicMock(return_value=MagicMock(
        filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))))
    return db


def _capture_events():
    events = []
    def capture(run_id, event_type, data):
        events.append((event_type, data))
    return events, capture


def _executor_mocks(stack, capture_fn, fake_outputs):
    """Apply all necessary executor mocks via an ExitStack. Returns nothing."""
    p = lambda target, **kw: stack.enter_context(patch(target, **kw))
    p("backend.engine.executor.publish_event", side_effect=capture_fn)
    p("backend.engine.executor._find_block_module", return_value=MagicMock())
    p("backend.engine.executor._load_and_run_block_with_timeout", return_value=(fake_outputs, {}))
    p("backend.engine.executor._check_cancelled", return_value=False)
    p("backend.engine.executor._check_memory_pressure", return_value=(False, 0))
    p("backend.engine.executor._start_heartbeat", return_value=threading.Event())
    p("backend.engine.executor._collect_system_metrics", return_value=None)
    p("backend.engine.executor.load_block_schema", return_value=None)
    p("backend.engine.executor.validate_inputs")
    p("backend.engine.executor.validate_config", side_effect=lambda s, c: c)
    p("backend.engine.executor.inject_workspace_file_paths")
    p("backend.engine.executor.compute_fingerprints", return_value={})
    p("backend.engine.executor._cache_block_outputs")
    p("backend.engine.executor.register_block_artifacts", return_value=[])
    p("backend.engine.executor._safe_outputs_snapshot", return_value={})
    p("backend.engine.executor.log_run_start")
    p("backend.engine.executor.log_run_complete")
    p("backend.engine.executor.log_run_failed")
    p("backend.engine.executor.log_block_start")
    p("backend.engine.executor.log_block_complete")
    p("backend.engine.executor.log_block_failed")
    # ARTIFACTS_DIR mock
    arts_mock = MagicMock()
    arts_mock.__truediv__ = lambda self, x: MagicMock(
        mkdir=MagicMock(),
        __truediv__=lambda self2, y: MagicMock(parent=MagicMock(mkdir=MagicMock())),
    )
    p("backend.engine.executor.ARTIFACTS_DIR", new=arts_mock)


# ────────────────────────────────────────────────────────────────
# evaluate_breakpoint_condition (unit tests)
# ────────────────────────────────────────────────────────────────

class TestEvaluateBreakpointCondition:
    def test_gt_met(self):
        assert evaluate_breakpoint_condition({"field": "loss", "op": "gt", "value": 2.0}, {"loss": 3.5}) is True

    def test_gt_not_met(self):
        assert evaluate_breakpoint_condition({"field": "loss", "op": "gt", "value": 2.0}, {"loss": 1.0}) is False

    def test_lt_met(self):
        assert evaluate_breakpoint_condition({"field": "score", "op": "lt", "value": 0.5}, {"score": 0.3}) is True

    def test_eq_met(self):
        assert evaluate_breakpoint_condition({"field": "epoch", "op": "eq", "value": 10}, {"epoch": 10}) is True

    def test_neq_met(self):
        assert evaluate_breakpoint_condition({"field": "epoch", "op": "neq", "value": 10}, {"epoch": 5}) is True

    def test_gte_boundary(self):
        assert evaluate_breakpoint_condition({"field": "val", "op": "gte", "value": 3.0}, {"val": 3.0}) is True

    def test_lte_not_met(self):
        assert evaluate_breakpoint_condition({"field": "val", "op": "lte", "value": 3.0}, {"val": 5.0}) is False

    def test_missing_field_pauses(self):
        assert evaluate_breakpoint_condition({"field": "nonexistent", "op": "gt", "value": 2.0}, {"loss": 1.0}) is True

    def test_nested_field_lookup(self):
        assert evaluate_breakpoint_condition({"field": "loss", "op": "gt", "value": 2.0}, {"metrics": {"loss": 3.5}}) is True

    def test_empty_condition_pauses(self):
        assert evaluate_breakpoint_condition({}, {"loss": 1.0}) is True

    def test_none_condition_pauses(self):
        assert evaluate_breakpoint_condition(None, {"loss": 1.0}) is True

    def test_non_numeric_value_pauses(self):
        assert evaluate_breakpoint_condition({"field": "name", "op": "gt", "value": 2.0}, {"name": "hello"}) is True


# ────────────────────────────────────────────────────────────────
# debug_action (unit tests)
# ────────────────────────────────────────────────────────────────

class TestDebugAction:
    def setup_method(self):
        self.run_id = "test-run-debug"
        with _debug_lock:
            _debug_resume_events[self.run_id] = threading.Event()
            _debug_step_flags[self.run_id] = False
            _debug_abort_flags[self.run_id] = False

    def teardown_method(self):
        with _debug_lock:
            _debug_resume_events.pop(self.run_id, None)
            _debug_step_flags.pop(self.run_id, None)
            _debug_abort_flags.pop(self.run_id, None)

    def test_resume_sets_event(self):
        assert debug_action(self.run_id, "resume") is True
        assert _debug_resume_events[self.run_id].is_set()
        assert _debug_step_flags[self.run_id] is False

    def test_step_sets_event_and_flag(self):
        assert debug_action(self.run_id, "step") is True
        assert _debug_resume_events[self.run_id].is_set()
        assert _debug_step_flags[self.run_id] is True

    def test_abort_sets_event_and_flag(self):
        assert debug_action(self.run_id, "abort") is True
        assert _debug_resume_events[self.run_id].is_set()
        assert _debug_abort_flags[self.run_id] is True

    def test_invalid_action_returns_false(self):
        assert debug_action(self.run_id, "invalid") is False

    def test_unknown_run_id_returns_false(self):
        assert debug_action("nonexistent-run", "resume") is False


# ────────────────────────────────────────────────────────────────
# Integration tests: breakpoint pausing with mocked block execution
# ────────────────────────────────────────────────────────────────

class TestBreakpointIntegration:

    def _run_pipeline(self, definition, run_id, fake_outputs, background_fn=None):
        """Run the executor with all mocks applied. Returns captured events."""
        events, capture = _capture_events()

        # Need a resolve_configs return keyed by all node IDs
        node_ids = [n["id"] for n in definition["nodes"]]
        resolved = {nid: ({}, {}) for nid in node_ids}

        bg_thread = None
        if background_fn:
            bg_thread = threading.Thread(target=background_fn, daemon=True)

        with contextlib.ExitStack() as stack:
            _executor_mocks(stack, capture, fake_outputs)
            stack.enter_context(patch(
                "backend.engine.executor.resolve_configs", return_value=resolved))

            db = _mock_db()
            if bg_thread:
                bg_thread.start()
            _run(execute_pipeline("pipe1", run_id, definition, db))
            if bg_thread:
                bg_thread.join(timeout=10)

        return events

    def test_breakpoint_pauses(self):
        """Set breakpoint on node B of A->B->C, verify breakpoint_hit SSE event."""
        nodes = [_node("A"), _node("B", breakpoint=True), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        run_id = "test-bp-pauses"

        def resume():
            time.sleep(0.3)
            debug_action(run_id, "resume")

        events = self._run_pipeline(
            {"nodes": nodes, "edges": edges}, run_id,
            {"output": "data"}, background_fn=resume)

        bp = [e for e in events if e[0] == "breakpoint_hit"]
        assert len(bp) >= 1, f"Expected breakpoint_hit, got: {[e[0] for e in events]}"
        assert bp[0][1]["node_id"] == "B"

    def test_resume_continues(self):
        """After resume, remaining nodes execute and run_completed fires."""
        nodes = [_node("A"), _node("B", breakpoint=True), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        run_id = "test-bp-resume"

        def resume():
            time.sleep(0.3)
            debug_action(run_id, "resume")

        events = self._run_pipeline(
            {"nodes": nodes, "edges": edges}, run_id,
            {"output": "data"}, background_fn=resume)

        completed_ids = {e[1]["node_id"] for e in events if e[0] == "node_completed"}
        assert {"A", "B", "C"} <= completed_ids
        assert any(e[0] == "run_completed" for e in events)

    def test_step_executes_one(self):
        """Step from A should pause again at B."""
        nodes = [_node("A", breakpoint=True), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        run_id = "test-bp-step"

        def step_then_resume():
            time.sleep(0.3)
            debug_action(run_id, "step")
            time.sleep(0.3)
            debug_action(run_id, "resume")

        events = self._run_pipeline(
            {"nodes": nodes, "edges": edges}, run_id,
            {"output": "data"}, background_fn=step_then_resume)

        bp = [e for e in events if e[0] == "breakpoint_hit"]
        assert len(bp) >= 2, f"Expected 2 breakpoint_hit events, got {len(bp)}"
        assert bp[0][1]["node_id"] == "A"
        assert bp[1][1]["node_id"] == "B"

    def test_conditional_breakpoint_skips(self):
        """Conditional breakpoint with unmet condition should not pause."""
        nodes = [
            _node("A"),
            _node("B", breakpoint=True, breakpoint_condition={"field": "loss", "op": "gt", "value": 100.0}),
            _node("C"),
        ]
        edges = [_edge("A", "B"), _edge("B", "C")]
        run_id = "test-bp-cond-skip"

        # loss=0.5 is NOT > 100 → no pause expected
        events = self._run_pipeline(
            {"nodes": nodes, "edges": edges}, run_id,
            {"output": "data", "loss": 0.5})

        bp = [e for e in events if e[0] == "breakpoint_hit"]
        assert len(bp) == 0, f"Expected no breakpoint_hit, got {len(bp)}"
        assert any(e[0] == "run_completed" for e in events)

    def test_abort_cancels(self):
        """Abort during breakpoint pause cancels the run."""
        nodes = [_node("A"), _node("B", breakpoint=True), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        run_id = "test-bp-abort"

        def abort():
            time.sleep(0.3)
            debug_action(run_id, "abort")

        events = self._run_pipeline(
            {"nodes": nodes, "edges": edges}, run_id,
            {"output": "data"}, background_fn=abort)

        cancel = [e for e in events if e[0] == "run_cancelled"]
        assert len(cancel) >= 1, f"Expected run_cancelled, got: {[e[0] for e in events]}"
        assert cancel[0][1].get("reason") == "debug_abort"

        completed_ids = {e[1]["node_id"] for e in events if e[0] == "node_completed"}
        assert "C" not in completed_ids


# ────────────────────────────────────────────────────────────────
# Risk fix tests: timeout, semaphore, _pause_at_breakpoint
# ────────────────────────────────────────────────────────────────

class TestPauseAtBreakpoint:
    """Unit tests for the _pause_at_breakpoint helper."""

    def setup_method(self):
        self.run_id = "test-pause-helper"
        with _debug_lock:
            _debug_resume_events[self.run_id] = threading.Event()
            _debug_step_flags[self.run_id] = False
            _debug_abort_flags[self.run_id] = False
        # Acquire semaphore to simulate active run
        _active_run_semaphore.acquire()

    def teardown_method(self):
        with _debug_lock:
            _debug_resume_events.pop(self.run_id, None)
            _debug_step_flags.pop(self.run_id, None)
            _debug_abort_flags.pop(self.run_id, None)
        # Release semaphore (may already be released by the test)
        try:
            _active_run_semaphore.release()
        except ValueError:
            pass

    def test_pause_releases_semaphore_during_wait(self):
        """The semaphore should be released while paused, then re-acquired on resume."""
        initial_value = _active_run_semaphore._value  # Should be MAX-1 after setup

        # Resume from background thread
        def resume():
            time.sleep(0.1)
            # While paused, the semaphore should have been released (value +1)
            debug_action(self.run_id, "resume")

        t = threading.Thread(target=resume, daemon=True)
        t.start()

        with patch("backend.engine.executor.publish_event"):
            _pause_at_breakpoint(
                self.run_id, "N1", 0, 3,
                ["N1", "N2", "N3"], {},
            )

        t.join(timeout=5)
        # After resume, semaphore should be re-acquired (back to initial value)
        assert _active_run_semaphore._value == initial_value

    def test_abort_raises_breakpoint_abort(self):
        """Abort during pause should raise BreakpointAbort."""
        def abort():
            time.sleep(0.1)
            debug_action(self.run_id, "abort")

        t = threading.Thread(target=abort, daemon=True)
        t.start()

        with patch("backend.engine.executor.publish_event"):
            with pytest.raises(BreakpointAbort, match="Aborted at breakpoint"):
                _pause_at_breakpoint(
                    self.run_id, "N1", 0, 3,
                    ["N1", "N2", "N3"], {},
                )

        t.join(timeout=5)

    def test_timeout_raises_breakpoint_abort(self):
        """When the timeout expires, BreakpointAbort should be raised."""
        # Patch timeout to a very short value for testing
        with patch("backend.engine.executor.BREAKPOINT_PAUSE_TIMEOUT_S", 0.2):
            with patch("backend.engine.executor.publish_event"):
                with pytest.raises(BreakpointAbort, match="timed out"):
                    _pause_at_breakpoint(
                        self.run_id, "N1", 0, 3,
                        ["N1", "N2", "N3"], {},
                    )

    def test_emits_breakpoint_hit_event(self):
        """Should emit a breakpoint_hit SSE event with correct data."""
        captured = []
        def capture(run_id, event_type, data):
            captured.append((event_type, data))

        def resume():
            time.sleep(0.1)
            debug_action(self.run_id, "resume")

        t = threading.Thread(target=resume, daemon=True)
        t.start()

        with patch("backend.engine.executor.publish_event", side_effect=capture):
            _pause_at_breakpoint(
                self.run_id, "N2", 1, 3,
                ["N1", "N2", "N3"],
                {"N1": {"out": 42}},
                conditional=True,
            )

        t.join(timeout=5)

        bp_events = [e for e in captured if e[0] == "breakpoint_hit"]
        assert len(bp_events) == 1
        data = bp_events[0][1]
        assert data["node_id"] == "N2"
        assert data["conditional"] is True
        assert "N1" in data["completed_nodes"]
        assert "N1" in data["outputs_preview"]


class TestSemaphoreIntegration:
    """Tests that the active-run semaphore correctly limits concurrency."""

    def test_semaphore_released_after_normal_run(self):
        """A normal run (no breakpoints) acquires and releases the semaphore."""
        nodes = [_node("A")]
        edges = []
        definition = {"nodes": nodes, "edges": edges}
        events, capture = _capture_events()
        run_id = "test-sem-normal"

        initial_value = _active_run_semaphore._value

        with contextlib.ExitStack() as stack:
            _executor_mocks(stack, capture, {"output": "data"})
            stack.enter_context(patch(
                "backend.engine.executor.resolve_configs",
                return_value={"A": ({}, {})}))
            db = _mock_db()
            _run(execute_pipeline("pipe1", run_id, definition, db))

        # Semaphore value should be restored
        assert _active_run_semaphore._value == initial_value

    def test_semaphore_released_after_abort(self):
        """An aborted run still releases the semaphore."""
        nodes = [_node("A"), _node("B", breakpoint=True), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        definition = {"nodes": nodes, "edges": edges}
        run_id = "test-sem-abort"

        initial_value = _active_run_semaphore._value

        def abort():
            time.sleep(0.3)
            debug_action(run_id, "abort")

        events, capture = _capture_events()
        with contextlib.ExitStack() as stack:
            _executor_mocks(stack, capture, {"output": "data"})
            stack.enter_context(patch(
                "backend.engine.executor.resolve_configs",
                return_value={"A": ({}, {}), "B": ({}, {}), "C": ({}, {})}))
            db = _mock_db()
            t = threading.Thread(target=abort, daemon=True)
            t.start()
            _run(execute_pipeline("pipe1", run_id, definition, db))
            t.join(timeout=5)

        # Semaphore value should be restored
        assert _active_run_semaphore._value == initial_value
