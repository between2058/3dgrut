import asyncio
import logging
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")


def run_pycolmap(image_path: str, database_path: str, output_path: str, camera_model: str):
    """Run SfM pipeline using pycolmap (no GUI, no OpenGL)."""
    import pycolmap

    reader_options = pycolmap.ImageReaderOptions()
    reader_options.camera_model = camera_model
    reader_options.single_camera = True

    pycolmap.extract_features(
        database_path=database_path,
        image_path=image_path,
        camera_mode=pycolmap.CameraMode.SINGLE,
        reader_options=reader_options,
    )

    pycolmap.match_exhaustive(database_path=database_path)

    maps = pycolmap.incremental_mapping(
        database_path=database_path,
        image_path=image_path,
        output_path=output_path,
    )

    return maps


class ColmapSfmStep(BaseStep):
    name = "sfm"
    status = JobStatus.SFM_FEATURE
    label = "正在建立空間點雲..."
    needs_gpu = True

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        job_dir = self.data_dir / job_id
        camera_model = job.get("camera_model") or context.get("camera_model", "SIMPLE_RADIAL")

        image_path = str(job_dir / "images")
        database_path = str(job_dir / "database.db")
        output_path = str(job_dir / "sparse")

        bus = context.get("_bus")

        try:
            if bus:
                await bus.publish(job_id, {
                    "type": "progress",
                    "step": "sfm_feature",
                    "label": "正在分析圖片特徵...",
                })

            logger.info(f"Job {job_id}: running pycolmap SfM (camera={camera_model})")
            maps = await run_in_threadpool(
                run_pycolmap, image_path, database_path, output_path, camera_model
            )

            if bus:
                await bus.publish(job_id, {
                    "type": "step_complete",
                    "step": "sfm",
                })

        except Exception as e:
            logger.error(f"Job {job_id}: pycolmap failed: {e}")
            return StepResult(success=False, error=f"SfM failed: {e}")

        points_file = job_dir / "sparse" / "0" / "points3D.bin"
        if not points_file.exists():
            return StepResult(success=False, error="SfM produced no reconstruction")

        logger.info(f"Job {job_id}: SfM completed")
        return StepResult(success=True, data={"sparse_path": str(job_dir / "sparse")})
