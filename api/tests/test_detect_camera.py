import pytest
from api.pipeline.steps.detect_camera import DetectCameraStep, detect_from_exif


def _make_image_dir(tmp_data_dir, job_id="testjob"):
    img_dir = tmp_data_dir / job_id / "images"
    img_dir.mkdir(parents=True)
    (img_dir / "frame_00001.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")
    return img_dir


def test_detect_from_exif_no_data(tmp_path):
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0fake")
    assert detect_from_exif(str(img)) is None


@pytest.mark.asyncio
async def test_step_defaults_when_no_exif(tmp_data_dir):
    job_id = "testjob"
    _make_image_dir(tmp_data_dir, job_id)

    step = DetectCameraStep(data_dir=str(tmp_data_dir), default_model="SIMPLE_RADIAL")
    result = await step.run(job_id, {"id": job_id, "camera_model": None}, {})

    assert result.success
    assert result.data.get("camera_select_required") is True


@pytest.mark.asyncio
async def test_step_uses_preset_camera_model(tmp_data_dir):
    job_id = "testjob"
    _make_image_dir(tmp_data_dir, job_id)

    step = DetectCameraStep(data_dir=str(tmp_data_dir), default_model="SIMPLE_RADIAL")
    result = await step.run(job_id, {"id": job_id, "camera_model": "OPENCV_FISHEYE"}, {})

    assert result.success
    assert result.data["camera_model"] == "OPENCV_FISHEYE"
    assert result.data.get("camera_select_required") is None
