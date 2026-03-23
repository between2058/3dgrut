import secrets
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api.models import ShareResponse, ShareInfoResponse
from api.pipeline.job_store import JobStore
from api.storage.manager import StorageManager

router = APIRouter()
logger = logging.getLogger("api")
TW_TZ = timezone(timedelta(hours=8))

# In-memory share store (replace with Redis/DB for production)
_shares: dict[str, dict] = {}


@router.get("/jobs/{job_id}/artifacts")
async def list_artifacts(job_id: str, request: Request):
    storage = StorageManager(request.app.state.settings.data_dir)
    try:
        return storage.list_artifacts(job_id)
    except Exception:
        raise HTTPException(404, "Job not found")


@router.get("/jobs/{job_id}/artifacts/{name}")
async def download_artifact(job_id: str, name: str, request: Request):
    storage = StorageManager(request.app.state.settings.data_dir)
    try:
        path = storage.artifact_path(job_id, name)
    except FileNotFoundError:
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path, filename=name)


@router.get("/jobs/{job_id}/frames/{name}")
async def get_frame(job_id: str, name: str, request: Request):
    storage = StorageManager(request.app.state.settings.data_dir)
    frame_path = storage.job_dir(job_id) / "images" / name
    if not frame_path.exists():
        raise HTTPException(404, "Frame not found")
    return FileResponse(frame_path, filename=name)


@router.post("/jobs/{job_id}/share", response_model=ShareResponse)
async def create_share(job_id: str, request: Request):
    store = JobStore(request.app.state.settings.data_dir)
    try:
        store.get(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job not found")

    token = secrets.token_urlsafe(32)
    expiry_days = request.app.state.settings.share_token_expiry_days
    expires_at = datetime.now(TW_TZ) + timedelta(days=expiry_days)

    _shares[token] = {
        "job_id": job_id,
        "created_at": datetime.now(TW_TZ).isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    logger.info(f"Job {job_id}: share token created (expires {expires_at.date()})")
    return {
        "token": token,
        "url": f"/share/{token}",
        "expires_at": expires_at.isoformat(),
    }


@router.get("/share/{token}", response_model=ShareInfoResponse)
async def get_share(token: str, request: Request):
    share = _shares.get(token)
    if not share:
        raise HTTPException(404, "Share link not found or expired")

    expires = datetime.fromisoformat(share["expires_at"])
    if datetime.now(TW_TZ) > expires:
        del _shares[token]
        raise HTTPException(410, "Share link expired")

    storage = StorageManager(request.app.state.settings.data_dir)
    artifacts = storage.list_artifacts(share["job_id"])

    return {
        "job_id": share["job_id"],
        "created_at": share["created_at"],
        "artifacts": artifacts,
    }


@router.get("/share/{token}/artifacts/{name}")
async def download_shared_artifact(token: str, name: str, request: Request):
    share = _shares.get(token)
    if not share:
        raise HTTPException(404, "Share link not found")

    storage = StorageManager(request.app.state.settings.data_dir)
    try:
        path = storage.artifact_path(share["job_id"], name)
    except FileNotFoundError:
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path, filename=name)
