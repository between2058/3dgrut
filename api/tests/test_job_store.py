import pytest
from api.pipeline.job_store import JobStore
from api.models import JobStatus


def test_create_job(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    job = store.create(user_id="user1")
    assert job["status"] == JobStatus.CREATED
    assert job["user_id"] == "user1"
    assert "id" in job
    assert (tmp_data_dir / job["id"] / "job.json").exists()


def test_get_job(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    job = store.create(user_id="user1")
    loaded = store.get(job["id"])
    assert loaded["id"] == job["id"]
    assert loaded["status"] == JobStatus.CREATED


def test_update_status(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    job = store.create(user_id="user1")
    store.update_status(job["id"], JobStatus.EXTRACTING)
    loaded = store.get(job["id"])
    assert loaded["status"] == JobStatus.EXTRACTING


def test_get_nonexistent_raises(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    with pytest.raises(FileNotFoundError):
        store.get("nonexistent")
