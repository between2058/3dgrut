import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Request

from api.models import JobResponse, CameraModelRequest, JobStatus
from api.pipeline.job_store import JobStore

router = APIRouter()
logger = logging.getLogger("api")

ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
ALLOWED_EXT = ALLOWED_VIDEO_EXT | ALLOWED_IMAGE_EXT


def _get_store(request: Request) -> JobStore:
    return JobStore(request.app.state.settings.data_dir)


@router.post("/jobs", status_code=201, response_model=JobResponse)
async def create_job(request: Request, file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(422, f"Unsupported format: {ext}. Allowed: {ALLOWED_EXT}")

    store = _get_store(request)
    job = store.create(user_id=None)  # TODO: extract from auth header
    job_id = job["id"]

    input_dir = Path(request.app.state.settings.data_dir) / job_id / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    dest = input_dir / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"Job {job_id} created: {file.filename} ({ext})")
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
