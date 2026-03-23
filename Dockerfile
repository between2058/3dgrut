# =============================================================================
# 3DGRUT API — Docker Image
#
# Target hardware : NVIDIA GPU with CUDA support
# Python          : 3.11 (via Miniconda)
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
# NOTE: First build compiles CUDA extensions via install_env.sh (~30-60 min).
# =============================================================================

FROM ubuntu:24.04

# ── Build-time arguments ────────────────────────────────────────────────────
ARG CUDA_VERSION=11.8.0
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
ENV CUDA_VERSION=${CUDA_VERSION} \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    FORCE_CUDA=1 \
    MAX_JOBS=${MAX_JOBS}

# ── apt proxy config (only takes effect if http_proxy ARG is set) ───────────
RUN if [ -n "${http_proxy}" ]; then \
      printf 'Acquire::http::Proxy "%s";\nAcquire::https::Proxy "%s";\n' \
        "${http_proxy}" "${https_proxy}" \
        > /etc/apt/apt.conf.d/99proxy; \
    fi

# ── System packages ────────────────────────────────────────────────────────
RUN apt-get update \
    && apt-get install -y --allow-unauthenticated ca-certificates \
    && apt-get install -y -qq --no-install-recommends \
    wget git curl \
    build-essential \
    gcc-11 g++-11 \
    libgl1-mesa-dev \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ── Miniconda ───────────────────────────────────────────────────────────────
RUN curl -o ~/miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-py311_25.1.1-2-Linux-x86_64.sh && \
    bash ~/miniconda.sh -b -p /opt/conda && \
    rm ~/miniconda.sh && \
    /opt/conda/bin/conda clean -ya
ENV PATH=/opt/conda/bin:$PATH
RUN conda init

# ── 3DGRUT core (CUDA extensions, PyTorch, Kaolin, etc.) ───────────────────
WORKDIR /workspace
COPY . .

RUN CUDA_VERSION=$CUDA_VERSION bash ./install_env.sh 3dgrut WITH_GCC11
RUN echo "conda activate 3dgrut" >> ~/.bashrc

# ── API Layer: system packages ──────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    colmap ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── API Layer: Python dependencies ──────────────────────────────────────────
COPY requirements-api.txt /workspace/requirements-api.txt
RUN conda run -n 3dgrut pip install --no-cache-dir -r /workspace/requirements-api.txt

# ── API Layer: source code ──────────────────────────────────────────────────
COPY api/ /workspace/api/

# Create mount points
RUN mkdir -p /workspace/data /workspace/logs

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
CMD ["conda", "run", "--no-capture-output", "-n", "3dgrut", "python", "api/main.py"]
