import asyncio
import logging
import re
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
    ]


async def run_training(cmd: list[str], bus=None, job_id: str = "") -> tuple[bool, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stderr_lines = []
    if proc.stdout and bus and job_id:
        async for line in proc.stdout:
            text = line.decode().strip()
            if "Step" in text or "step" in text:
                match = re.search(r"[Ss]tep\s+(\d+)[/|](\d+)", text)
                if match:
                    iteration = int(match.group(1))
                    total = int(match.group(2))
                    await bus.publish(job_id, {
                        "type": "progress",
                        "step": "training",
                        "label": "正在訓練 3D 模型...",
                        "iteration": iteration,
                        "total": total,
                    })

    stderr_data = await proc.stderr.read() if proc.stderr else b""
    await proc.wait()
    return proc.returncode == 0, stderr_data.decode()


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

        bus = context.get("_bus")
        success, stderr = await run_training(cmd, bus=bus, job_id=job_id)
        if not success:
            return StepResult(success=False, error=f"Training failed: {stderr[:500]}")

        ply_path = self.data_dir / job_id / "output" / "model.ply"
        if not ply_path.exists():
            runs_dir = self.data_dir / job_id / "runs"
            found = list(runs_dir.rglob("*.ply")) if runs_dir.exists() else []
            if found:
                import shutil
                shutil.copy2(found[0], ply_path)
                logger.info(f"Job {job_id}: copied PLY from {found[0]}")
            else:
                return StepResult(success=False, error="Training produced no PLY output")

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
