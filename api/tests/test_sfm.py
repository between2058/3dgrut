import pytest
from unittest.mock import patch
from api.pipeline.steps.sfm import ColmapSfmStep


@pytest.mark.asyncio
async def test_sfm_step_runs(tmp_data_dir):
    job_id = "testjob"
    job_dir = tmp_data_dir / job_id
    (job_dir / "images").mkdir(parents=True)
    (job_dir / "sparse" / "0").mkdir(parents=True)
    (job_dir / "sparse" / "0" / "points3D.bin").write_bytes(b"fake")

    step = ColmapSfmStep(data_dir=str(tmp_data_dir))

    with patch("api.pipeline.steps.sfm.run_in_threadpool") as mock_run:
        mock_run.return_value = {}
        result = await step.run(
            job_id,
            {"id": job_id, "camera_model": "SIMPLE_RADIAL"},
            {},
        )

    assert result.success
    mock_run.assert_called_once()
