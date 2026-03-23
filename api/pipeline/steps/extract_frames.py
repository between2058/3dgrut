import logging
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")


class ExtractFramesStep(BaseStep):
    name = "extracting"
    status = JobStatus.EXTRACTING
    label = "正在挑選清晰畫面..."
    needs_gpu = False

    def __init__(self, data_dir: str, fps: int = 10, num_frames: int = 300,
                 method: str = "best-n"):
        self.data_dir = Path(data_dir)
        self.fps = fps
        self.num_frames = num_frames
        self.method = method

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        job_dir = self.data_dir / job_id
        input_dir = job_dir / "input"
        output_dir = job_dir / "images"

        input_files = list(input_dir.iterdir())
        if not input_files:
            return StepResult(success=False, error="No input file found")

        input_path = input_files[0]
        input_type = "video" if input_path.suffix.lower() in {
            ".mp4", ".mov", ".avi", ".mkv", ".webm"
        } else "directory"

        try:
            from sharp_frames import SharpFrames

            processor = SharpFrames(
                input_path=str(input_path),
                input_type=input_type,
                output_dir=str(output_dir),
                fps=self.fps,
                selection_method=self.method,
                num_frames=self.num_frames,
                force_overwrite=True,
            )
            success = await run_in_threadpool(processor.run)

            if not success:
                return StepResult(success=False, error="Frame extraction failed")

            frame_count = len(list(output_dir.glob("frame_*.jpg")))
            logger.info(f"Job {job_id}: extracted {frame_count} frames")
            return StepResult(success=True, data={"frame_count": frame_count})

        except Exception as e:
            return StepResult(success=False, error=f"Frame extraction error: {e}")
