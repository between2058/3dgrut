import pytest
from unittest.mock import patch, AsyncMock
from api.pipeline.steps.extract_frames import ExtractFramesStep


@pytest.mark.asyncio
async def test_extract_frames_ffmpeg(tmp_data_dir):
    job_id = "testjob"
    job_dir = tmp_data_dir / job_id
    (job_dir / "input").mkdir(parents=True)
    images_dir = job_dir / "images"
    images_dir.mkdir(parents=True)
    (job_dir / "input" / "video.mp4").write_bytes(b"fake")

    # Create fake output frames (simulating ffmpeg output)
    (images_dir / "frame_00001.jpg").write_bytes(b"fake")
    (images_dir / "frame_00002.jpg").write_bytes(b"fake")

    step = ExtractFramesStep(data_dir=str(tmp_data_dir), fps=1)

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"ffmpeg output\n", None)
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await step.run(job_id, {"id": job_id}, {})

    assert result.success
    assert result.data["frame_count"] == 2


@pytest.mark.asyncio
async def test_extract_frames_no_input(tmp_data_dir):
    job_id = "testjob"
    (tmp_data_dir / job_id / "input").mkdir(parents=True)

    step = ExtractFramesStep(data_dir=str(tmp_data_dir))
    result = await step.run(job_id, {"id": job_id}, {})

    assert not result.success
    assert "No input file" in result.error


@pytest.mark.asyncio
async def test_extract_handles_images(tmp_data_dir):
    job_id = "testjob"
    input_dir = tmp_data_dir / job_id / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "photo1.jpg").write_bytes(b"fake jpg")
    (input_dir / "photo2.jpg").write_bytes(b"fake jpg")

    step = ExtractFramesStep(data_dir=str(tmp_data_dir))
    result = await step.run(job_id, {"id": job_id}, {})

    assert result.success
    assert result.data["frame_count"] == 2
