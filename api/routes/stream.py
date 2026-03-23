import json
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from api.pipeline.event_bus import EventBus

router = APIRouter()
logger = logging.getLogger("api")


def _get_bus(request) -> EventBus:
    return request.app.state.event_bus


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request):
    bus = _get_bus(request)

    async def event_generator():
        async for event in bus.subscribe(job_id):
            yield {"data": json.dumps(event, ensure_ascii=False)}
            if event.get("type") in ("completed", "failed"):
                break

    return EventSourceResponse(event_generator())


@router.websocket("/jobs/{job_id}/preview")
async def job_preview(websocket: WebSocket, job_id: str):
    await websocket.accept()
    bus = _get_bus(websocket)

    try:
        async for event in bus.subscribe(job_id):
            if event.get("type") == "preview":
                await websocket.send_json(event)
            elif event.get("type") in ("completed", "failed"):
                await websocket.send_json(event)
                break
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job {job_id}")
