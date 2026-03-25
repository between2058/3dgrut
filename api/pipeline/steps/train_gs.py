import asyncio
import logging
import os
import shutil
from pathlib import Path

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")


def build_train_command(
    job_id: str,
    data_dir: str,
    config: str = "apps/colmap_3dgut_mcmc",
) -> list[str]:
    job_path = os.path.abspath(f"{data_dir}/{job_id}")
    return [
        "python", "train.py",
        f"--config-name={config}",
        f"path={job_path}",
        f"out_dir={job_path}/runs",
        f"experiment_name={job_id}",
        "export_ply.enabled=true",
        f"export_ply.path={job_path}/output/model.ply",
    ]


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
        logger.info(f"Job {job_id}: training command: {' '.join(cmd)}")

        # Verify input data exists
        job_dir = self.data_dir / job_id
        images_dir = job_dir / "images"
        sparse_dir = job_dir / "sparse" / "0"
        image_count = len(list(images_dir.glob("*"))) if images_dir.exists() else 0
        sparse_files = list(sparse_dir.glob("*")) if sparse_dir.exists() else []
        logger.info(f"Job {job_id}: input check — {image_count} images, sparse files: {[f.name for f in sparse_files]}")

        if image_count == 0:
            return StepResult(success=False, error="No images found for training")
        if not sparse_files:
            return StepResult(success=False, error="No sparse reconstruction found for training")

        # Ensure output dir exists
        (job_dir / "output").mkdir(parents=True, exist_ok=True)

        # Run training — use communicate() to avoid stdout/stderr deadlock
        env = os.environ.copy()
        env["HYDRA_FULL_ERROR"] = "1"

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # merge stderr into stdout
            env=env,
        )

        # Read all output (stdout + stderr merged)
        stdout_data, _ = await proc.communicate()
        output = stdout_data.decode() if stdout_data else ""

        # Log the FULL training output so we can see what happened
        logger.info(f"Job {job_id}: training exit code: {proc.returncode}")
        # Log last 3000 chars of output (most important part)
        if output:
            logger.info(f"Job {job_id}: training output (last 3000 chars):\n{output[-3000:]}")

        if proc.returncode != 0:
            return StepResult(success=False, error=f"Training failed (exit {proc.returncode}):\n{output[-2000:]}")

        # Find PLY output
        ply_path = job_dir / "output" / "model.ply"

        if not ply_path.exists():
            # Scan runs/ for auto-generated PLY (export_last.ply or similar)
            runs_dir = job_dir / "runs"
            found = list(runs_dir.rglob("*.ply")) if runs_dir.exists() else []
            logger.info(f"Job {job_id}: PLY not at expected path, scanning runs/: found {[str(f) for f in found]}")
            if found:
                # Pick the largest PLY file (most likely the real model)
                found.sort(key=lambda f: f.stat().st_size, reverse=True)
                ply_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(found[0], ply_path)
                logger.info(f"Job {job_id}: copied PLY from {found[0]} ({found[0].stat().st_size} bytes)")
            else:
                return StepResult(success=False, error="Training produced no PLY output")

        # Validate PLY is not empty
        ply_size = ply_path.stat().st_size
        logger.info(f"Job {job_id}: model.ply size = {ply_size} bytes")
        if ply_size < 1000:
            return StepResult(success=False, error=f"model.ply is suspiciously small ({ply_size} bytes), training likely failed")

        # Try USDZ conversion
        usdz_path = job_dir / "output" / "model.usdz"
        if not usdz_path.exists():
            try:
                logger.info(f"Job {job_id}: attempting ply_to_usd conversion")
                usd_proc = await asyncio.create_subprocess_exec(
                    "python", "-m", "threedgrut.export.scripts.ply_to_usd",
                    str(ply_path),
                    "--output_file", str(usdz_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                usd_output, _ = await usd_proc.communicate()
                if usd_proc.returncode != 0:
                    logger.warning(f"Job {job_id}: ply_to_usd failed: {usd_output.decode()[-500:]}")
                else:
                    logger.info(f"Job {job_id}: USDZ created ({usdz_path.stat().st_size} bytes)")
            except Exception as e:
                logger.warning(f"Job {job_id}: ply_to_usd exception: {e}")

        logger.info(f"Job {job_id}: training step completed")
        return StepResult(success=True)
