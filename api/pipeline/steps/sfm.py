import asyncio
import logging
from pathlib import Path

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")


def build_colmap_commands(
    image_path: str, database_path: str, output_path: str, camera_model: str
) -> list[tuple[list[str], str]]:
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

            bus = context.get("_bus")
            if bus:
                step_labels = {
                    "sfm_feature": "正在分析圖片特徵...",
                    "sfm_matching": "正在比對圖片...",
                    "sfm_mapping": "正在建立空間點雲...",
                }
                await bus.publish(job_id, {
                    "type": "progress",
                    "step": step_name,
                    "label": step_labels.get(step_name, ""),
                })

            success, stderr = await run_colmap_command(cmd, step_name)
            if not success:
                return StepResult(success=False, error=f"COLMAP {step_name} failed: {stderr[:500]}")

        points_file = job_dir / "sparse" / "0" / "points3D.bin"
        if not points_file.exists():
            return StepResult(success=False, error="COLMAP produced no reconstruction")

        logger.info(f"Job {job_id}: SfM completed")
        return StepResult(success=True, data={"sparse_path": str(job_dir / "sparse")})
