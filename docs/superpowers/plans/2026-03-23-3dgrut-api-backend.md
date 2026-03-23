# 3DGRUT API Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FastAPI service layer to the 3dgrut repo that orchestrates the full 3D reconstruction pipeline (sharp-frames → COLMAP → 3dgrut train → frgs mesh) with real-time progress streaming.

**Architecture:** FastAPI app in `api/` directory, using asyncio.Lock for GPU concurrency, Celery+Redis for background job execution, SSE for progress, WebSocket for live preview. Follows ai-services-unified patterns (TaiwanFormatter logging, health check, CORS).

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, Celery, Redis, sharp-frames, COLMAP (binary), Pydantic v2

**Spec:** `docs/superpowers/specs/2026-03-23-3dgrut-web-pipeline-design.md`

**Reference patterns:** `ai-services-unified/qwen-image-edit-2511/qwen_image_api.py` for FastAPI setup, logging, GPU lock, health check.

---

## File Structure

```
3dgrut/
├── requirements-api.txt                    # NEW: API dependencies
├── api/
│   ├── __init__.py                         # NEW: package init
│   ├── main.py                             # NEW: FastAPI app + uvicorn entry
│   ├── config.py                           # NEW: Pydantic Settings
│   ├── logging_config.py                   # NEW: TaiwanFormatter, rotating logs
│   ├── models.py                           # NEW: Pydantic request/response schemas
│   ├── routes/
│   │   ├── __init__.py                     # NEW
│   │   ├── jobs.py                         # NEW: POST /jobs, GET /jobs/:id, POST /jobs/:id/camera_model
│   │   ├── artifacts.py                    # NEW: GET /jobs/:id/artifacts, download, share
│   │   └── stream.py                       # NEW: SSE /jobs/:id/events, WS /jobs/:id/preview
│   ├── pipeline/
│   │   ├── __init__.py                     # NEW
│   │   ├── job_store.py                    # NEW: Job persistence (job.json read/write)
│   │   ├── orchestrator.py                 # NEW: Pipeline step sequencing
│   │   ├── event_bus.py                    # NEW: In-process pub/sub for SSE/WS
│   │   ├── steps/
│   │   │   ├── __init__.py                 # NEW
│   │   │   ├── base.py                     # NEW: Abstract step interface
│   │   │   ├── extract_frames.py           # NEW: sharp-frames
│   │   │   ├── detect_camera.py            # NEW: EXIF detection
│   │   │   ├── sfm.py                      # NEW: COLMAP binary
│   │   │   ├── train_gs.py                 # NEW: 3dgrut train.py
│   │   │   └── mesh.py                     # NEW: frgs mesh-dlnr
│   │   └── queue.py                        # NEW: Celery tasks + GPU lock
│   └── storage/
│       ├── __init__.py                     # NEW
│       └── manager.py                      # NEW: File storage (local, job dirs)
├── api/tests/
│   ├── __init__.py                         # NEW
│   ├── conftest.py                         # NEW: Fixtures (test client, tmp dirs)
│   ├── test_health.py                      # NEW
│   ├── test_job_store.py                   # NEW
│   ├── test_jobs_routes.py                 # NEW
│   ├── test_orchestrator.py                # NEW
│   ├── test_event_bus.py                   # NEW
│   ├── test_extract_frames.py              # NEW
│   ├── test_detect_camera.py               # NEW
│   ├── test_sfm.py                         # NEW
│   ├── test_train_gs.py                    # NEW
│   ├── test_mesh.py                        # NEW
│   ├── test_artifacts.py                   # NEW
│   ├── test_stream.py                      # NEW
│   └── test_share.py                       # NEW
└── Dockerfile                              # MODIFY: extend for API layer
```

---

## Task 1: Dependencies + Project Skeleton

**Files:**
- Create: `requirements-api.txt`
- Create: `api/__init__.py`
- Create: `api/config.py`
- Create: `api/tests/__init__.py`
- Create: `api/tests/conftest.py`

- [ ] **Step 1: Create requirements-api.txt**

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0
pydantic-settings>=2.0
python-multipart>=0.0.9
sse-starlette>=2.0.0
websockets>=12.0
celery[redis]>=5.4.0
redis>=5.0.0
sharp-frames>=0.3.1
Pillow>=10.0.0
exifread>=3.0.0
httpx>=0.27.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: Create api/__init__.py**

Empty file.

- [ ] **Step 3: Create api/config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8191
    host: str = "0.0.0.0"
    data_dir: str = "data"
    log_dir: str = "logs"
    allowed_origins: str = "*"
    max_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB
    redis_url: str = "redis://localhost:6379/0"
    max_gpu_jobs: int = 1
    share_token_expiry_days: int = 30
    cleanup_intermediate_after_days: int = 7
    cleanup_completed_after_days: int = 90

    # Pipeline defaults
    sharp_frames_fps: int = 10
    sharp_frames_num: int = 300
    sharp_frames_method: str = "best-n"
    default_camera_model: str = "SIMPLE_RADIAL"
    train_config: str = "apps/colmap_3dgut_mcmc.yaml"
    train_iterations: int = 30000
    mesh_resolution: float = 0.10

    class Config:
        env_prefix = "THREEDGRUT_"


settings = Settings()
```

- [ ] **Step 4: Create api/tests/conftest.py**

```python
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.config import Settings


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def test_settings(tmp_data_dir, tmp_path):
    return Settings(
        data_dir=str(tmp_data_dir),
        log_dir=str(tmp_path / "logs"),
        redis_url="redis://localhost:6379/15",  # test DB
    )


@pytest.fixture
def app(test_settings):
    """Create FastAPI app with test settings."""
    from api.main import create_app
    return create_app(test_settings)


@pytest.fixture
def client(app):
    return TestClient(app)
```

- [ ] **Step 5: Commit**

```bash
git add requirements-api.txt api/__init__.py api/config.py api/tests/__init__.py api/tests/conftest.py
git commit -m "feat(api): add project skeleton and config"
```

---

## Task 2: Logging Setup

**Files:**
- Create: `api/logging_config.py`

- [ ] **Step 1: Create api/logging_config.py**

Follow the pattern from `qwen_image_api.py`: TaiwanFormatter (UTC+8), TimedRotatingFileHandler (midnight rotation, 14-day retention), separate app.log / access.log / uvicorn.log, health check filter.

```python
import logging
import os
from datetime import datetime, timezone, timedelta
from logging.handlers import TimedRotatingFileHandler

TW_TZ = timezone(timedelta(hours=8))


class TaiwanFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=TW_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return "GET /health" not in msg


def setup_logging(log_dir: str):
    os.makedirs(log_dir, exist_ok=True)
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = TaiwanFormatter(fmt, datefmt=datefmt)

    # App logger
    app_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "app.log"), when="midnight", backupCount=14
    )
    app_handler.setFormatter(formatter)

    app_logger = logging.getLogger("api")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(app_handler)

    # Console
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    app_logger.addHandler(console)

    # Access logger (uvicorn.access)
    access_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "access.log"), when="midnight", backupCount=14
    )
    access_handler.setFormatter(formatter)
    access_handler.addFilter(HealthCheckFilter())

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(access_handler)

    return app_logger
```

- [ ] **Step 2: Commit**

```bash
git add api/logging_config.py
git commit -m "feat(api): add Taiwan-timezone logging setup"
```

---

## Task 3: FastAPI App + Health Endpoint

**Files:**
- Create: `api/main.py`
- Create: `api/models.py`
- Test: `api/tests/test_health.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_health.py
def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "gpu_busy" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/between2058/Documents/code/3dgrut && python -m pytest api/tests/test_health.py -v`
Expected: FAIL (api.main not found)

- [ ] **Step 3: Create api/models.py**

```python
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
    model: str  # SIMPLE_RADIAL, OPENCV_FISHEYE, etc.


class ShareResponse(BaseModel):
    token: str
    url: str
    expires_at: str


class ShareInfoResponse(BaseModel):
    job_id: str
    created_at: str
    artifacts: list[str]
```

- [ ] **Step 4: Create api/main.py**

```python
import asyncio
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import Settings, settings as default_settings
from api.logging_config import setup_logging
from api.models import HealthResponse

gpu_lock = asyncio.Lock()


def create_app(app_settings: Settings | None = None) -> FastAPI:
    s = app_settings or default_settings

    app = FastAPI(title="3DGRUT API")
    app.state.settings = s
    app.state.gpu_lock = gpu_lock

    origins = [o.strip() for o in s.allowed_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        return {"status": "ok", "gpu_busy": gpu_lock.locked()}

    # Import and include routers
    from api.routes.jobs import router as jobs_router
    from api.routes.artifacts import router as artifacts_router
    from api.routes.stream import router as stream_router

    app.include_router(jobs_router)
    app.include_router(artifacts_router)
    app.include_router(stream_router)

    return app


def main():
    logger = setup_logging(default_settings.log_dir)
    logger.info(f"Starting 3DGRUT API on {default_settings.host}:{default_settings.port}")
    app = create_app()
    uvicorn.run(app, host=default_settings.host, port=default_settings.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create stub routers** (so main.py imports don't fail)

```python
# api/routes/__init__.py
# empty

# api/routes/jobs.py
from fastapi import APIRouter
router = APIRouter()

# api/routes/artifacts.py
from fastapi import APIRouter
router = APIRouter()

# api/routes/stream.py
from fastapi import APIRouter
router = APIRouter()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /Users/between2058/Documents/code/3dgrut && python -m pytest api/tests/test_health.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add api/main.py api/models.py api/routes/ api/tests/test_health.py
git commit -m "feat(api): FastAPI app skeleton with health endpoint"
```

---

## Task 4: Job Store (Persistence Layer)

**Files:**
- Create: `api/pipeline/__init__.py`
- Create: `api/pipeline/job_store.py`
- Create: `api/storage/__init__.py`
- Create: `api/storage/manager.py`
- Test: `api/tests/test_job_store.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_job_store.py
import pytest
from api.pipeline.job_store import JobStore
from api.models import JobStatus


def test_create_job(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    job = store.create(user_id="user1")
    assert job["status"] == JobStatus.CREATED
    assert job["user_id"] == "user1"
    assert "id" in job
    assert (tmp_data_dir / job["id"] / "job.json").exists()


def test_get_job(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    job = store.create(user_id="user1")
    loaded = store.get(job["id"])
    assert loaded["id"] == job["id"]
    assert loaded["status"] == JobStatus.CREATED


def test_update_status(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    job = store.create(user_id="user1")
    store.update_status(job["id"], JobStatus.EXTRACTING)
    loaded = store.get(job["id"])
    assert loaded["status"] == JobStatus.EXTRACTING


def test_get_nonexistent_raises(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    with pytest.raises(FileNotFoundError):
        store.get("nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_job_store.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Create api/storage/manager.py**

```python
import os
import shutil
from pathlib import Path


class StorageManager:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def job_dir(self, job_id: str) -> Path:
        return self.data_dir / job_id

    def ensure_job_dirs(self, job_id: str):
        base = self.job_dir(job_id)
        for sub in ["input", "images", "sparse/0", "runs", "output"]:
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base

    def list_artifacts(self, job_id: str) -> list[str]:
        output_dir = self.job_dir(job_id) / "output"
        if not output_dir.exists():
            return []
        return [f.name for f in output_dir.iterdir() if f.is_file()]

    def artifact_path(self, job_id: str, name: str) -> Path:
        path = self.job_dir(job_id) / "output" / name
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {name}")
        return path
```

- [ ] **Step 4: Create api/pipeline/job_store.py**

```python
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from api.models import JobStatus
from api.storage.manager import StorageManager

TW_TZ = timezone(timedelta(hours=8))


class JobStore:
    def __init__(self, data_dir: str):
        self.storage = StorageManager(data_dir)

    def create(self, user_id: str | None = None) -> dict:
        job_id = uuid.uuid4().hex[:12]
        now = datetime.now(TW_TZ).isoformat()
        job = {
            "id": job_id,
            "status": JobStatus.CREATED,
            "user_id": user_id,
            "camera_model": None,
            "error": None,
            "artifacts": [],
            "created_at": now,
            "updated_at": now,
        }
        self.storage.ensure_job_dirs(job_id)
        self._save(job)
        return job

    def get(self, job_id: str) -> dict:
        path = self._job_file(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job not found: {job_id}")
        with open(path) as f:
            return json.load(f)

    def update_status(self, job_id: str, status: JobStatus, **fields):
        job = self.get(job_id)
        job["status"] = status
        job["updated_at"] = datetime.now(TW_TZ).isoformat()
        job.update(fields)
        self._save(job)
        return job

    def update_fields(self, job_id: str, **fields):
        job = self.get(job_id)
        job["updated_at"] = datetime.now(TW_TZ).isoformat()
        job.update(fields)
        self._save(job)
        return job

    def _job_file(self, job_id: str) -> Path:
        return self.storage.job_dir(job_id) / "job.json"

    def _save(self, job: dict):
        path = self._job_file(job["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(job, f, indent=2, default=str)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest api/tests/test_job_store.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/pipeline/ api/storage/ api/tests/test_job_store.py
git commit -m "feat(api): job store and storage manager"
```

---

## Task 5: Event Bus (In-Process Pub/Sub)

SSE and WebSocket routes need to subscribe to pipeline events. An in-process event bus decouples the pipeline steps from the HTTP layer.

**Files:**
- Create: `api/pipeline/event_bus.py`
- Test: `api/tests/test_event_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_event_bus.py
import asyncio
import pytest
from api.pipeline.event_bus import EventBus


@pytest.mark.asyncio
async def test_subscribe_and_publish():
    bus = EventBus()
    events = []

    async def collect():
        async for event in bus.subscribe("job1"):
            events.append(event)
            if event.get("type") == "completed":
                break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)

    await bus.publish("job1", {"type": "progress", "percent": 50})
    await bus.publish("job1", {"type": "completed"})
    await task

    assert len(events) == 2
    assert events[0]["type"] == "progress"
    assert events[1]["type"] == "completed"


@pytest.mark.asyncio
async def test_no_crosstalk():
    bus = EventBus()
    events = []

    async def collect():
        async for event in bus.subscribe("job1"):
            events.append(event)
            break

    task = asyncio.create_task(collect())
    await asyncio.sleep(0.05)

    await bus.publish("job2", {"type": "other_job"})
    await bus.publish("job1", {"type": "mine"})
    await task

    assert len(events) == 1
    assert events[0]["type"] == "mine"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_event_bus.py -v`
Expected: FAIL

- [ ] **Step 3: Implement event bus**

```python
# api/pipeline/event_bus.py
import asyncio
from collections import defaultdict
from typing import AsyncIterator


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, job_id: str, event: dict):
        for queue in self._subscribers.get(job_id, []):
            await queue.put(event)

    async def subscribe(self, job_id: str) -> AsyncIterator[dict]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[job_id].append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers[job_id].remove(queue)
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_event_bus.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/pipeline/event_bus.py api/tests/test_event_bus.py
git commit -m "feat(api): in-process event bus for SSE/WebSocket"
```

---

## Task 6: Job Routes (Upload + CRUD)

**Files:**
- Modify: `api/routes/jobs.py`
- Test: `api/tests/test_jobs_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_jobs_routes.py
import io


def test_create_job_with_video(client, tmp_data_dir):
    fake_video = io.BytesIO(b"fake video content")
    resp = client.post(
        "/jobs",
        files={"file": ("test.mp4", fake_video, "video/mp4")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["status"] == "created"


def test_create_job_rejects_bad_format(client):
    fake = io.BytesIO(b"not a video")
    resp = client.post(
        "/jobs",
        files={"file": ("test.txt", fake, "text/plain")},
    )
    assert resp.status_code == 422


def test_get_job(client, tmp_data_dir):
    fake_video = io.BytesIO(b"fake video content")
    create_resp = client.post(
        "/jobs",
        files={"file": ("test.mp4", fake_video, "video/mp4")},
    )
    job_id = create_resp.json()["id"]

    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


def test_get_nonexistent_job(client):
    resp = client.get("/jobs/nonexistent")
    assert resp.status_code == 404


def test_set_camera_model(client, tmp_data_dir):
    fake_video = io.BytesIO(b"fake video content")
    create_resp = client.post(
        "/jobs",
        files={"file": ("test.mp4", fake_video, "video/mp4")},
    )
    job_id = create_resp.json()["id"]

    resp = client.post(f"/jobs/{job_id}/camera_model", json={"model": "OPENCV_FISHEYE"})
    assert resp.status_code == 200

    job = client.get(f"/jobs/{job_id}").json()
    assert job["camera_model"] == "OPENCV_FISHEYE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_jobs_routes.py -v`
Expected: FAIL

- [ ] **Step 3: Implement jobs router**

```python
# api/routes/jobs.py
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse

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
    return job
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_jobs_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/jobs.py api/tests/test_jobs_routes.py
git commit -m "feat(api): job upload, CRUD, and camera model selection"
```

---

## Task 7: SSE Progress Streaming

**Files:**
- Modify: `api/routes/stream.py`
- Test: `api/tests/test_stream.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_stream.py
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from api.pipeline.event_bus import EventBus


@pytest.mark.asyncio
async def test_sse_receives_events(app):
    bus = EventBus()
    app.state.event_bus = bus

    # Create a job first
    from api.pipeline.job_store import JobStore
    store = JobStore(app.state.settings.data_dir)
    job = store.create()
    job_id = job["id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Publish events in background
        async def publish():
            await asyncio.sleep(0.1)
            await bus.publish(job_id, {"type": "progress", "step": "extracting", "percent": 50})
            await bus.publish(job_id, {"type": "completed", "artifacts": []})

        asyncio.create_task(publish())

        async with ac.stream("GET", f"/jobs/{job_id}/events") as resp:
            assert resp.status_code == 200
            lines = []
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    lines.append(line)
                if len(lines) >= 2:
                    break

        assert len(lines) == 2
        assert "extracting" in lines[0]
```

- [ ] **Step 2: Implement SSE route**

```python
# api/routes/stream.py
import json
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

from api.pipeline.event_bus import EventBus

router = APIRouter()
logger = logging.getLogger("api")


def _get_bus(request) -> EventBus:
    if not hasattr(request.app.state, "event_bus"):
        request.app.state.event_bus = EventBus()
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
```

- [ ] **Step 3: Initialize event bus in create_app**

Add to `api/main.py` inside `create_app()`, after `app.state.gpu_lock`:
```python
from api.pipeline.event_bus import EventBus
app.state.event_bus = EventBus()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_stream.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/stream.py api/tests/test_stream.py api/main.py
git commit -m "feat(api): SSE progress streaming and WebSocket preview"
```

---

## Task 8: Pipeline Step Interface + Orchestrator

**Files:**
- Create: `api/pipeline/steps/__init__.py`
- Create: `api/pipeline/steps/base.py`
- Create: `api/pipeline/orchestrator.py`
- Test: `api/tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_orchestrator.py
import asyncio
import pytest
from api.pipeline.orchestrator import PipelineOrchestrator
from api.pipeline.steps.base import BaseStep, StepResult
from api.pipeline.event_bus import EventBus
from api.pipeline.job_store import JobStore
from api.models import JobStatus


class FakeStepA(BaseStep):
    name = "step_a"
    status = JobStatus.EXTRACTING
    label = "Running step A..."

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        return StepResult(success=True, data={"a": 1})


class FakeStepB(BaseStep):
    name = "step_b"
    status = JobStatus.TRAINING
    label = "Running step B..."

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        return StepResult(success=True, data={"b": 2})


class FailingStep(BaseStep):
    name = "failing"
    status = JobStatus.SFM_MAPPING
    label = "Failing..."

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        return StepResult(success=False, error="Something broke")


@pytest.mark.asyncio
async def test_runs_steps_in_order(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    bus = EventBus()
    orch = PipelineOrchestrator(store, bus, steps=[FakeStepA(), FakeStepB()])

    job = store.create()
    await orch.run_pipeline(job["id"])

    final = store.get(job["id"])
    assert final["status"] == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_stops_on_failure(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    bus = EventBus()
    orch = PipelineOrchestrator(store, bus, steps=[FakeStepA(), FailingStep(), FakeStepB()])

    job = store.create()
    await orch.run_pipeline(job["id"])

    final = store.get(job["id"])
    assert final["status"] == JobStatus.FAILED
    assert "Something broke" in final["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_orchestrator.py -v`

- [ ] **Step 3: Implement base step and orchestrator**

```python
# api/pipeline/steps/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from api.models import JobStatus


@dataclass
class StepResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseStep(ABC):
    name: str = ""
    status: JobStatus = JobStatus.CREATED
    label: str = ""
    needs_gpu: bool = False

    @abstractmethod
    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        """Execute this pipeline step. Return StepResult."""
        ...
```

```python
# api/pipeline/orchestrator.py
import logging
from api.pipeline.job_store import JobStore
from api.pipeline.event_bus import EventBus
from api.pipeline.steps.base import BaseStep
from api.models import JobStatus

logger = logging.getLogger("api")


class PipelineOrchestrator:
    def __init__(self, store: JobStore, bus: EventBus, steps: list[BaseStep]):
        self.store = store
        self.bus = bus
        self.steps = steps

    async def run_pipeline(self, job_id: str):
        context: dict = {}

        for step in self.steps:
            job = self.store.get(job_id)
            self.store.update_status(job_id, step.status)
            await self.bus.publish(job_id, {
                "type": "progress",
                "step": step.name,
                "label": step.label,
            })

            logger.info(f"Job {job_id}: starting step '{step.name}'")

            try:
                result = await step.run(job_id, job, context)
            except Exception as e:
                logger.error(f"Job {job_id}: step '{step.name}' exception: {e}")
                self.store.update_status(job_id, JobStatus.FAILED, error=str(e))
                await self.bus.publish(job_id, {
                    "type": "failed",
                    "step": step.name,
                    "error": str(e),
                })
                return

            if not result.success:
                logger.warning(f"Job {job_id}: step '{step.name}' failed: {result.error}")
                self.store.update_status(job_id, JobStatus.FAILED, error=result.error)
                await self.bus.publish(job_id, {
                    "type": "failed",
                    "step": step.name,
                    "error": result.error,
                })
                return

            context.update(result.data)
            await self.bus.publish(job_id, {
                "type": "step_complete",
                "step": step.name,
                **result.data,
            })

        # All steps done
        artifacts = self.store.storage.list_artifacts(job_id)
        self.store.update_status(job_id, JobStatus.COMPLETED, artifacts=artifacts)
        await self.bus.publish(job_id, {
            "type": "completed",
            "artifacts": artifacts,
        })
        logger.info(f"Job {job_id}: pipeline completed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_orchestrator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/pipeline/steps/ api/pipeline/orchestrator.py api/tests/test_orchestrator.py
git commit -m "feat(api): pipeline orchestrator with step interface"
```

---

## Task 9: Step — Frame Extraction

**Files:**
- Create: `api/pipeline/steps/extract_frames.py`
- Test: `api/tests/test_extract_frames.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_extract_frames.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from api.pipeline.steps.extract_frames import ExtractFramesStep
from api.pipeline.steps.base import StepResult


@pytest.mark.asyncio
async def test_extract_frames_calls_sharp_frames(tmp_data_dir):
    job_id = "testjob"
    job_dir = tmp_data_dir / job_id
    (job_dir / "input").mkdir(parents=True)
    (job_dir / "images").mkdir(parents=True)

    # Create a fake video file
    (job_dir / "input" / "video.mp4").write_bytes(b"fake")

    step = ExtractFramesStep(data_dir=str(tmp_data_dir))

    with patch("api.pipeline.steps.extract_frames.SharpFrames") as MockSF:
        mock_instance = MagicMock()
        mock_instance.run.return_value = True
        MockSF.return_value = mock_instance

        result = await step.run(job_id, {"id": job_id}, {})

        assert result.success
        MockSF.assert_called_once()
        call_kwargs = MockSF.call_args
        assert "video.mp4" in str(call_kwargs)
```

- [ ] **Step 2: Implement**

```python
# api/pipeline/steps/extract_frames.py
import logging
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")


class ExtractFramesStep(BaseStep):
    name = "extracting"
    status = JobStatus.EXTRACTING
    label = "正在挑選清晰畫面..."
    needs_gpu = False

    def __init__(self, data_dir: str, fps: int = 10, num_frames: int = 300,
                 method: str = "best-n"):
        self.data_dir = Path(data_dir)
        self.fps = fps
        self.num_frames = num_frames
        self.method = method

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        job_dir = self.data_dir / job_id
        input_dir = job_dir / "input"
        output_dir = job_dir / "images"

        # Find input file
        input_files = list(input_dir.iterdir())
        if not input_files:
            return StepResult(success=False, error="No input file found")

        input_path = input_files[0]
        input_type = "video" if input_path.suffix.lower() in {
            ".mp4", ".mov", ".avi", ".mkv", ".webm"
        } else "directory"

        try:
            from sharp_frames import SharpFrames

            processor = SharpFrames(
                input_path=str(input_path),
                input_type=input_type,
                output_dir=str(output_dir),
                fps=self.fps,
                selection_method=self.method,
                num_frames=self.num_frames,
                force_overwrite=True,
            )
            success = await run_in_threadpool(processor.run)

            if not success:
                return StepResult(success=False, error="Frame extraction failed")

            frame_count = len(list(output_dir.glob("frame_*.jpg")))
            logger.info(f"Job {job_id}: extracted {frame_count} frames")
            return StepResult(success=True, data={"frame_count": frame_count})

        except Exception as e:
            return StepResult(success=False, error=f"Frame extraction error: {e}")
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest api/tests/test_extract_frames.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add api/pipeline/steps/extract_frames.py api/tests/test_extract_frames.py
git commit -m "feat(api): frame extraction step (sharp-frames)"
```

---

## Task 10: Step — Camera Detection

**Files:**
- Create: `api/pipeline/steps/detect_camera.py`
- Test: `api/tests/test_detect_camera.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_detect_camera.py
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from api.pipeline.steps.detect_camera import DetectCameraStep, detect_from_exif


def _make_image_dir(tmp_data_dir, job_id="testjob"):
    img_dir = tmp_data_dir / job_id / "images"
    img_dir.mkdir(parents=True)
    # Create a fake jpeg with no EXIF
    (img_dir / "frame_00001.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    return img_dir


def test_detect_from_exif_no_data(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0fake")
    assert detect_from_exif(str(img)) is None


@pytest.mark.asyncio
async def test_step_defaults_when_no_exif(tmp_data_dir):
    job_id = "testjob"
    _make_image_dir(tmp_data_dir, job_id)

    step = DetectCameraStep(data_dir=str(tmp_data_dir), default_model="SIMPLE_RADIAL")
    result = await step.run(job_id, {"id": job_id, "camera_model": None}, {})

    # No EXIF → should request user selection
    assert result.success
    assert result.data.get("camera_select_required") is True


@pytest.mark.asyncio
async def test_step_uses_preset_camera_model(tmp_data_dir):
    job_id = "testjob"
    _make_image_dir(tmp_data_dir, job_id)

    step = DetectCameraStep(data_dir=str(tmp_data_dir), default_model="SIMPLE_RADIAL")
    result = await step.run(job_id, {"id": job_id, "camera_model": "OPENCV_FISHEYE"}, {})

    assert result.success
    assert result.data["camera_model"] == "OPENCV_FISHEYE"
    assert result.data.get("camera_select_required") is None
```

- [ ] **Step 2: Implement**

```python
# api/pipeline/steps/detect_camera.py
import logging
from pathlib import Path

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")

FISHEYE_KEYWORDS = {"gopro", "hero", "insta360", "dji action", "fisheye", "360"}


def detect_from_exif(image_path: str) -> str | None:
    try:
        import exifread
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        model = str(tags.get("Image Model", "")).lower()
        lens = str(tags.get("EXIF LensModel", "")).lower()
        combined = f"{model} {lens}"

        for kw in FISHEYE_KEYWORDS:
            if kw in combined:
                return "OPENCV_FISHEYE"

        if model or lens:
            return "SIMPLE_RADIAL"

        return None
    except Exception:
        return None


class DetectCameraStep(BaseStep):
    name = "camera_detecting"
    status = JobStatus.CAMERA_DETECTING
    label = "正在偵測相機類型..."
    needs_gpu = False

    def __init__(self, data_dir: str, default_model: str = "SIMPLE_RADIAL"):
        self.data_dir = Path(data_dir)
        self.default_model = default_model

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        # If user already set camera model, use it
        if job.get("camera_model"):
            logger.info(f"Job {job_id}: using preset camera model {job['camera_model']}")
            return StepResult(success=True, data={"camera_model": job["camera_model"]})

        # Try EXIF detection
        images_dir = self.data_dir / job_id / "images"
        sample_images = list(images_dir.glob("*.jpg"))[:5]

        detected = None
        for img in sample_images:
            detected = detect_from_exif(str(img))
            if detected:
                break

        if detected:
            logger.info(f"Job {job_id}: auto-detected camera model: {detected}")
            return StepResult(success=True, data={"camera_model": detected})

        # Cannot detect → ask user
        logger.info(f"Job {job_id}: camera model not detected, requesting user input")
        return StepResult(success=True, data={"camera_select_required": True})
```

- [ ] **Step 3: Run test, commit**

Run: `python -m pytest api/tests/test_detect_camera.py -v`

```bash
git add api/pipeline/steps/detect_camera.py api/tests/test_detect_camera.py
git commit -m "feat(api): camera model detection step (EXIF)"
```

---

## Task 11: Step — COLMAP SfM

**Files:**
- Create: `api/pipeline/steps/sfm.py`
- Test: `api/tests/test_sfm.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sfm.py
import pytest
from unittest.mock import patch, AsyncMock
from api.pipeline.steps.sfm import ColmapSfmStep, build_colmap_commands


def test_build_commands():
    cmds = build_colmap_commands(
        image_path="/data/job1/images",
        database_path="/data/job1/database.db",
        output_path="/data/job1/sparse",
        camera_model="SIMPLE_RADIAL",
    )
    assert len(cmds) == 3
    assert "feature_extractor" in cmds[0][0]
    assert "exhaustive_matcher" in cmds[1][0]
    assert "mapper" in cmds[2][0]
    assert "--ImageReader.camera_model" in " ".join(cmds[0][0])
    assert "SIMPLE_RADIAL" in " ".join(cmds[0][0])


@pytest.mark.asyncio
async def test_sfm_step_builds_correct_commands(tmp_data_dir):
    job_id = "testjob"
    job_dir = tmp_data_dir / job_id
    (job_dir / "images").mkdir(parents=True)
    (job_dir / "sparse" / "0").mkdir(parents=True)

    step = ColmapSfmStep(data_dir=str(tmp_data_dir))

    with patch("api.pipeline.steps.sfm.run_colmap_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (True, "")
        result = await step.run(
            job_id,
            {"id": job_id},
            {"camera_model": "SIMPLE_RADIAL"},
        )

    assert result.success
    assert mock_run.call_count == 3  # 3 COLMAP commands
```

- [ ] **Step 2: Implement**

```python
# api/pipeline/steps/sfm.py
import asyncio
import logging
import re
from pathlib import Path

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")


def build_colmap_commands(
    image_path: str, database_path: str, output_path: str, camera_model: str
) -> list[tuple[list[str], str]]:
    """Returns list of (command_args, step_name) tuples."""
    return [
        (
            [
                "colmap", "feature_extractor",
                "--database_path", database_path,
                "--image_path", image_path,
                "--ImageReader.camera_model", camera_model,
                "--ImageReader.single_camera", "1",
            ],
            "sfm_feature",
        ),
        (
            [
                "colmap", "exhaustive_matcher",
                "--database_path", database_path,
            ],
            "sfm_matching",
        ),
        (
            [
                "colmap", "mapper",
                "--database_path", database_path,
                "--image_path", image_path,
                "--output_path", output_path,
            ],
            "sfm_mapping",
        ),
    ]


async def run_colmap_command(cmd: list[str], step_name: str) -> tuple[bool, str]:
    """Run a COLMAP command, return (success, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    success = proc.returncode == 0
    if not success:
        logger.error(f"COLMAP {step_name} failed: {stderr.decode()}")
    return success, stderr.decode()


class ColmapSfmStep(BaseStep):
    name = "sfm"
    status = JobStatus.SFM_FEATURE
    label = "正在建立空間點雲..."
    needs_gpu = True

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        job_dir = self.data_dir / job_id
        camera_model = context.get("camera_model", "SIMPLE_RADIAL")

        image_path = str(job_dir / "images")
        database_path = str(job_dir / "database.db")
        output_path = str(job_dir / "sparse")

        commands = build_colmap_commands(image_path, database_path, output_path, camera_model)

        for cmd, step_name in commands:
            logger.info(f"Job {job_id}: running COLMAP {step_name}")
            success, stderr = await run_colmap_command(cmd, step_name)
            if not success:
                return StepResult(success=False, error=f"COLMAP {step_name} failed: {stderr[:500]}")

        # Check output
        points_file = job_dir / "sparse" / "0" / "points3D.bin"
        if not points_file.exists():
            return StepResult(success=False, error="COLMAP produced no reconstruction")

        logger.info(f"Job {job_id}: SfM completed")
        return StepResult(success=True, data={"sparse_path": str(job_dir / "sparse")})
```

- [ ] **Step 3: Run test, commit**

Run: `python -m pytest api/tests/test_sfm.py -v`

```bash
git add api/pipeline/steps/sfm.py api/tests/test_sfm.py
git commit -m "feat(api): COLMAP SfM step with command builder"
```

---

## Task 12: Step — 3DGRUT Training

**Files:**
- Create: `api/pipeline/steps/train_gs.py`
- Test: `api/tests/test_train_gs.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_train_gs.py
import pytest
from unittest.mock import patch, AsyncMock
from api.pipeline.steps.train_gs import TrainGsStep, build_train_command


def test_build_train_command():
    cmd = build_train_command(
        job_id="abc123",
        data_dir="/data",
        config="apps/colmap_3dgut_mcmc.yaml",
    )
    assert "train.py" in cmd[1]
    assert "apps/colmap_3dgut_mcmc.yaml" in cmd
    assert "export_ply.enabled=true" in cmd
    assert "export_usdz.enabled=true" in cmd
    assert any("export_ply.path=" in arg for arg in cmd)


@pytest.mark.asyncio
async def test_train_step_runs(tmp_data_dir):
    job_id = "testjob"
    (tmp_data_dir / job_id / "sparse" / "0").mkdir(parents=True)
    (tmp_data_dir / job_id / "output").mkdir(parents=True)

    step = TrainGsStep(data_dir=str(tmp_data_dir))

    with patch("api.pipeline.steps.train_gs.run_training", new_callable=AsyncMock) as mock:
        mock.return_value = (True, "")
        result = await step.run(job_id, {"id": job_id}, {})

    assert result.success
    mock.assert_called_once()
```

- [ ] **Step 2: Implement**

```python
# api/pipeline/steps/train_gs.py
import asyncio
import logging
from pathlib import Path

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")


def build_train_command(
    job_id: str,
    data_dir: str,
    config: str = "apps/colmap_3dgut_mcmc.yaml",
) -> list[str]:
    job_path = f"{data_dir}/{job_id}"
    return [
        "python", "train.py",
        f"--config-name={config}",
        f"path={job_path}",
        f"out_dir={job_path}/runs",
        f"experiment_name={job_id}",
        "export_ply.enabled=true",
        f"export_ply.path={job_path}/output/model.ply",
        "export_usdz.enabled=true",
    ]


async def run_training(cmd: list[str]) -> tuple[bool, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode == 0, stderr.decode()


class TrainGsStep(BaseStep):
    name = "training"
    status = JobStatus.TRAINING
    label = "正在訓練 3D 模型..."
    needs_gpu = True

    def __init__(self, data_dir: str, config: str = "apps/colmap_3dgut_mcmc.yaml"):
        self.data_dir = Path(data_dir)
        self.config = config

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        cmd = build_train_command(job_id, str(self.data_dir), self.config)
        logger.info(f"Job {job_id}: starting training")

        success, stderr = await run_training(cmd)
        if not success:
            return StepResult(success=False, error=f"Training failed: {stderr[:500]}")

        # Verify output
        ply_path = self.data_dir / job_id / "output" / "model.ply"
        if not ply_path.exists():
            # Scan runs/ for auto-generated PLY
            runs_dir = self.data_dir / job_id / "runs"
            found = list(runs_dir.rglob("*.ply")) if runs_dir.exists() else []
            if found:
                import shutil
                shutil.copy2(found[0], ply_path)
                logger.info(f"Job {job_id}: copied PLY from {found[0]}")
            else:
                return StepResult(success=False, error="Training produced no PLY output")

        # Try USDZ fallback if not produced by training
        usdz_path = self.data_dir / job_id / "output" / "model.usdz"
        if not usdz_path.exists():
            logger.info(f"Job {job_id}: running ply_to_usd conversion")
            usd_cmd = [
                "python", "-m", "threedgrut.export.scripts.ply_to_usd",
                str(ply_path),
                "--output_file", str(usdz_path),
            ]
            usd_proc = await asyncio.create_subprocess_exec(
                *usd_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await usd_proc.communicate()

        logger.info(f"Job {job_id}: training completed")
        return StepResult(success=True)
```

- [ ] **Step 3: Run test, commit**

Run: `python -m pytest api/tests/test_train_gs.py -v`

```bash
git add api/pipeline/steps/train_gs.py api/tests/test_train_gs.py
git commit -m "feat(api): 3dgrut training step with USDZ fallback"
```

---

## Task 13: Step — Mesh Generation

**Files:**
- Create: `api/pipeline/steps/mesh.py`
- Test: `api/tests/test_mesh.py`

- [ ] **Step 1: Write test + implement**

```python
# api/tests/test_mesh.py
import pytest
from unittest.mock import patch, AsyncMock
from api.pipeline.steps.mesh import MeshStep, build_mesh_command


def test_build_mesh_command():
    cmd = build_mesh_command("/data/job1/output/model.ply", "/data/job1/output/collider.ply", 0.10)
    assert cmd == ["frgs", "mesh-dlnr", "/data/job1/output/model.ply", "-o", "/data/job1/output/collider.ply", "0.10"]


@pytest.mark.asyncio
async def test_mesh_step(tmp_data_dir):
    job_id = "testjob"
    output_dir = tmp_data_dir / job_id / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "model.ply").write_bytes(b"fake ply")

    step = MeshStep(data_dir=str(tmp_data_dir))

    with patch("api.pipeline.steps.mesh.run_mesh", new_callable=AsyncMock) as mock:
        mock.return_value = (True, "")
        result = await step.run(job_id, {"id": job_id}, {})

    assert result.success
```

```python
# api/pipeline/steps/mesh.py
import asyncio
import logging
from pathlib import Path

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")


def build_mesh_command(ply_path: str, output_path: str, resolution: float = 0.10) -> list[str]:
    return ["frgs", "mesh-dlnr", ply_path, "-o", output_path, str(resolution)]


async def run_mesh(cmd: list[str]) -> tuple[bool, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode == 0, stderr.decode()


class MeshStep(BaseStep):
    name = "meshing"
    status = JobStatus.MESHING
    label = "正在產生碰撞模型..."
    needs_gpu = True

    def __init__(self, data_dir: str, resolution: float = 0.10):
        self.data_dir = Path(data_dir)
        self.resolution = resolution

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        ply_path = self.data_dir / job_id / "output" / "model.ply"
        collider_path = self.data_dir / job_id / "output" / "collider.ply"

        if not ply_path.exists():
            return StepResult(success=False, error="model.ply not found for meshing")

        cmd = build_mesh_command(str(ply_path), str(collider_path), self.resolution)
        logger.info(f"Job {job_id}: generating collider mesh")

        success, stderr = await run_mesh(cmd)
        if not success:
            return StepResult(success=False, error=f"Mesh generation failed: {stderr[:500]}")

        logger.info(f"Job {job_id}: mesh generation completed")
        return StepResult(success=True)
```

- [ ] **Step 2: Run test, commit**

Run: `python -m pytest api/tests/test_mesh.py -v`

```bash
git add api/pipeline/steps/mesh.py api/tests/test_mesh.py
git commit -m "feat(api): mesh generation step (frgs mesh-dlnr)"
```

---

## Task 14: Artifacts Routes

**Files:**
- Modify: `api/routes/artifacts.py`
- Test: `api/tests/test_artifacts.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_artifacts.py
from pathlib import Path


def _setup_job_with_artifacts(client, tmp_data_dir):
    """Create a job and put fake artifacts in output/."""
    import io
    resp = client.post("/jobs", files={"file": ("test.mp4", io.BytesIO(b"fake"), "video/mp4")})
    job_id = resp.json()["id"]

    output_dir = tmp_data_dir / job_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model.ply").write_bytes(b"ply content")
    (output_dir / "model.usdz").write_bytes(b"usdz content")
    return job_id


def test_list_artifacts(client, tmp_data_dir):
    job_id = _setup_job_with_artifacts(client, tmp_data_dir)
    resp = client.get(f"/jobs/{job_id}/artifacts")
    assert resp.status_code == 200
    names = resp.json()
    assert "model.ply" in names
    assert "model.usdz" in names


def test_download_artifact(client, tmp_data_dir):
    job_id = _setup_job_with_artifacts(client, tmp_data_dir)
    resp = client.get(f"/jobs/{job_id}/artifacts/model.ply")
    assert resp.status_code == 200
    assert resp.content == b"ply content"


def test_download_missing_artifact(client, tmp_data_dir):
    job_id = _setup_job_with_artifacts(client, tmp_data_dir)
    resp = client.get(f"/jobs/{job_id}/artifacts/nonexistent.ply")
    assert resp.status_code == 404
```

- [ ] **Step 2: Implement**

```python
# api/routes/artifacts.py
import secrets
import json
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
```

- [ ] **Step 3: Run test, commit**

Run: `python -m pytest api/tests/test_artifacts.py -v`

```bash
git add api/routes/artifacts.py api/tests/test_artifacts.py
git commit -m "feat(api): artifact listing, download, and share system"
```

---

## Task 15: Queue Management (GPU Lock)

**Files:**
- Create: `api/pipeline/queue.py`
- Test: `api/tests/test_queue.py`

- [ ] **Step 1: Write test + implement**

The queue wraps pipeline execution with GPU locking and job queuing. For v1, use asyncio.Lock + asyncio.Queue instead of Celery (simpler, can upgrade later).

```python
# api/tests/test_queue.py
import asyncio
import pytest
from api.pipeline.queue import JobQueue


@pytest.mark.asyncio
async def test_queue_fifo_order():
    queue = JobQueue(max_gpu_jobs=1)
    order = []

    async def job(name):
        async with queue.acquire_gpu():
            order.append(name)
            await asyncio.sleep(0.05)

    await asyncio.gather(job("a"), job("b"), job("c"))
    assert order == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_queue_position():
    queue = JobQueue(max_gpu_jobs=1)
    assert queue.position("any") == 0
```

```python
# api/pipeline/queue.py
import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger("api")


class JobQueue:
    def __init__(self, max_gpu_jobs: int = 1):
        self._semaphore = asyncio.Semaphore(max_gpu_jobs)
        self._waiting: list[str] = []

    @asynccontextmanager
    async def acquire_gpu(self, job_id: str = ""):
        self._waiting.append(job_id)
        try:
            await self._semaphore.acquire()
            self._waiting.remove(job_id) if job_id in self._waiting else None
            yield
        finally:
            self._semaphore.release()

    def position(self, job_id: str) -> int:
        try:
            return self._waiting.index(job_id)
        except ValueError:
            return 0

    @property
    def gpu_busy(self) -> bool:
        return self._semaphore._value == 0
```

- [ ] **Step 2: Run test, commit**

Run: `python -m pytest api/tests/test_queue.py -v`

```bash
git add api/pipeline/queue.py api/tests/test_queue.py
git commit -m "feat(api): GPU job queue with semaphore-based concurrency"
```

---

## Task 16: Wire Everything Together

Connect the pipeline steps, queue, and orchestrator into the job creation flow.

**Files:**
- Modify: `api/main.py` — register pipeline components on app state
- Modify: `api/routes/jobs.py` — trigger pipeline after job creation

- [ ] **Step 1: Update main.py to assemble pipeline**

Add after router includes in `create_app()`:

```python
from api.pipeline.job_store import JobStore
from api.pipeline.queue import JobQueue
from api.pipeline.orchestrator import PipelineOrchestrator
from api.pipeline.steps.extract_frames import ExtractFramesStep
from api.pipeline.steps.detect_camera import DetectCameraStep
from api.pipeline.steps.sfm import ColmapSfmStep
from api.pipeline.steps.train_gs import TrainGsStep
from api.pipeline.steps.mesh import MeshStep

app.state.job_store = JobStore(s.data_dir)
app.state.job_queue = JobQueue(max_gpu_jobs=s.max_gpu_jobs)
app.state.orchestrator = PipelineOrchestrator(
    store=app.state.job_store,
    bus=app.state.event_bus,
    steps=[
        ExtractFramesStep(
            data_dir=s.data_dir,
            fps=s.sharp_frames_fps,
            num_frames=s.sharp_frames_num,
            method=s.sharp_frames_method,
        ),
        DetectCameraStep(data_dir=s.data_dir, default_model=s.default_camera_model),
        ColmapSfmStep(data_dir=s.data_dir),
        TrainGsStep(data_dir=s.data_dir, config=s.train_config),
        MeshStep(data_dir=s.data_dir, resolution=s.mesh_resolution),
    ],
)
```

- [ ] **Step 2: Update jobs.py to launch pipeline as background task**

Add to `create_job()` after file save:

```python
import asyncio

# Launch pipeline in background
asyncio.create_task(_run_pipeline(request.app, job_id))

# At module level:
async def _run_pipeline(app, job_id: str):
    queue = app.state.job_queue
    orchestrator = app.state.orchestrator
    bus = app.state.event_bus

    async with queue.acquire_gpu(job_id):
        await orchestrator.run_pipeline(job_id)
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest api/tests/ -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add api/main.py api/routes/jobs.py
git commit -m "feat(api): wire pipeline steps into job creation flow"
```

---

## Task 17: Dockerfile Extension

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Read the existing Dockerfile**

Read: `/Users/between2058/Documents/code/3dgrut/Dockerfile`

- [ ] **Step 2: Append API layer to existing Dockerfile**

Add at the end of the existing Dockerfile (after `install_env.sh` has run):

```dockerfile
# === API Layer ===
RUN apt-get update && apt-get install -y --no-install-recommends \
    colmap ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt /workspace/requirements-api.txt
RUN conda run -n 3dgrut pip install --no-cache-dir -r /workspace/requirements-api.txt

COPY api/ /workspace/api/

EXPOSE 8191

CMD ["conda", "run", "--no-capture-output", "-n", "3dgrut", "python", "api/main.py"]
```

- [ ] **Step 3: Test build** (on a machine with Docker)

Run: `docker build -t 3dgrut-api .`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add Dockerfile requirements-api.txt
git commit -m "feat(api): extend Dockerfile for API service layer"
```

---

## Task 18: Final Integration Smoke Test

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest api/tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Start the server locally** (if Redis is available)

Run: `python api/main.py`
Test: `curl http://localhost:8191/health`
Expected: `{"status":"ok","gpu_busy":false}`

- [ ] **Step 3: Commit any fixes, tag milestone**

```bash
git add -A
git commit -m "feat(api): complete 3dgrut API backend v1"
```

---

## Summary

| Task | Component | Key Files |
|------|-----------|-----------|
| 1 | Skeleton + Config | `requirements-api.txt`, `api/config.py` |
| 2 | Logging | `api/logging_config.py` |
| 3 | Health + App | `api/main.py`, `api/models.py` |
| 4 | Job Store | `api/pipeline/job_store.py`, `api/storage/manager.py` |
| 5 | Event Bus | `api/pipeline/event_bus.py` |
| 6 | Job Routes | `api/routes/jobs.py` |
| 7 | SSE/WebSocket | `api/routes/stream.py` |
| 8 | Orchestrator | `api/pipeline/orchestrator.py`, `api/pipeline/steps/base.py` |
| 9 | Frame Extraction | `api/pipeline/steps/extract_frames.py` |
| 10 | Camera Detection | `api/pipeline/steps/detect_camera.py` |
| 11 | COLMAP SfM | `api/pipeline/steps/sfm.py` |
| 12 | 3dgrut Training | `api/pipeline/steps/train_gs.py` |
| 13 | Mesh Generation | `api/pipeline/steps/mesh.py` |
| 14 | Artifacts + Share | `api/routes/artifacts.py` |
| 15 | GPU Queue | `api/pipeline/queue.py` |
| 16 | Wire Together | `api/main.py`, `api/routes/jobs.py` |
| 17 | Dockerfile | `Dockerfile` |
| 18 | Smoke Test | All |
