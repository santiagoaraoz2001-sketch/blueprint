import asyncio
import collections
import json
from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/events", tags=["events"])

# In-memory event queues per run
_run_queues: dict[str, list[asyncio.Queue]] = {}

# Event buffer: last 200 events per run (ring buffer)
_run_buffers: dict[str, collections.deque] = {}
# Monotonic event ID counter per run
_event_counters: dict[str, int] = {}

KEEPALIVE_TIMEOUT = 15.0  # seconds
BUFFER_SIZE = 200


def publish_event(run_id: str, event_type: str, data: dict):
    """Publish an event to all SSE subscribers for a run.

    Supported event types:
      node_started   – block execution begins
      node_progress  – block progress update (0-1)
      node_log       – log message from block
      node_output    – block outputs (truncated)
      node_completed – block finished successfully
      node_failed    – block raised an error
      node_cached    – block skipped; outputs reused from a previous run
                       (emitted by partial executor)
      node_iteration – emitted once per loop iteration (loop_controller)
      node_retry     – block retry attempt in progress
      metric         – per-block metric value
      system_metric  – CPU/memory/GPU snapshot
      run_completed  – pipeline finished successfully
      run_failed     – pipeline failed
      run_cancelled  – pipeline cancelled by user
    """
    # Assign monotonic event ID
    if run_id not in _event_counters:
        _event_counters[run_id] = 0
    _event_counters[run_id] += 1
    event_id = _event_counters[run_id]

    event = {"event": event_type, "data": json.dumps(data), "id": str(event_id)}

    # Append to ring buffer
    if run_id not in _run_buffers:
        _run_buffers[run_id] = collections.deque(maxlen=BUFFER_SIZE)
    _run_buffers[run_id].append(event)

    # Push to live subscribers (crash-safe per queue)
    for queue in list(_run_queues.get(run_id, [])):
        try:
            queue.put_nowait(event)
        except Exception:
            pass  # Dead subscriber

    # Clean up buffer when run/sweep completes or fails
    if event_type in ("run_completed", "run_failed", "run_cancelled", "sweep_completed"):
        _cleanup_run(run_id)


def _cleanup_run(run_id: str):
    """Clean up buffer and counter for a completed run (after a delay)."""
    _event_counters.pop(run_id, None)
    # Remove buffer after brief delay to let late reconnectors catch the final event
    import threading
    def _deferred_pop():
        _run_buffers.pop(run_id, None)
        _run_queues.pop(run_id, None)
    threading.Timer(30.0, _deferred_pop).start()


@router.get("/runs/{run_id}")
async def stream_run_events(
    run_id: str,
    lastEventId: str | None = Query(None),
):
    """SSE endpoint for live run progress updates."""
    queue: asyncio.Queue = asyncio.Queue()

    if run_id not in _run_queues:
        _run_queues[run_id] = []
    _run_queues[run_id].append(queue)

    async def event_generator():
        try:
            # Replay missed events from buffer if client provides lastEventId
            if lastEventId is not None:
                try:
                    last_id = int(lastEventId)
                except (ValueError, TypeError):
                    last_id = 0

                buffer = _run_buffers.get(run_id, collections.deque())
                for buffered_event in buffer:
                    buffered_id = int(buffered_event.get("id", 0))
                    if buffered_id > last_id:
                        yield buffered_event

            # Live stream with keepalive
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_TIMEOUT)
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent NAT/proxy timeout
                    yield {"comment": "keepalive"}
        except asyncio.CancelledError:
            pass
        finally:
            if run_id in _run_queues:
                try:
                    _run_queues[run_id].remove(queue)
                except ValueError:
                    pass
                if not _run_queues[run_id]:
                    del _run_queues[run_id]

    return EventSourceResponse(event_generator())
