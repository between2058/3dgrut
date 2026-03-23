import asyncio
import logging
import shutil
from pathlib import Path

from enum import Enum
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

from api.models import JobResponse, CameraModelRequest, JobStatus


class CameraModelEnum(str, Enum):
    SIMPLE_RADIAL = "SIMPLE_RADIAL"
    OPENCV_FISHEYE = "OPENCV_FISHEYE"
    PINHOLE = "PINHOLE"
    SIMPLE_PINHOLE = "SIMPLE_PINHOLE"
from api.pipeline.job_store import JobStore

router = APIRouter()
logger = logging.getLogger("api")

async def _run_pipeline(app, job_id: str):
    queue = app.state.job_queue
    orchestrator = app.state.orchestrator
    bus = app.state.event_bus
    store = app.state.job_store

    pos = queue.position(job_id)
    if pos > 0:
        store.update_status(job_id, "queued")
        await bus.publish(job_id, {
            "type": "queued",
            "position": pos,
            "label": f"排隊中，前面還有 {pos} 個任務...",
        })

    async with queue.acquire_gpu(job_id):
        await orchestrator.run_pipeline(job_id)


ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
ALLOWED_EXT = ALLOWED_VIDEO_EXT | ALLOWED_IMAGE_EXT


def _get_store(request: Request) -> JobStore:
    return JobStore(request.app.state.settings.data_dir)


@router.post("/jobs", status_code=201, response_model=JobResponse)
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    camera_model: CameraModelEnum = Form(
        default=CameraModelEnum.SIMPLE_RADIAL,
        description="一般鏡頭=SIMPLE_RADIAL, 廣角/魚眼=OPENCV_FISHEYE",
    ),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(422, f"Unsupported format: {ext}. Allowed: {ALLOWED_EXT}")

    store = _get_store(request)
    job = store.create(user_id=None, camera_model=camera_model.value)
    job_id = job["id"]

    input_dir = Path(request.app.state.settings.data_dir) / job_id / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    dest = input_dir / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"Job {job_id} created: {file.filename} ({ext}), camera={camera_model.value}")
    asyncio.create_task(_run_pipeline(request.app, job_id))
    return job


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, request: Request):
    store = _get_store(request)
    try:
        job = store.get(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/{job_id}/camera_model", response_model=JobResponse)
async def set_camera_model(job_id: str, body: CameraModelRequest, request: Request):
    store = _get_store(request)
    try:
        job = store.update_fields(job_id, camera_model=body.model)
    except FileNotFoundError:
        raise HTTPException(404, "Job not found")
    logger.info(f"Job {job_id} camera model set to {body.model}")

    # Resume the paused pipeline (orchestrator will be wired in Task 16)
    if hasattr(request.app.state, "orchestrator"):
        request.app.state.orchestrator.resume(job_id)

    return job
