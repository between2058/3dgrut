# Phidias Reconstruct Workspace — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Reconstruct workspace to phidias-standalone that allows users to upload videos/images, monitor real-time 3D reconstruction progress, preview results, download artifacts, and share via public links.

**Architecture:** New `/workspace/reconstruct` route in existing Next.js 14 app, using existing component patterns (SplatViewport, ThreeViewport, workspace layout). Connects to 3dgrut API via phidias proxy rewrite pattern.

**Tech Stack:** Next.js 14, React 18, TypeScript, Zustand, React Three Fiber, SSE (EventSource), WebSocket, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-23-3dgrut-web-pipeline-design.md`

**Prerequisite:** 3dgrut API backend must be running (see `docs/superpowers/plans/2026-03-23-3dgrut-api-backend.md`)

**Working repo:** `/Users/between2058/Documents/code/phidias-standalone` — create feature branch `feat/reconstruct-workspace`

**Reference patterns:**
- Existing workspace: `src/app/workspace/model/`, `src/app/workspace/image/`
- API client: `src/lib/api/phidias.ts`
- Store: `src/store/phidias-store.ts`
- Viewport: `src/components/shared/SplatViewport.tsx`, `src/components/shared/ThreeViewport.tsx`
- Sidebar: `src/components/shared/LeftIconSidebar.tsx`

---

## File Structure

All new files in `phidias-standalone`:

```
src/
├── app/
│   ├── workspace/reconstruct/
│   │   └── page.tsx                        # NEW: Reconstruct workspace route
│   └── share/[token]/
│       └── page.tsx                        # NEW: Public share preview page
├── components/reconstruct/
│   ├── ReconstructPanel.tsx                # NEW: Right panel — upload, params, controls
│   ├── ReconstructProgress.tsx             # NEW: Step timeline with live status
│   ├── CameraModelSelector.tsx             # NEW: Human-readable camera model picker
│   ├── FramePreview.tsx                    # NEW: Grid display of extracted frames
│   ├── PointCloudLive.tsx                  # NEW: Live sparse point cloud via WS
│   ├── TrainingPreview.tsx                 # NEW: Training snapshot stream
│   ├── ArtifactPanel.tsx                   # NEW: Download buttons, format info
│   └── ShareDialog.tsx                     # NEW: Generate/manage share links
├── lib/api/
│   └── recon.ts                            # NEW: 3dgrut API client functions
└── store/
    └── recon-store.ts                      # NEW: Zustand store for reconstruct state
```

Modified existing files:
- `src/components/shared/LeftIconSidebar.tsx` — add Reconstruct icon
- `next.config.mjs` — add proxy rewrite for 3dgrut API
- `.env.example` — add `THREEDGRUT_API_URL`

---

## Task 1: Feature Branch + Proxy Config

**Files:**
- Modify: `next.config.mjs`
- Modify: `.env.example` (or `.env.local`)

- [ ] **Step 1: Create feature branch**

```bash
cd /Users/between2058/Documents/code/phidias-standalone
git checkout main
git pull
git checkout -b feat/reconstruct-workspace
```

- [ ] **Step 2: Add proxy rewrite to next.config.mjs**

Read the existing `next.config.mjs` to find the `rewrites` section. Add:

```javascript
{ source: '/phidias/3dgrut/:path*', destination: `${process.env.THREEDGRUT_API_URL || 'http://localhost:8191'}/:path*` }
```

- [ ] **Step 3: Add env var to .env.example**

```bash
THREEDGRUT_API_URL=http://localhost:8191
```

- [ ] **Step 4: Commit**

```bash
git add next.config.mjs .env.example
git commit -m "feat(reconstruct): add 3dgrut API proxy rewrite"
```

---

## Task 2: API Client

**Files:**
- Create: `src/lib/api/recon.ts`

- [ ] **Step 1: Create the API client**

Follow patterns from `src/lib/api/phidias.ts`.

```typescript
// src/lib/api/recon.ts
const BASE = '/phidias/3dgrut';

export interface Job {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  camera_model: string | null;
  error: string | null;
  artifacts: string[];
}

export interface ShareInfo {
  token: string;
  url: string;
  expires_at: string;
}

export interface SSEEvent {
  type: string;
  step?: string;
  label?: string;
  percent?: number;
  current?: number;
  total?: number;
  points?: number;
  iteration?: number;
  frame_count?: number;
  artifacts?: string[];
  error?: string;
  position?: number;
  image_url?: string;
  model?: string;
  camera_select_required?: boolean;
}

export async function createJob(file: File): Promise<Job> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/jobs`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${BASE}/jobs/${id}`);
  if (!res.ok) throw new Error(`Job not found: ${res.status}`);
  return res.json();
}

export async function setCameraModel(id: string, model: string): Promise<Job> {
  const res = await fetch(`${BASE}/jobs/${id}/camera_model`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  if (!res.ok) throw new Error(`Failed to set camera model: ${res.status}`);
  return res.json();
}

export function subscribeEvents(id: string): EventSource {
  return new EventSource(`${BASE}/jobs/${id}/events`);
}

export function connectPreview(id: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.host;
  return new WebSocket(`${proto}://${host}${BASE}/jobs/${id}/preview`);
}

export async function listArtifacts(id: string): Promise<string[]> {
  const res = await fetch(`${BASE}/jobs/${id}/artifacts`);
  return res.json();
}

export function getArtifactUrl(id: string, name: string): string {
  return `${BASE}/jobs/${id}/artifacts/${name}`;
}

export async function createShareLink(id: string): Promise<ShareInfo> {
  const res = await fetch(`${BASE}/jobs/${id}/share`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to create share link`);
  return res.json();
}

export async function getShareInfo(token: string): Promise<{ job_id: string; artifacts: string[] }> {
  const res = await fetch(`${BASE}/share/${token}`);
  if (!res.ok) throw new Error(`Share link not found`);
  return res.json();
}

export function getSharedArtifactUrl(token: string, name: string): string {
  return `${BASE}/share/${token}/artifacts/${name}`;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/lib/api/recon.ts
git commit -m "feat(reconstruct): add 3dgrut API client"
```

---

## Task 3: Zustand Store

**Files:**
- Create: `src/store/recon-store.ts`

- [ ] **Step 1: Create the store**

Follow patterns from `src/store/phidias-store.ts`.

```typescript
// src/store/recon-store.ts
import { create } from 'zustand';
import type { Job, SSEEvent } from '@/lib/api/recon';

export type PipelineStage =
  | 'idle'
  | 'uploading'
  | 'queued'
  | 'extracting'
  | 'camera_detecting'
  | 'camera_select_required'
  | 'sfm_feature'
  | 'sfm_matching'
  | 'sfm_mapping'
  | 'training'
  | 'meshing'
  | 'completed'
  | 'failed';

export interface StepProgress {
  step: string;
  label: string;
  percent?: number;
  current?: number;
  total?: number;
  startedAt?: number;
  completedAt?: number;
}

interface ReconState {
  // Job
  job: Job | null;
  stage: PipelineStage;
  error: string | null;

  // Progress
  steps: StepProgress[];
  currentStep: string | null;
  queuePosition: number;

  // Camera
  detectedCameraModel: string | null;
  cameraSelectRequired: boolean;

  // Preview
  trainingPreviewUrl: string | null;
  latestIteration: number;
  totalIterations: number;

  // Artifacts
  artifacts: string[];

  // Actions
  setJob: (job: Job) => void;
  setStage: (stage: PipelineStage) => void;
  handleSSEEvent: (event: SSEEvent) => void;
  reset: () => void;
}

const initialState = {
  job: null,
  stage: 'idle' as PipelineStage,
  error: null,
  steps: [],
  currentStep: null,
  queuePosition: 0,
  detectedCameraModel: null,
  cameraSelectRequired: false,
  trainingPreviewUrl: null,
  latestIteration: 0,
  totalIterations: 30000,
  artifacts: [],
};

export const useReconStore = create<ReconState>((set, get) => ({
  ...initialState,

  setJob: (job) => set({ job, stage: job.status as PipelineStage }),

  setStage: (stage) => set({ stage }),

  handleSSEEvent: (event) => {
    const state = get();

    switch (event.type) {
      case 'queued':
        set({ stage: 'queued', queuePosition: event.position ?? 0 });
        break;

      case 'progress':
        set({
          stage: (event.step as PipelineStage) ?? state.stage,
          currentStep: event.step ?? null,
          steps: updateStepProgress(state.steps, event),
          latestIteration: event.iteration ?? state.latestIteration,
          totalIterations: event.total ?? state.totalIterations,
        });
        break;

      case 'step_complete':
        set({
          steps: markStepComplete(state.steps, event.step ?? ''),
        });
        break;

      case 'camera_detected':
        set({ detectedCameraModel: event.model ?? null });
        break;

      case 'camera_select_required':
        set({ stage: 'camera_select_required', cameraSelectRequired: true });
        break;

      case 'preview':
        set({ trainingPreviewUrl: event.image_url ?? null });
        break;

      case 'completed':
        set({ stage: 'completed', artifacts: event.artifacts ?? [] });
        break;

      case 'failed':
        set({ stage: 'failed', error: event.error ?? 'Unknown error' });
        break;
    }
  },

  reset: () => set(initialState),
}));

function updateStepProgress(steps: StepProgress[], event: SSEEvent): StepProgress[] {
  const existing = steps.find((s) => s.step === event.step);
  if (existing) {
    return steps.map((s) =>
      s.step === event.step
        ? { ...s, label: event.label ?? s.label, percent: event.percent, current: event.current, total: event.total }
        : s
    );
  }
  return [
    ...steps,
    {
      step: event.step ?? '',
      label: event.label ?? '',
      percent: event.percent,
      current: event.current,
      total: event.total,
      startedAt: Date.now(),
    },
  ];
}

function markStepComplete(steps: StepProgress[], stepName: string): StepProgress[] {
  return steps.map((s) =>
    s.step === stepName ? { ...s, percent: 100, completedAt: Date.now() } : s
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/store/recon-store.ts
git commit -m "feat(reconstruct): add Zustand store for pipeline state"
```

---

## Task 4: Reconstruct Page + Layout

**Files:**
- Create: `src/app/workspace/reconstruct/page.tsx`
- Modify: `src/components/shared/LeftIconSidebar.tsx`

- [ ] **Step 1: Create the page**

Follow the pattern from `src/app/workspace/model/page.tsx` and `src/app/workspace/image/page.tsx`.

```tsx
// src/app/workspace/reconstruct/page.tsx
'use client';

import { ReconstructPanel } from '@/components/reconstruct/ReconstructPanel';
import { ReconstructViewport } from '@/components/reconstruct/ReconstructViewport';

export default function ReconstructPage() {
  return (
    <div className="flex h-full w-full">
      <div className="flex-1 relative">
        <ReconstructViewport />
      </div>
      <div className="w-[360px] border-l border-white/10 overflow-y-auto">
        <ReconstructPanel />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create ReconstructViewport** (dynamic viewport switcher)

```tsx
// src/components/reconstruct/ReconstructViewport.tsx
'use client';

import { useReconStore } from '@/store/recon-store';
import { FramePreview } from './FramePreview';
import { PointCloudLive } from './PointCloudLive';
import { TrainingPreview } from './TrainingPreview';
// Import existing components
// import { SplatViewport } from '@/components/shared/SplatViewport';
// import { ThreeViewport } from '@/components/shared/ThreeViewport';

export function ReconstructViewport() {
  const stage = useReconStore((s) => s.stage);
  const jobId = useReconStore((s) => s.job?.id);

  if (stage === 'idle' || stage === 'uploading') {
    return <UploadDropzone />;
  }
  if (stage === 'extracting') {
    return <div className="flex items-center justify-center h-full text-white/60">正在挑選清晰畫面...</div>;
  }
  if (stage === 'camera_detecting' || stage === 'camera_select_required') {
    return <FramePreview jobId={jobId!} />;
  }
  if (stage === 'sfm_feature' || stage === 'sfm_matching' || stage === 'sfm_mapping') {
    return <PointCloudLive jobId={jobId!} />;
  }
  if (stage === 'training') {
    return <TrainingPreview jobId={jobId!} />;
  }
  if (stage === 'completed') {
    // TODO: SplatViewport with model.ply / model.usdz
    return <div className="flex items-center justify-center h-full text-white">3D 模型預覽 (TODO: SplatViewport)</div>;
  }
  if (stage === 'failed') {
    return <div className="flex items-center justify-center h-full text-red-400">Pipeline 失敗</div>;
  }

  return <UploadDropzone />;
}

function UploadDropzone() {
  // Placeholder — will be implemented in ReconstructPanel's upload logic
  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center text-white/40">
        <p className="text-lg">拖放影片或圖片到這裡</p>
        <p className="text-sm mt-2">或使用右側面板上傳</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add to sidebar**

Read `src/components/shared/LeftIconSidebar.tsx`, add a Reconstruct icon entry following the existing pattern (model/image/segment icons). Use a suitable Lucide icon like `ScanLine` or `Box`.

- [ ] **Step 4: Commit**

```bash
git add src/app/workspace/reconstruct/ src/components/reconstruct/ReconstructViewport.tsx src/components/shared/LeftIconSidebar.tsx
git commit -m "feat(reconstruct): add workspace page, viewport switcher, sidebar icon"
```

---

## Task 5: ReconstructPanel (Right Panel)

**Files:**
- Create: `src/components/reconstruct/ReconstructPanel.tsx`
- Create: `src/components/reconstruct/ReconstructProgress.tsx`
- Create: `src/components/reconstruct/CameraModelSelector.tsx`

- [ ] **Step 1: Create ReconstructPanel**

```tsx
// src/components/reconstruct/ReconstructPanel.tsx
'use client';

import { useCallback, useRef } from 'react';
import { useReconStore } from '@/store/recon-store';
import { createJob, subscribeEvents, setCameraModel } from '@/lib/api/recon';
import { ReconstructProgress } from './ReconstructProgress';
import { CameraModelSelector } from './CameraModelSelector';
import { ArtifactPanel } from './ArtifactPanel';

export function ReconstructPanel() {
  const { stage, job, cameraSelectRequired, detectedCameraModel, setJob, setStage, handleSSEEvent, reset } = useReconStore();
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = useCallback(async (file: File) => {
    try {
      setStage('uploading');
      const newJob = await createJob(file);
      setJob(newJob);

      // Subscribe to SSE events
      const es = subscribeEvents(newJob.id);
      es.onmessage = (e) => {
        const event = JSON.parse(e.data);
        handleSSEEvent(event);
        if (event.type === 'completed' || event.type === 'failed') {
          es.close();
        }
      };
      es.onerror = () => es.close();
    } catch (err) {
      setStage('failed');
    }
  }, [setJob, setStage, handleSSEEvent]);

  const handleCameraSelect = useCallback(async (model: string) => {
    if (!job) return;
    await setCameraModel(job.id, model);
    // Pipeline will resume automatically after camera model is set
  }, [job]);

  return (
    <div className="p-4 space-y-4">
      <h2 className="text-lg font-semibold text-white">3D 重建</h2>

      {stage === 'idle' && (
        <div>
          <input
            ref={fileRef}
            type="file"
            accept="video/*,image/*"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
          />
          <button
            onClick={() => fileRef.current?.click()}
            className="w-full py-3 px-4 rounded-lg bg-purple-600 hover:bg-purple-500 text-white transition-colors"
          >
            上傳影片或圖片
          </button>
        </div>
      )}

      {(cameraSelectRequired || detectedCameraModel) && (
        <CameraModelSelector
          onSelect={handleCameraSelect}
          detectedModel={detectedCameraModel}
          required={cameraSelectRequired}
        />
      )}

      {stage !== 'idle' && <ReconstructProgress />}

      {stage === 'completed' && job && <ArtifactPanel jobId={job.id} />}

      {stage !== 'idle' && (
        <button
          onClick={reset}
          className="w-full py-2 px-4 rounded-lg border border-white/20 text-white/60 hover:text-white transition-colors"
        >
          新建任務
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create ReconstructProgress**

```tsx
// src/components/reconstruct/ReconstructProgress.tsx
'use client';

import { useReconStore } from '@/store/recon-store';

const STEP_LABELS: Record<string, string> = {
  extracting: '挑選清晰畫面',
  camera_detecting: '偵測相機類型',
  sfm_feature: '分析圖片特徵',
  sfm_matching: '比對圖片',
  sfm_mapping: '建立空間點雲',
  training: '訓練 3D 模型',
  meshing: '產生碰撞模型',
};

export function ReconstructProgress() {
  const { steps, stage, queuePosition, error } = useReconStore();

  return (
    <div className="space-y-2">
      {stage === 'queued' && (
        <div className="text-yellow-400 text-sm">
          排隊中，前面還有 {queuePosition} 個任務...
        </div>
      )}

      {steps.map((step) => (
        <div key={step.step} className="flex items-center gap-2 text-sm">
          <span>
            {step.completedAt ? '✅' : step.step === stage ? '🔄' : '⬜'}
          </span>
          <span className="text-white/80 flex-1">
            {STEP_LABELS[step.step] ?? step.label}
          </span>
          {step.percent != null && !step.completedAt && (
            <span className="text-white/40">{step.percent}%</span>
          )}
          {step.completedAt && step.startedAt && (
            <span className="text-white/30 text-xs">
              {formatDuration(step.completedAt - step.startedAt)}
            </span>
          )}
        </div>
      ))}

      {stage === 'failed' && error && (
        <div className="text-red-400 text-sm mt-2">
          錯誤：{error}
        </div>
      )}
    </div>
  );
}

function formatDuration(ms: number): string {
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m} 分 ${rem} 秒`;
}
```

- [ ] **Step 3: Create CameraModelSelector**

```tsx
// src/components/reconstruct/CameraModelSelector.tsx
'use client';

import { useState } from 'react';

interface Props {
  onSelect: (model: string) => void;
  detectedModel: string | null;
  required: boolean;
}

const OPTIONS = [
  {
    model: 'SIMPLE_RADIAL',
    label: '一般鏡頭',
    description: '手機、單眼相機',
  },
  {
    model: 'OPENCV_FISHEYE',
    label: '廣角/魚眼鏡頭',
    description: 'GoPro、運動相機、360 相機',
  },
];

const MODEL_LABELS: Record<string, string> = {
  SIMPLE_RADIAL: '一般鏡頭',
  OPENCV_FISHEYE: '廣角/魚眼鏡頭',
};

export function CameraModelSelector({ onSelect, detectedModel, required }: Props) {
  const [showOverride, setShowOverride] = useState(false);

  // Auto-detected: show detected model with override option
  if (detectedModel && !required && !showOverride) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between p-3 rounded-lg border border-green-500/30 bg-green-500/5">
          <div>
            <div className="text-sm text-green-400">已偵測到相機類型</div>
            <div className="text-white font-medium">{MODEL_LABELS[detectedModel] ?? detectedModel}</div>
          </div>
          <button
            onClick={() => setShowOverride(true)}
            className="text-white/40 text-sm hover:text-white"
          >
            變更
          </button>
        </div>
      </div>
    );
  }

  // Not detected or user wants to override
  return (
    <div className="space-y-2">
      <p className="text-sm text-yellow-400">
        {required ? '無法自動偵測相機類型，請選擇：' : '選擇相機類型：'}
      </p>
      {OPTIONS.map((opt) => (
        <button
          key={opt.model}
          onClick={() => {
            onSelect(opt.model);
            setShowOverride(false);
          }}
          className="w-full text-left p-3 rounded-lg border border-white/20 hover:border-purple-500 transition-colors"
        >
          <div className="text-white font-medium">{opt.label}</div>
          <div className="text-white/40 text-sm">{opt.description}</div>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add src/components/reconstruct/ReconstructPanel.tsx src/components/reconstruct/ReconstructProgress.tsx src/components/reconstruct/CameraModelSelector.tsx
git commit -m "feat(reconstruct): right panel with upload, progress, camera selector"
```

---

## Task 6: Visualization Components

**Files:**
- Create: `src/components/reconstruct/FramePreview.tsx`
- Create: `src/components/reconstruct/PointCloudLive.tsx`
- Create: `src/components/reconstruct/TrainingPreview.tsx`

- [ ] **Step 1: Create FramePreview**

```tsx
// src/components/reconstruct/FramePreview.tsx
'use client';

import { useEffect, useState } from 'react';
import { getArtifactUrl } from '@/lib/api/recon';
import { useReconStore } from '@/store/recon-store';

interface Props {
  jobId: string;
}

export function FramePreview({ jobId }: Props) {
  const frameCount = useReconStore((s) =>
    s.steps.find((st) => st.step === 'extracting')?.total ?? 0
  );

  // Show a sample of extracted frames (first 20)
  // Frames are stored as frame_00001.jpg, frame_00002.jpg, etc.
  const sampleFrames = Array.from({ length: Math.min(20, frameCount) }, (_, i) => {
    const num = String(i + 1).padStart(5, '0');
    return `frame_${num}.jpg`;
  });

  return (
    <div className="p-4 h-full overflow-y-auto">
      <p className="text-white/60 text-sm mb-3">
        已選出 {frameCount} 張清晰畫面
      </p>
      <div className="grid grid-cols-4 gap-2">
        {sampleFrames.map((name) => (
          <div key={name} className="aspect-video bg-white/5 rounded overflow-hidden">
            <img
              src={`/phidias/3dgrut/jobs/${jobId}/frames/${name}`}  // matches GET /jobs/:id/frames/:name backend endpoint
              alt={name}
              className="w-full h-full object-cover"
              loading="lazy"
            />
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create PointCloudLive**

```tsx
// src/components/reconstruct/PointCloudLive.tsx
'use client';

import { useEffect, useRef, useState } from 'react';
import { connectPreview } from '@/lib/api/recon';

interface Props {
  jobId: string;
}

export function PointCloudLive({ jobId }: Props) {
  const [pointCount, setPointCount] = useState(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const ws = connectPreview(jobId);

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === 'sfm_points') {
        setPointCount(data.count ?? 0);
        // TODO: Render points in ThreeViewport/canvas
      }
    };

    return () => ws.close();
  }, [jobId]);

  return (
    <div className="relative h-full">
      <div className="absolute top-4 left-4 z-10 bg-black/60 rounded px-3 py-1 text-sm text-white/80">
        稀疏點雲：{pointCount.toLocaleString()} 點
      </div>
      <canvas ref={canvasRef} className="w-full h-full" />
      {/* TODO: Replace canvas with ThreeViewport rendering point cloud data */}
    </div>
  );
}
```

- [ ] **Step 3: Create TrainingPreview**

```tsx
// src/components/reconstruct/TrainingPreview.tsx
'use client';

import { useReconStore } from '@/store/recon-store';

interface Props {
  jobId: string;
}

export function TrainingPreview({ jobId }: Props) {
  const previewUrl = useReconStore((s) => s.trainingPreviewUrl);
  const iteration = useReconStore((s) => s.latestIteration);
  const total = useReconStore((s) => s.totalIterations);
  const percent = total > 0 ? Math.round((iteration / total) * 100) : 0;

  return (
    <div className="relative h-full flex items-center justify-center bg-black">
      {previewUrl ? (
        <img
          src={`/phidias/3dgrut${previewUrl}`}
          alt="Training preview"
          className="max-w-full max-h-full object-contain"
        />
      ) : (
        <div className="text-white/40">等待訓練預覽...</div>
      )}
      <div className="absolute bottom-4 left-4 right-4 z-10">
        <div className="bg-black/60 rounded px-3 py-2">
          <div className="flex justify-between text-sm text-white/80 mb-1">
            <span>訓練進度</span>
            <span>{iteration.toLocaleString()} / {total.toLocaleString()} ({percent}%)</span>
          </div>
          <div className="w-full h-1.5 bg-white/10 rounded-full">
            <div
              className="h-full bg-purple-500 rounded-full transition-all"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add src/components/reconstruct/FramePreview.tsx src/components/reconstruct/PointCloudLive.tsx src/components/reconstruct/TrainingPreview.tsx
git commit -m "feat(reconstruct): frame preview, live point cloud, training preview"
```

---

## Task 7: Artifact Panel + Share Dialog

**Files:**
- Create: `src/components/reconstruct/ArtifactPanel.tsx`
- Create: `src/components/reconstruct/ShareDialog.tsx`

- [ ] **Step 1: Create ArtifactPanel**

```tsx
// src/components/reconstruct/ArtifactPanel.tsx
'use client';

import { useState } from 'react';
import { useReconStore } from '@/store/recon-store';
import { getArtifactUrl } from '@/lib/api/recon';
import { ShareDialog } from './ShareDialog';

interface Props {
  jobId: string;
}

const FORMAT_LABELS: Record<string, string> = {
  'model.ply': '3D 高斯模型 (PLY)',
  'model.usdz': 'USDZ 模型',
  'collider.ply': '碰撞模型 (Mesh)',
};

export function ArtifactPanel({ jobId }: Props) {
  const artifacts = useReconStore((s) => s.artifacts);
  const [showShare, setShowShare] = useState(false);

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-white/60">產出檔案</h3>
      {artifacts.map((name) => (
        <a
          key={name}
          href={getArtifactUrl(jobId, name)}
          download={name}
          className="flex items-center justify-between p-2 rounded-lg border border-white/10 hover:border-purple-500 transition-colors"
        >
          <span className="text-white text-sm">{FORMAT_LABELS[name] ?? name}</span>
          <span className="text-white/40 text-xs">下載</span>
        </a>
      ))}
      <button
        onClick={() => setShowShare(true)}
        className="w-full py-2 px-4 rounded-lg bg-white/10 hover:bg-white/20 text-white text-sm transition-colors"
      >
        產生分享連結
      </button>
      {showShare && <ShareDialog jobId={jobId} onClose={() => setShowShare(false)} />}
    </div>
  );
}
```

- [ ] **Step 2: Create ShareDialog**

```tsx
// src/components/reconstruct/ShareDialog.tsx
'use client';

import { useState, useCallback } from 'react';
import { createShareLink } from '@/lib/api/recon';

interface Props {
  jobId: string;
  onClose: () => void;
}

export function ShareDialog({ jobId, onClose }: Props) {
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCreate = useCallback(async () => {
    setLoading(true);
    try {
      const share = await createShareLink(jobId);
      const fullUrl = `${window.location.origin}/share/${share.token}`;
      setShareUrl(fullUrl);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  const handleCopy = useCallback(() => {
    if (shareUrl) {
      navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [shareUrl]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#1a1a2e] rounded-xl p-6 w-[420px] space-y-4">
        <h3 className="text-white font-semibold">分享 3D 模型</h3>

        {!shareUrl ? (
          <button
            onClick={handleCreate}
            disabled={loading}
            className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-50"
          >
            {loading ? '產生中...' : '產生分享連結'}
          </button>
        ) : (
          <div className="space-y-2">
            <input
              readOnly
              value={shareUrl}
              className="w-full bg-white/10 rounded-lg px-3 py-2 text-white text-sm"
            />
            <button
              onClick={handleCopy}
              className="w-full py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white"
            >
              {copied ? '已複製！' : '複製連結'}
            </button>
          </div>
        )}

        <button onClick={onClose} className="w-full py-2 text-white/40 hover:text-white text-sm">
          關閉
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/components/reconstruct/ArtifactPanel.tsx src/components/reconstruct/ShareDialog.tsx
git commit -m "feat(reconstruct): artifact download panel and share dialog"
```

---

## Task 8: Share Page

**Files:**
- Create: `src/app/share/[token]/page.tsx`

- [ ] **Step 1: Create the public share page**

```tsx
// src/app/share/[token]/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { getShareInfo, getSharedArtifactUrl } from '@/lib/api/recon';

interface ShareData {
  job_id: string;
  artifacts: string[];
}

export default function SharePage() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<ShareData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'splat' | 'mesh'>('splat');

  useEffect(() => {
    getShareInfo(token)
      .then(setData)
      .catch(() => setError('分享連結無效或已過期'));
  }, [token]);

  if (error) {
    return (
      <div className="min-h-screen bg-[#0A1E35] flex items-center justify-center">
        <p className="text-white/60">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-[#0A1E35] flex items-center justify-center">
        <p className="text-white/40">載入中...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0A1E35] flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-white/10">
        <span className="text-white font-bold text-lg">Phidias</span>
        <div className="flex gap-2">
          {data.artifacts.map((name) => (
            <a
              key={name}
              href={getSharedArtifactUrl(token, name)}
              download={name}
              className="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm"
            >
              下載 {name.split('.').pop()?.toUpperCase()}
            </a>
          ))}
        </div>
      </header>

      {/* Tab bar */}
      <div className="flex gap-4 px-6 pt-3">
        <button
          onClick={() => setActiveTab('splat')}
          className={`px-3 py-1 rounded text-sm ${activeTab === 'splat' ? 'bg-purple-600 text-white' : 'text-white/40'}`}
        >
          3D 模型
        </button>
        {data.artifacts.includes('collider.ply') && (
          <button
            onClick={() => setActiveTab('mesh')}
            className={`px-3 py-1 rounded text-sm ${activeTab === 'mesh' ? 'bg-purple-600 text-white' : 'text-white/40'}`}
          >
            Mesh
          </button>
        )}
      </div>

      {/* Viewport */}
      <div className="flex-1 p-6">
        <div className="w-full h-full rounded-xl bg-black/40 flex items-center justify-center">
          {/* TODO: Integrate SplatViewport / ThreeViewport with shared artifact URLs */}
          <p className="text-white/40">
            {activeTab === 'splat' ? '3DGS 預覽 (TODO: SplatViewport)' : 'Mesh 預覽 (TODO: ThreeViewport)'}
          </p>
        </div>
      </div>

      {/* Footer */}
      <footer className="px-6 py-4 border-t border-white/10 flex justify-between items-center">
        <span className="text-white/30 text-sm">用 Phidias 建立你的 3D 模型</span>
      </footer>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/app/share/
git commit -m "feat(reconstruct): public share page with artifact downloads"
```

---

## Task 9: Integration Test + Final Polish

- [ ] **Step 1: Run dev server and verify routing**

```bash
cd /Users/between2058/Documents/code/phidias-standalone
pnpm dev
```

Verify:
- `http://localhost:3000/workspace/reconstruct` loads
- Sidebar shows Reconstruct icon
- Upload button appears
- Share page at `/share/test-token` renders (will show error since no real token)

- [ ] **Step 2: Fix any TypeScript errors**

Run: `pnpm build`
Fix any type errors or import issues.

- [ ] **Step 3: Commit final fixes**

```bash
git add -A
git commit -m "feat(reconstruct): fix build issues and polish"
```

---

## Summary

| Task | Component | Key Files |
|------|-----------|-----------|
| 1 | Branch + Proxy | `next.config.mjs` |
| 2 | API Client | `src/lib/api/recon.ts` |
| 3 | Zustand Store | `src/store/recon-store.ts` |
| 4 | Page + Layout | `src/app/workspace/reconstruct/page.tsx` |
| 5 | Right Panel | `ReconstructPanel.tsx`, `ReconstructProgress.tsx`, `CameraModelSelector.tsx` |
| 6 | Visualization | `FramePreview.tsx`, `PointCloudLive.tsx`, `TrainingPreview.tsx` |
| 7 | Artifacts + Share | `ArtifactPanel.tsx`, `ShareDialog.tsx` |
| 8 | Share Page | `src/app/share/[token]/page.tsx` |
| 9 | Integration | Build verification |

**TODO markers** left in code for:
- SplatViewport integration (needs real 3dgrut API running to test with actual .ply/.splat data)
- ThreeViewport point cloud rendering in PointCloudLive
- ThreeViewport mesh rendering in share page
- WebSocket point cloud data format (depends on backend implementation)
