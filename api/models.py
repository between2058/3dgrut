from pydantic import BaseModel
from typing import Optional
from enum import Enum


class HealthResponse(BaseModel):
    status: str
    gpu_busy: bool


class JobStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CAMERA_DETECTING = "camera_detecting"
    CAMERA_SELECT_REQUIRED = "camera_select_required"
    SFM_FEATURE = "sfm_feature"
    SFM_MATCHING = "sfm_matching"
    SFM_MAPPING = "sfm_mapping"
    TRAINING = "training"
    MESHING = "meshing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    created_at: str
    updated_at: str
    user_id: Optional[str] = None
    camera_model: Optional[str] = None
    error: Optional[str] = None
    artifacts: list[str] = []


class CameraModelRequest(BaseModel):
    model: str


class ShareResponse(BaseModel):
    token: str
    url: str
    expires_at: str


class ShareInfoResponse(BaseModel):
    job_id: str
    created_at: str
    artifacts: list[str]
