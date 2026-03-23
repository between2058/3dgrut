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
