import asyncio
import logging
from pathlib import Path

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}


class ExtractFramesStep(BaseStep):
    name = "extracting"
    status = JobStatus.EXTRACTING
    label = "正在擷取影格..."
    needs_gpu = False

    def __init__(self, data_dir: str, fps: int = 1):
        self.data_dir = Path(data_dir)
        self.fps = fps

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        job_dir = self.data_dir / job_id
        input_dir = job_dir / "input"
        output_dir = job_dir / "images"
        output_dir.mkdir(parents=True, exist_ok=True)

        input_files = list(input_dir.iterdir())
        if not input_files:
            return StepResult(success=False, error="No input file found")

        input_path = input_files[0]
        ext = input_path.suffix.lower()

        # If input is images (not video), just copy/symlink them
        if ext in IMAGE_EXTS:
            return await self._handle_images(job_id, input_dir, output_dir)

        # If input is video, use ffmpeg to extract frames
        if ext in VIDEO_EXTS:
            return await self._extract_with_ffmpeg(job_id, input_path, output_dir)

        return StepResult(success=False, error=f"Unsupported input format: {ext}")

    async def _handle_images(self, job_id: str, input_dir: Path, output_dir: Path) -> StepResult:
        """Input is already images — copy them to images/ directory."""
        import shutil
        count = 0
        for f in sorted(input_dir.iterdir()):
            if f.suffix.lower() in IMAGE_EXTS:
                count += 1
                dest = output_dir / f"frame_{count:05d}{f.suffix}"
                shutil.copy2(f, dest)

        logger.info(f"Job {job_id}: copied {count} images")
        if count == 0:
            return StepResult(success=False, error="No valid images found in input")
        return StepResult(success=True, data={"frame_count": count})

    async def _extract_with_ffmpeg(self, job_id: str, video_path: Path, output_dir: Path) -> StepResult:
        """Extract frames from video using ffmpeg at configured FPS."""
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"fps={self.fps}",
            "-q:v", "2",  # high quality JPEG
            str(output_dir / "frame_%05d.jpg"),
            "-y",  # overwrite
        ]

        logger.info(f"Job {job_id}: extracting frames with ffmpeg (fps={self.fps}): {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"Job {job_id}: ffmpeg failed:\n{output.decode()[-1000:]}")
            return StepResult(success=False, error=f"ffmpeg failed: {output.decode()[-500:]}")

        frame_count = len(list(output_dir.glob("frame_*.jpg")))
        logger.info(f"Job {job_id}: extracted {frame_count} frames from video")

        if frame_count == 0:
            return StepResult(success=False, error="ffmpeg produced no frames")

        return StepResult(success=True, data={"frame_count": frame_count})
