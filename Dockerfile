# =============================================================================
# 3DGRUT API — Docker Image
#
# Base: nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04
# Python: 3.11 via deadsnakes PPA
# PyTorch: nightly cu128 (Blackwell sm_120 support)
# CUDA extensions: JIT compiled on first training run (needs runtime GPU)
#
# Build:
#   docker compose build --no-cache
#   docker compose up -d
# =============================================================================

FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

# ── Build args ──────────────────────────────────────────────────────────────
ARG MAX_JOBS=4
ARG http_proxy=""
ARG https_proxy=""
ARG no_proxy="localhost,127.0.0.1"

# ── Proxy (build + runtime) ────────────────────────────────────────────────
ENV http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    HTTP_PROXY=${http_proxy} \
    HTTPS_PROXY=${https_proxy} \
    no_proxy=${no_proxy} \
    NO_PROXY=${no_proxy}

# ── Core environment ────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    CUDA_HOME=/usr/local/cuda \
    TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;9.0;10.0;12.0" \
    MAX_JOBS=${MAX_JOBS} \
    FORCE_CUDA=1 \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    CC=/usr/bin/gcc-11 \
    CXX=/usr/bin/g++-11 \
    HF_HOME=/hf_cache

# ── apt proxy ──────────────────────────────────────────────────────────────
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
    python3.11 python3.11-dev python3.11-venv python3.11-distutils \
    build-essential gcc-11 g++-11 \
    cmake ninja-build \
    git wget curl \
    libgl1-mesa-dev libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── Python 3.11 ────────────────────────────────────────────────────────────
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && pip install --upgrade --no-cache-dir pip setuptools wheel

# ── PyTorch cu128 ──────────────────────────────────────────────────────────
RUN pip install --no-cache-dir \
    --pre torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/nightly/cu128 \
    && pip install --no-cache-dir --force-reinstall "numpy<2"

# ── Kaolin (from source) ───────────────────────────────────────────────────
RUN cd /tmp \
    && git clone --recursive https://github.com/NVIDIAGameWorks/kaolin.git \
    && cd kaolin \
    && pip install --no-cache-dir ninja imageio imageio-ffmpeg \
    && pip install --no-cache-dir --ignore-installed \
        -r tools/viz_requirements.txt \
        -r tools/requirements.txt \
        -r tools/build_requirements.txt \
    && IGNORE_TORCH_VER=1 python setup.py install \
    && cd / && rm -rf /tmp/kaolin

# ── 3DGRUT source ──────────────────────────────────────────────────────────
WORKDIR /workspace
COPY . .

# Git submodules (tiny-cuda-nn headers, optix-dev)
RUN git submodule update --init --recursive

# Python deps (--no-build-isolation: fused-ssim needs torch at build time)
RUN pip install --no-cache-dir --no-build-isolation -r requirements.txt \
    && pip install --no-cache-dir --no-build-isolation -e .

# ── API Layer ───────────────────────────────────────────────────────────────
RUN pip install --no-cache-dir -r requirements-api.txt

RUN mkdir -p /workspace/data /workspace/logs /hf_cache

EXPOSE 8191

ENV PYTHONPATH=/workspace

HEALTHCHECK --interval=30s --timeout=15s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:8191/health || exit 1

CMD ["python", "api/main.py"]
