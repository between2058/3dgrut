import pytest
from pathlib import Path
import sys
from unittest.mock import patch, MagicMock
from api.pipeline.steps.extract_frames import ExtractFramesStep


@pytest.mark.asyncio
async def test_extract_frames_calls_sharp_frames(tmp_data_dir):
    job_id = "testjob"
    job_dir = tmp_data_dir / job_id
    (job_dir / "input").mkdir(parents=True)
    (job_dir / "images").mkdir(parents=True)
    (job_dir / "input" / "video.mp4").write_bytes(b"fake")

    step = ExtractFramesStep(data_dir=str(tmp_data_dir))

    mock_instance = MagicMock()
    mock_instance.run.return_value = True
    MockSF = MagicMock(return_value=mock_instance)

    mock_sf_module = MagicMock()
    mock_sf_module.SharpFrames = MockSF

    with patch.dict("sys.modules", {"sharp_frames": mock_sf_module}):
        result = await step.run(job_id, {"id": job_id}, {})

        assert result.success
        MockSF.assert_called_once()


@pytest.mark.asyncio
async def test_extract_frames_no_input(tmp_data_dir):
    job_id = "testjob"
    (tmp_data_dir / job_id / "input").mkdir(parents=True)

    step = ExtractFramesStep(data_dir=str(tmp_data_dir))
    result = await step.run(job_id, {"id": job_id}, {})

    assert not result.success
    assert "No input file" in result.error
