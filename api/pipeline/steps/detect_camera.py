import logging
from pathlib import Path

from api.models import JobStatus
from api.pipeline.steps.base import BaseStep, StepResult

logger = logging.getLogger("api")

FISHEYE_KEYWORDS = {"gopro", "hero", "insta360", "dji action", "fisheye", "360"}


def detect_from_exif(image_path: str) -> str | None:
    try:
        import exifread
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        model = str(tags.get("Image Model", "")).lower()
        lens = str(tags.get("EXIF LensModel", "")).lower()
        combined = f"{model} {lens}"

        for kw in FISHEYE_KEYWORDS:
            if kw in combined:
                return "OPENCV_FISHEYE"

        if model or lens:
            return "SIMPLE_RADIAL"

        return None
    except Exception:
        return None


class DetectCameraStep(BaseStep):
    name = "camera_detecting"
    status = JobStatus.CAMERA_DETECTING
    label = "正在偵測相機類型..."
    needs_gpu = False

    def __init__(self, data_dir: str, default_model: str = "SIMPLE_RADIAL"):
        self.data_dir = Path(data_dir)
        self.default_model = default_model

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        if job.get("camera_model"):
            logger.info(f"Job {job_id}: using preset camera model {job['camera_model']}")
            return StepResult(success=True, data={"camera_model": job["camera_model"]})

        images_dir = self.data_dir / job_id / "images"
        sample_images = list(images_dir.glob("*.jpg"))[:5]

        detected = None
        for img in sample_images:
            detected = detect_from_exif(str(img))
            if detected:
                break

        if detected:
            logger.info(f"Job {job_id}: auto-detected camera model: {detected}")
            return StepResult(success=True, data={"camera_model": detected})

        logger.info(f"Job {job_id}: camera model not detected, requesting user input")
        return StepResult(success=True, data={"camera_select_required": True})
