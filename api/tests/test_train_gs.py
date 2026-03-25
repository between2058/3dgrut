import pytest
from unittest.mock import patch, AsyncMock, MagicMock
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
    assert any("export_ply.path=" in arg for arg in cmd)
    assert "export_usdz.enabled=true" not in cmd


@pytest.mark.asyncio
async def test_train_step_runs(tmp_data_dir):
    job_id = "testjob"
    # Create input data so validation passes
    images_dir = tmp_data_dir / job_id / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "frame_00001.jpg").write_bytes(b"fake")
    sparse_dir = tmp_data_dir / job_id / "sparse" / "0"
    sparse_dir.mkdir(parents=True)
    (sparse_dir / "points3D.bin").write_bytes(b"fake")
    # Create output PLY (large enough to pass validation)
    output_dir = tmp_data_dir / job_id / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "model.ply").write_bytes(b"x" * 2000)

    step = TrainGsStep(data_dir=str(tmp_data_dir))

    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"Training done\n", None)
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await step.run(job_id, {"id": job_id}, {})

    assert result.success
