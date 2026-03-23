import pytest
from unittest.mock import patch, AsyncMock
from api.pipeline.steps.mesh import MeshStep, build_mesh_command


def test_build_mesh_command():
    cmd = build_mesh_command("/data/job1/output/model.ply", "/data/job1/output/collider.ply", 0.10)
    assert cmd == ["frgs", "mesh-dlnr", "/data/job1/output/model.ply", "-o", "/data/job1/output/collider.ply", "0.1"]


@pytest.mark.asyncio
async def test_mesh_step(tmp_data_dir):
    job_id = "testjob"
    output_dir = tmp_data_dir / job_id / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "model.ply").write_bytes(b"fake ply")

    step = MeshStep(data_dir=str(tmp_data_dir))

    with patch("api.pipeline.steps.mesh.run_mesh", new_callable=AsyncMock) as mock:
        mock.return_value = (True, "")
        result = await step.run(job_id, {"id": job_id}, {})

    assert result.success


@pytest.mark.asyncio
async def test_mesh_step_no_ply(tmp_data_dir):
    job_id = "testjob"
    (tmp_data_dir / job_id / "output").mkdir(parents=True)

    step = MeshStep(data_dir=str(tmp_data_dir))
    result = await step.run(job_id, {"id": job_id}, {})

    assert not result.success
    assert "model.ply not found" in result.error
