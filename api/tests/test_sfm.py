import pytest
from unittest.mock import patch, AsyncMock
from api.pipeline.steps.sfm import ColmapSfmStep, build_colmap_commands


def test_build_commands():
    cmds = build_colmap_commands(
        image_path="/data/job1/images",
        database_path="/data/job1/database.db",
        output_path="/data/job1/sparse",
        camera_model="SIMPLE_RADIAL",
    )
    assert len(cmds) == 3
    assert "feature_extractor" in cmds[0][0][1]
    assert "exhaustive_matcher" in cmds[1][0][1]
    assert "mapper" in cmds[2][0][1]
    assert "SIMPLE_RADIAL" in " ".join(cmds[0][0])


@pytest.mark.asyncio
async def test_sfm_step_runs(tmp_data_dir):
    job_id = "testjob"
    job_dir = tmp_data_dir / job_id
    (job_dir / "images").mkdir(parents=True)
    (job_dir / "sparse" / "0").mkdir(parents=True)
    (job_dir / "sparse" / "0" / "points3D.bin").write_bytes(b"fake")

    step = ColmapSfmStep(data_dir=str(tmp_data_dir))

    with patch("api.pipeline.steps.sfm.run_colmap_command", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (True, "")
        result = await step.run(
            job_id,
            {"id": job_id},
            {"camera_model": "SIMPLE_RADIAL"},
        )

    assert result.success
    assert mock_run.call_count == 3
