# =============================================================================
# 3DGRUT API — Docker Image
#
# Base image    : nvidia/cuda (includes nvcc, cuDNN)
# Python        : 3.11 (deadsnakes PPA)
# PyTorch       : 2.7+ with cu128 (sm_120 / Blackwell support)
#
# Endpoints:
#   POST /jobs                  — Upload video/images, create reconstruction job
#   GET  /jobs/:id              — Get job status
#   GET  /jobs/:id/events       — SSE progress stream
#   WS   /jobs/:id/preview      — WebSocket live preview
#   GET  /jobs/:id/artifacts    — List/download output files
#   GET  /health
#
# Build:
#   docker compose up --build -d
#
# NOTE: First build compiles CUDA extensions (~20-40 min).
# =============================================================================

FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

# ── Build-time arguments ────────────────────────────────────────────────────
ARG MAX_JOBS=4

# ── Proxy (build-time + runtime) ────────────────────────────────────────────
ARG http_proxy=""
ARG https_proxy=""
ARG no_proxy="localhost,127.0.0.1"

ENV http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    HTTP_PROXY=${http_proxy} \
    HTTPS_PROXY=${https_proxy} \
    no_proxy=${no_proxy} \
    NO_PROXY=${no_proxy}

# ── Environment variables ───────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CUDA_HOME=/usr/local/cuda \
    TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;9.0;10.0;12.0" \
    MAX_JOBS=${MAX_JOBS} \
    FORCE_CUDA=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    HF_HOME=/hf_cache

# ── apt proxy config (only takes effect if http_proxy ARG is set) ───────────
RUN if [ -n "${http_proxy}" ]; then \
      printf 'Acquire::http::Proxy "%s";\nAcquire::https::Proxy "%s";\n' \
        "${http_proxy}" "${https_proxy}" \
        > /etc/apt/apt.conf.d/99proxy; \
    fi

# ── System packages ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    # Python 3.11
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    # Build tools
    build-essential \
    gcc-11 g++-11 \
    cmake \
    ninja-build \
    git \
    wget \
    curl \
    # OpenGL / graphics
    libgl1-mesa-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    # Pipeline tools
    colmap \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── Python 3.11 as default + pip ────────────────────────────────────────────
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && python -m ensurepip --upgrade \
    && python -m pip install --upgrade --no-cache-dir pip setuptools wheel

# ── Force gcc-11 for nvcc compatibility ─────────────────────────────────────
ENV CC=/usr/bin/gcc-11 \
    CXX=/usr/bin/g++-11

# ── PyTorch 2.7+ with CUDA 12.8 ────────────────────────────────────────────
RUN pip install --no-cache-dir \
    --pre torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/nightly/cu128

RUN pip install --no-cache-dir --force-reinstall "numpy<2"

# ── Kaolin (build from source for CUDA 12.8) ───────────────────────────────
WORKDIR /tmp/kaolin
RUN git clone --recursive https://github.com/NVIDIAGameWorks/kaolin.git . \
    && pip install --no-cache-dir ninja imageio imageio-ffmpeg \
    && pip install --no-cache-dir \
        -r tools/viz_requirements.txt \
        -r tools/requirements.txt \
        -r tools/build_requirements.txt \
    && IGNORE_TORCH_VER=1 python setup.py install \
    && cd / && rm -rf /tmp/kaolin

# ── 3DGRUT source + dependencies ───────────────────────────────────────────
WORKDIR /workspace
COPY . .

RUN git submodule update --init --recursive \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .

# ── API Layer: Python dependencies ──────────────────────────────────────────
COPY requirements-api.txt /workspace/requirements-api.txt
RUN pip install --no-cache-dir -r /workspace/requirements-api.txt

# ── API Layer: source code ──────────────────────────────────────────────────
COPY api/ /workspace/api/

# Create mount points
RUN mkdir -p /workspace/data /workspace/logs /hf_cache

# ── Port ────────────────────────────────────────────────────────────────────
EXPOSE 8191

# ── Health check ────────────────────────────────────────────────────────────
HEALTHCHECK \
    --interval=30s \
    --timeout=15s \
    --start-period=120s \
    --retries=5 \
    CMD curl -f http://localhost:8191/health || exit 1

# ── Entrypoint ──────────────────────────────────────────────────────────────
CMD ["python", "api/main.py"]
