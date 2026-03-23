import pytest
from unittest.mock import patch, AsyncMock
from api.pipeline.steps.train_gs import TrainGsStep, build_train_command


def test_build_train_command():
    cmd = build_train_command(
        job_id="abc123",
        data_dir="/data",
        config="apps/colmap_3dgut_mcmc.yaml",
    )
    assert "train.py" in cmd[1]
    assert "apps/colmap_3dgut_mcmc.yaml" in " ".join(cmd)
    assert "export_ply.enabled=true" in cmd
    assert "export_usdz.enabled=true" in cmd
    assert any("export_ply.path=" in arg for arg in cmd)


@pytest.mark.asyncio
async def test_train_step_runs(tmp_data_dir):
    job_id = "testjob"
    (tmp_data_dir / job_id / "sparse" / "0").mkdir(parents=True)
    output_dir = tmp_data_dir / job_id / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "model.ply").write_bytes(b"fake ply")

    step = TrainGsStep(data_dir=str(tmp_data_dir))

    with patch("api.pipeline.steps.train_gs.run_training", new_callable=AsyncMock) as mock:
        mock.return_value = (True, "")
        result = await step.run(job_id, {"id": job_id}, {})

    assert result.success
    mock.assert_called_once()
