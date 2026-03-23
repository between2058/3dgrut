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

- **Tool:** sharp-frames-python (`pip install sharp-frames`, pinned in requirements-api.txt)
- **Input:** Uploaded video or image folder
- **Output:** `data/{job_id}/images/` — selected sharp frames
- **Config:** fps=10, selection_method=best-n, num_frames=300 (adjustable)
- **Visualization:** SSE progress — frame count, processing status

### Step 2: Camera Model Detection

- **Auto-detect:** Read EXIF/metadata from images to determine lens type
- **Fallback:** If detection fails, pause pipeline and ask user to choose:
  - 「一般鏡頭（手機、單眼）」→ `SIMPLE_RADIAL` (COLMAP default, robust for standard cameras)
  - 「廣角/魚眼鏡頭（GoPro、運動相機、360 相機）」→ `OPENCV_FISHEYE`
- **Auto-detected always editable:** Display 「已偵測到：一般鏡頭」with option to override
- **API:** SSE sends `{"type":"camera_select_required"}`, frontend shows selector, user responds via `POST /jobs/:id/camera_model`
- **Note:** COLMAP `--ImageReader.camera_model` accepts `SIMPLE_PINHOLE`, `PINHOLE`, `SIMPLE_RADIAL`, `RADIAL`, `OPENCV`, `OPENCV_FISHEYE` etc. We default to `SIMPLE_RADIAL` for robustness; advanced users can override.

### Step 3: COLMAP SfM (GPU)

- **Tool:** `colmap` binary (`apt install colmap`)
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
    out_dir=data/{job_id}/runs \
    experiment_name={job_id} \
    export_ply.enabled=true \
    export_ply.path=data/{job_id}/output/model.ply \
    export_usdz.enabled=true
  ```
- **Output:**
  - `data/{job_id}/output/model.ply` — explicit path via `export_ply.path` to avoid nested timestamped directories
  - USDZ output from `export_usdz.enabled=true`; if path is not controllable, run post-training: `python -m threedgrut.export.scripts.ply_to_usd data/{job_id}/output/model.ply --output_file data/{job_id}/output/model.usdz`
- **Note on output directory:** 3dgrut's trainer appends `{experiment_name}/{object_name}-{timestamp}` to `out_dir`. We set `export_ply.path` explicitly to control the final PLY location. The orchestrator will also scan the `runs/` directory to locate any auto-generated artifacts.
- **Note on USDZ:** This is a supported feature in 3dgrut for Omniverse/Isaac Sim integration. The USDZ format uses a custom extension of UsdVolVolume Schema. See: [NVIDIA USDZ support](https://radiancefields.com/nvidia-adds-usdz-support-to-3dgrut-and-beta-for-omniverse-and-isaac-sim)
- **Visualization:** Custom development required — hook into the training loop to render preview snapshots every ~500 iterations. Two approaches:
  1. **Preferred:** Modify `Trainer3DGRUT` to call a render callback during training, capturing a JPEG from a fixed viewpoint and pushing via WebSocket
  2. **Fallback:** Stream loss/PSNR metrics only, display as a chart on the frontend
  - This is new code, not an existing 3dgrut feature.

### Step 5: Mesh Generation (GPU)

- **Tool:** `frgs mesh-dlnr`
- **Installation:** frgs is an external CLI tool. Must be installed in the Docker image. Installation method and version to be confirmed during implementation. (TODO: document frgs source, install command, license)
- **Command:** `frgs mesh-dlnr data/{job_id}/output/model.ply -o data/{job_id}/output/collider.ply 0.10`
- **Output:** `data/{job_id}/output/collider.ply`
- **Visualization:** SSE text progress, preview mesh on completion

---

## 4. 3dgrut API Design

### 4.1 Directory Structure

```
3dgrut/
├── train.py                        # Existing
├── render.py                       # Existing
├── Dockerfile                      # Existing — extend for API layer
├── requirements-api.txt            # New — API dependencies (fastapi, uvicorn, celery, redis, sharp-frames)
├── api/
│   ├── main.py                     # FastAPI app, uvicorn entry
│   ├── config.py                   # Settings (port, storage, redis)
│   ├── logging.py                  # TaiwanFormatter, rotating logs (app.log, access.log, uvicorn.log)
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
| `/health` | GET | Health check (for Docker/monitoring) |
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
created → queued → extracting → camera_detecting → camera_select_required (optional, paused)
       → sfm_feature → sfm_matching → sfm_mapping → training → meshing → completed
                                                                      ↘ failed (any step)
```

**Concurrency model:**
- GPU steps (COLMAP, training, meshing): max 1 concurrent job (configurable based on GPU VRAM)
- CPU steps (frame extraction): can run concurrently with another job's GPU step
- When GPU is busy, new jobs enter `queued` state with FIFO ordering
- SSE sends queue position: `{"type":"queued","position":2}`
- Queue position updates pushed as jobs complete

### 4.4 SSE Event Types

```json
{"type": "queued", "position": 2, "label": "排隊中，前面還有 2 個任務..."}
{"type": "progress", "step": "extracting", "label": "正在挑選清晰畫面...", "percent": 60}
{"type": "step_complete", "step": "extracting", "frame_count": 287}
{"type": "camera_detected", "model": "SIMPLE_RADIAL", "label": "偵測到：一般鏡頭"}
{"type": "camera_select_required"}
{"type": "progress", "step": "sfm_feature", "label": "正在分析圖片特徵...", "current": 45, "total": 287}
{"type": "progress", "step": "sfm_matching", "label": "正在比對圖片...", "percent": 30}
{"type": "progress", "step": "sfm_mapping", "label": "正在建立空間點雲...", "points": 48523}
{"type": "progress", "step": "training", "label": "正在訓練 3D 模型...", "iteration": 13500, "total": 30000}
{"type": "preview", "step": "training", "image_url": "/jobs/{id}/preview/latest"}
{"type": "progress", "step": "meshing", "label": "正在產生碰撞模型..."}
{"type": "step_complete", "step": "meshing"}
{"type": "completed", "artifacts": ["model.ply", "model.usdz", "collider.ply"]}
{"type": "failed", "step": "sfm_mapping", "error": "Insufficient feature matches"}
```

### 4.5 Docker Configuration

**Dockerfile** — extend the existing 3dgrut Dockerfile which uses conda + `install_env.sh`:

The existing `Dockerfile` in the 3dgrut repo uses `ubuntu:24.04` with Miniconda and `install_env.sh` to compile CUDA extensions (slangtorch, BVH kernels, etc.). The API Dockerfile must preserve this build process and add API-specific layers on top.

```dockerfile
# Start from existing 3dgrut Dockerfile base
# (The existing Dockerfile handles: conda env, CUDA extensions, install_env.sh)

# Additional system packages for the pipeline
RUN apt-get update && apt-get install -y \
    colmap ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install API dependencies into the existing conda env
COPY requirements-api.txt /app/requirements-api.txt
RUN conda run -n 3dgrut pip install -r /app/requirements-api.txt

# Copy API code
COPY api/ /app/api/

ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/hf_cache

CMD ["conda", "run", "-n", "3dgrut", "python", "api/main.py"]
```

> **Implementation note:** The exact Dockerfile will be finalized during implementation by extending the existing multi-stage build. The above is the conceptual approach.

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

### 4.6 Authentication

The 3dgrut API sits behind the phidias proxy. Authentication follows the existing phidias pattern:
- Phidias frontend attaches auth headers (JWT/session token from Zustand store)
- Next.js proxy route forwards these headers to the 3dgrut API
- 3dgrut API validates the token and associates jobs with user identity
- Share endpoints (`/share/:token`) bypass auth — token-based public access

### 4.7 CORS

FastAPI CORS middleware configured to allow:
- The phidias-standalone origin (for direct WebSocket connections that bypass the proxy)
- Configurable via environment variable `ALLOWED_ORIGINS`

### 4.8 Upload Limits

- **Max file size:** 5 GB (configurable via env var)
- **Accepted formats:** Video (mp4, mov, avi, mkv, webm) and images (jpg, png, bmp, tiff)
- **Chunked upload:** Support `tus` or multipart chunked upload for reliability with large files
- **Next.js proxy:** Configure `api.bodyParser.sizeLimit` in next.config.mjs to match
- **Timeout:** Upload endpoint timeout set to 10 minutes for large files

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
| Queued | Queue position + waiting animation | ReconstructProgress |
| Frames extracted | Grid of selected sharp frames | FramePreview |
| SfM running | Live sparse point cloud growing | PointCloudLive (ThreeViewport) |
| Training | Headless render snapshot stream (or loss chart fallback) | TrainingPreview |
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
- **一般鏡頭**（手機、單眼相機）→ maps to `SIMPLE_RADIAL`
- **廣角/魚眼鏡頭**（GoPro、運動相機、360 相機）→ maps to `OPENCV_FISHEYE`

When auto-detected, display: 「已偵測到：一般鏡頭」(editable — user can override)

---

## 6. Data Flow

```
User uploads video/images
  → POST /jobs (multipart/chunked)
  → 3dgrut API saves to data/{job_id}/input/
  → Step 1: sharp-frames selects frames → data/{job_id}/images/
  → Step 2: EXIF detection → auto or ask user
  → Step 3: colmap feature_extractor → matcher → mapper → data/{job_id}/sparse/0/
  → Step 4: train.py → data/{job_id}/output/model.ply + model.usdz
  → Step 5: frgs mesh-dlnr → data/{job_id}/output/collider.ply
  → Job completed → frontend switches to SplatViewport preview
```

### 6.1 Per-Job Data Directory

```
data/{job_id}/
├── input/              # Original upload
├── images/             # Selected sharp frames
├── sparse/0/           # COLMAP output
├── runs/               # 3dgrut training runs (auto-generated nested dirs)
├── output/             # Final artifacts (explicit paths)
│   ├── model.ply
│   ├── model.usdz
│   └── collider.ply
└── job.json            # Metadata, status, timestamps, user_id
```

### 6.2 Data Retention

- **Active jobs:** Kept indefinitely while user account is active
- **Completed jobs:** Retained for 90 days by default (configurable per deployment)
- **Intermediate files** (input video, extracted frames, sparse): Cleaned up 7 days after job completion to save disk space. Only `output/` artifacts are retained long-term.
- **Cleanup job:** A periodic background task scans and removes expired data

---

## 7. Real-Time Visualization

### 7.1 COLMAP SfM — Live Point Cloud

- COLMAP mapper writes intermediate results to `sparse/0/points3D.bin`
- File watcher detects changes, reads current point cloud
- Converts to lightweight JSON/binary format
- Streams to frontend via WebSocket
- Frontend renders in ThreeViewport as growing point cloud

### 7.2 3DGRUT Training — Snapshot Stream

**This requires custom development** — the existing 3dgrut headless engine (`Engine3DGRUT`) is a post-training tool, not integrated into the training loop.

Implementation approach:
1. Add a render callback hook to `Trainer3DGRUT` that fires every N iterations
2. The callback loads current Gaussian parameters, renders a JPEG from a fixed viewpoint
3. Pushes the image via WebSocket to the frontend
4. Frontend displays as an updating preview image

If this proves too resource-intensive or complex:
- **Fallback:** Stream loss/PSNR metrics via SSE, display as a live chart on the frontend
- Both text metrics and visual preview can coexist

### 7.3 Fallback

If real-time visualization adds too much overhead:
- COLMAP: text-only progress (image count, point count)
- Training: text-only progress (iteration, loss value, PSNR)
- Both always available; visual streaming is an enhancement layer

---

## 8. Security & Sharing

- **Authentication:** JWT/session tokens forwarded through phidias proxy, validated by 3dgrut API
- **Share tokens:** Cryptographically random, unguessable
- **Default expiry:** 30 days (configurable)
- **Revocation:** Users can revoke share links at any time
- **Share endpoints:** Only expose artifacts, not job internals or intermediate files
- **Upload validation:** Format whitelist, size limit (5 GB default), virus scanning optional
- **CORS:** Restricted to allowed origins via env var

---

## 9. Open Items (TODO)

Items to resolve during implementation:

1. **frgs mesh-dlnr:** Confirm installation source, package name, version, and license
2. **USDZ export path:** Verify exact output path when `export_usdz.enabled=true` is set; if not controllable, use the post-training `ply_to_usd` script
3. **Training preview hook:** Determine feasibility and GPU memory impact of rendering during training
4. **3dgrut version:** Ensure the deployed version includes USDZ export support (confirmed available in recent releases)
5. **Error recovery:** Define whether users can retry individual failed steps with adjusted parameters (e.g., switch matcher type after SfM failure)
