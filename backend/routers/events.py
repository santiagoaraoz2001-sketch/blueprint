import asyncio
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/events", tags=["events"])

# In-memory event queues per run
_run_queues: dict[str, list[asyncio.Queue]] = {}


def publish_event(run_id: str, event_type: str, data: dict):
    """Publish an event to all SSE subscribers for a run."""
    if run_id in _run_queues:
        for queue in _run_queues[run_id]:
            queue.put_nowait({"event": event_type, "data": json.dumps(data)})


@router.get("/runs/{run_id}")
async def stream_run_events(run_id: str):
    """SSE endpoint for live run progress updates."""
    queue: asyncio.Queue = asyncio.Queue()

    if run_id not in _run_queues:
        _run_queues[run_id] = []
    _run_queues[run_id].append(queue)

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield event
        except asyncio.CancelledError:
            pass
        finally:
            if run_id in _run_queues:
                _run_queues[run_id].remove(queue)
                if not _run_queues[run_id]:
                    del _run_queues[run_id]

    return EventSourceResponse(event_generator())
