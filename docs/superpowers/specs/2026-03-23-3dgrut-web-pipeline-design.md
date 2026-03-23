# 3DGRUT Web Pipeline — Design Spec

**Date:** 2026-03-23
**Status:** Draft
**Scope:** Web application integrating sharp-frames, COLMAP, 3dgrut training, and frgs mesh into a unified 3D reconstruction pipeline.

---

## 1. Overview

Build a web-based 3D reconstruction pipeline that allows users to upload videos or images and receive a fully trained 3D Gaussian Splatting model with interactive preview, downloadable artifacts, and shareable links.

**Users:** Internal team + external SaaS customers.

**Pipeline:** Video/Images → Frame Selection → SfM → 3DGS Training → Mesh Generation → Preview & Download

---

## 2. Architecture

Two separate codebases, one user-facing flow:

### 2.1 Frontend — phidias-standalone

- New feature branch on the existing `phidias-standalone` repo
- Add `/workspace/reconstruct` route (same pattern as model/image/segment)
- Reuse existing components: SplatViewport, ThreeViewport, workspace layout, Zustand store
- Connect to 3dgrut API via phidias's existing proxy pattern

### 2.2 Backend — 3dgrut API

- New `api/` directory in the existing `3dgrut` repo
- FastAPI service, Dockerized, following `ai-services-unified` patterns
- Will be added to `ai-services-unified` as a git submodule
- Runs on RTX Pro 6000 GPU machine
- CPU-only steps (sharp-frames) run in the same container
- GPU steps (COLMAP, training, meshing) also run in the same container

### 2.3 System Diagram

```
phidias-standalone (Next.js)        3dgrut API (FastAPI, RTX Pro 6000)
┌──────────────────────┐            ┌──────────────────────────────┐
│ /workspace/reconstruct│ ──HTTP──→ │ Job orchestration             │
│   - Upload            │            │ File storage (local/S3)      │
│   - Progress (SSE/WS) │ ←SSE/WS─ │                              │
│   - 3D preview        │            │ CPU: [sharp-frames]          │
│   - Download/Share    │            │ GPU: [colmap] [train] [frgs] │
└──────────────────────┘            └──────────────────────────────┘
```

### 2.4 Proxy Configuration

phidias `next.config.mjs` rewrite:
```javascript
{ source: '/phidias/3dgrut/:path*', destination: `${process.env.THREEDGRUT_API_URL}/:path*` }
```

Environment variable: `THREEDGRUT_API_URL` pointing to the GPU machine.

---

## 3. Pipeline Steps

### Step 1: Frame Extraction (CPU)

- **Tool:** sharp-frames-python
- **Input:** Uploaded video or image folder
- **Output:** `data/{job_id}/images/` — selected sharp frames
- **Config:** fps=10, selection_method=best-n, num_frames=300 (adjustable)
- **Visualization:** SSE progress — frame count, processing status

### Step 2: Camera Model Detection

- **Auto-detect:** Read EXIF/metadata from images to determine lens type
- **Fallback:** If detection fails, pause pipeline and ask user to choose:
  - 「一般鏡頭（手機、單眼）」→ PINHOLE
  - 「廣角/魚眼鏡頭（GoPro、運動相機、360 相機）」→ OPENCV_FISHEYE
- **API:** SSE sends `{"type":"camera_select_required"}`, frontend shows selector, user responds via `POST /jobs/:id/camera_model`

### Step 3: COLMAP SfM (GPU)

- **Tool:** `colmap` binary (apt install, not pycolmap)
- **Steps:** feature_extractor → exhaustive_matcher → mapper
- **Output:** `data/{job_id}/sparse/0/` — cameras.bin, images.bin, points3D.bin
- **Visualization:**
  - Feature extraction/matching: SSE text progress (parsed from stdout)
  - Mapper: Monitor `points3D.bin` file changes, stream sparse point cloud to frontend via WebSocket for live 3D visualization

### Step 4: 3DGRUT Training (GPU)

- **Tool:** `python train.py`
- **Command:**
  ```bash
  python train.py --config-name apps/colmap_3dgut_mcmc.yaml \
    path=data/{job_id} \
    out_dir=data/{job_id}/output \
    experiment_name={job_id} \
    export_ply.enabled=true \
    export_usdz.enabled=true
  ```
- **Output:** `data/{job_id}/output/` — point_cloud.ply, model.usdz
- **Visualization:** Every 500 iterations, headless engine renders a preview image, streamed to frontend via WebSocket
- **Alternative USDZ export:** `python -m threedgrut.export.scripts.ply_to_usd` if needed separately

### Step 5: Mesh Generation (GPU)

- **Tool:** `frgs mesh-dlnr`
- **Command:** `frgs mesh-dlnr point_cloud.ply -o collider.ply 0.10`
- **Output:** `data/{job_id}/output/collider.ply`
- **Visualization:** SSE text progress, preview mesh on completion

---

## 4. 3dgrut API Design

### 4.1 Directory Structure

```
3dgrut/
├── train.py                        # Existing
├── render.py                       # Existing
├── Dockerfile                      # New — follows ai-services-unified pattern
├── requirements-api.txt            # New — API dependencies
├── api/
│   ├── main.py                     # FastAPI app, uvicorn entry
│   ├── config.py                   # Settings (port, storage, redis)
│   ├── logging.py                  # TaiwanFormatter, rotating logs
│   ├── routes/
│   │   ├── jobs.py                 # CRUD, upload, camera model selection
│   │   ├── artifacts.py            # File download, share link creation
│   │   └── stream.py              # SSE progress, WebSocket preview
│   ├── pipeline/
│   │   ├── orchestrator.py         # DAG step orchestration
│   │   ├── steps/
│   │   │   ├── extract_frames.py   # sharp-frames integration
│   │   │   ├── detect_camera.py    # EXIF camera model detection
│   │   │   ├── sfm.py             # COLMAP binary invocation
│   │   │   ├── train.py           # 3dgrut training
│   │   │   └── mesh.py            # frgs mesh-dlnr
│   │   └── queue.py               # Celery/Redis worker management
│   └── storage/
│       └── manager.py             # File storage abstraction (local or S3)
```

### 4.2 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/jobs` | POST | Upload video/images, create reconstruction job |
| `/jobs/:id` | GET | Get job status and metadata |
| `/jobs/:id/events` | GET | SSE — real-time progress stream |
| `/jobs/:id/preview` | WS | WebSocket — training snapshots, live point cloud |
| `/jobs/:id/camera_model` | POST | User selects camera model when auto-detect fails |
| `/jobs/:id/artifacts` | GET | List output files (ply, usdz, mesh) |
| `/jobs/:id/artifacts/:name` | GET | Download specific artifact |
| `/jobs/:id/share` | POST | Generate share token (expirable, revocable) |
| `/share/:token` | GET | Validate share token, return job metadata |
| `/share/:token/artifacts/:name` | GET | Public artifact download |

### 4.3 Job Lifecycle

```
created → extracting → camera_detecting → camera_select_required (optional)
       → sfm_feature → sfm_matching → sfm_mapping → training → meshing → completed
                                                                      ↘ failed
```

### 4.4 SSE Event Types

```json
{"type": "progress", "step": "extracting", "label": "正在挑選清晰畫面...", "percent": 60}
{"type": "step_complete", "step": "extracting", "frame_count": 287}
{"type": "camera_detected", "model": "PINHOLE", "label": "偵測到：一般鏡頭"}
{"type": "camera_select_required"}
{"type": "progress", "step": "sfm_feature", "label": "正在分析圖片特徵...", "current": 45, "total": 287}
{"type": "progress", "step": "sfm_matching", "label": "正在比對圖片...", "percent": 30}
{"type": "progress", "step": "sfm_mapping", "label": "正在建立空間點雲...", "points": 48523}
{"type": "progress", "step": "training", "label": "正在訓練 3D 模型...", "iteration": 13500, "total": 30000}
{"type": "preview", "step": "training", "image_url": "/jobs/{id}/preview/latest"}
{"type": "progress", "step": "meshing", "label": "正在產生碰撞模型..."}
{"type": "step_complete", "step": "meshing"}
{"type": "completed", "artifacts": ["point_cloud.ply", "model.usdz", "collider.ply"]}
{"type": "failed", "step": "sfm_mapping", "error": "Insufficient feature matches"}
```

### 4.5 Docker Configuration

**Dockerfile** — follows ai-services-unified pattern:
```dockerfile
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

ARG TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0;10.0;12.0"
ARG MAX_JOBS=4

RUN apt-get update && apt-get install -y \
    python3.11 python3-pip \
    colmap ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install 3dgrut dependencies + API dependencies
COPY requirements.txt requirements-api.txt ./
RUN pip install -r requirements.txt -r requirements-api.txt

COPY . /app
WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/hf_cache

CMD ["python", "api/main.py"]
```

**docker-compose.yml entry** (for ai-services-unified):
```yaml
3dgrut-api:
  build:
    context: ./3dgrut
    dockerfile: Dockerfile
    args:
      TORCH_CUDA_ARCH_LIST: "${TORCH_CUDA_ARCH_LIST:-8.0;8.6;8.9;9.0;10.0;12.0}"
      MAX_JOBS: "${MAX_JOBS:-4}"
  container_name: 3dgrut-api
  ports:
    - "${THREEDGRUT_PORT:-8191}:8191"
  volumes:
    - ${HF_CACHE_HOST_PATH}:/hf_cache:rw
    - ./logs/3dgrut:/app/logs
    - ${THREEDGRUT_DATA_PATH:-./data/3dgrut}:/app/data
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ["${THREEDGRUT_GPU_ID:-0}"]
            capabilities: [gpu]
  shm_size: "8gb"
  restart: unless-stopped
```

**.env additions:**
```bash
THREEDGRUT_GPU_ID=0
THREEDGRUT_PORT=8191
THREEDGRUT_DATA_PATH=/path/to/persistent/data
```

---

## 5. Frontend — Reconstruct Workspace

### 5.1 New Files in phidias-standalone

```
src/
├── app/workspace/reconstruct/
│   └── page.tsx
├── app/share/[token]/
│   └── page.tsx                    # Public share preview page
├── components/reconstruct/
│   ├── ReconstructPanel.tsx        # Right panel — upload, params, start
│   ├── ReconstructProgress.tsx     # Step timeline with status
│   ├── CameraModelSelector.tsx     # Human-readable camera choice
│   ├── FramePreview.tsx            # Grid of selected frames
│   ├── PointCloudLive.tsx          # Live sparse point cloud (ThreeViewport)
│   ├── TrainingPreview.tsx         # Training snapshot stream
│   ├── ArtifactPanel.tsx           # Download, preview, share buttons
│   └── ShareDialog.tsx             # Generate/manage share links
├── lib/api/
│   └── recon.ts                    # 3dgrut API client
└── store/
    └── recon-store.ts              # Reconstruct workspace Zustand store
```

### 5.2 Page Layout

Follows existing phidias workspace pattern:
- Left: Icon sidebar (adds Reconstruct icon)
- Center: Dynamic viewport that switches based on pipeline stage
- Right: Control panel with upload, camera model, progress timeline, artifacts

### 5.3 Viewport Stages

| Stage | Viewport Content | Component |
|-------|-----------------|-----------|
| Not started | Drag-and-drop upload zone | dropzone |
| Frames extracted | Grid of selected sharp frames | FramePreview |
| SfM running | Live sparse point cloud growing | PointCloudLive (ThreeViewport) |
| Training | Headless render snapshot stream | TrainingPreview |
| Completed | Interactive 3DGS splat preview | SplatViewport (existing) |
| Completed (tab) | Collider mesh preview | ThreeViewport (existing) |

### 5.4 Progress Timeline (Right Panel)

```
✅ 挑選清晰畫面          12 秒
✅ 偵測相機：一般鏡頭
✅ 建立空間點雲           3 分 22 秒
🔄 訓練 3D 模型          45% (13500/30000)
⬜ 產生碰撞模型
```

### 5.5 Share Page

Route: `/share/[token]`

Minimal public page (no login required):
- Phidias logo
- SplatViewport for 3DGS preview
- Tab to switch to mesh view (ThreeViewport)
- Download button for artifacts
- Footer with creation date and CTA

### 5.6 Camera Model Selector (Human-Readable)

When auto-detection fails, present:
- **一般鏡頭**（手機、單眼相機）→ maps to `PINHOLE`
- **廣角/魚眼鏡頭**（GoPro、運動相機、360 相機）→ maps to `OPENCV_FISHEYE`

When auto-detected, display: 「已偵測到：一般鏡頭」(editable)

---

## 6. Data Flow

```
User uploads video/images
  → POST /jobs (multipart)
  → 3dgrut API saves to data/{job_id}/input/
  → Step 1: sharp-frames selects frames → data/{job_id}/images/
  → Step 2: EXIF detection → auto or ask user
  → Step 3: colmap feature_extractor → matcher → mapper → data/{job_id}/sparse/0/
  → Step 4: train.py → data/{job_id}/output/point_cloud.ply + model.usdz
  → Step 5: frgs mesh-dlnr → data/{job_id}/output/collider.ply
  → Job completed → frontend switches to SplatViewport preview
```

### 6.1 Per-Job Data Directory

```
data/{job_id}/
├── input/              # Original upload
├── images/             # Selected sharp frames
├── sparse/0/           # COLMAP output
├── output/             # Final artifacts
│   ├── point_cloud.ply
│   ├── model.usdz
│   └── collider.ply
└── job.json            # Metadata, status, timestamps
```

---

## 7. Real-Time Visualization

### 7.1 COLMAP SfM — Live Point Cloud

- COLMAP mapper writes intermediate results to `sparse/0/points3D.bin`
- File watcher detects changes, reads current point cloud
- Converts to lightweight JSON/binary format
- Streams to frontend via WebSocket
- Frontend renders in ThreeViewport as growing point cloud

### 7.2 3DGRUT Training — Snapshot Stream

- Every 500 iterations, headless engine renders a preview JPEG from a fixed viewpoint
- Pushed to frontend via WebSocket
- Frontend displays as updating image
- Falls back to loss curve chart if GPU memory is tight

### 7.3 Fallback

If real-time visualization adds too much overhead:
- COLMAP: text-only progress (image count, point count)
- Training: text-only progress (iteration, loss value)
- Both always available; visual streaming is enhancement

---

## 8. Security & Sharing

- Share tokens: cryptographically random, unguessable
- Default expiry: 30 days (configurable)
- Users can revoke share links at any time
- Share endpoints only expose artifacts, not job internals
- File uploads validated for format and size limits
