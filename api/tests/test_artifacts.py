import io
from pathlib import Path


def _setup_job_with_artifacts(client, tmp_data_dir):
    resp = client.post("/jobs", files={"file": ("test.mp4", io.BytesIO(b"fake"), "video/mp4")})
    job_id = resp.json()["id"]

    output_dir = tmp_data_dir / job_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model.ply").write_bytes(b"ply content")
    (output_dir / "model.usdz").write_bytes(b"usdz content")
    return job_id


def test_list_artifacts(client, tmp_data_dir):
    job_id = _setup_job_with_artifacts(client, tmp_data_dir)
    resp = client.get(f"/jobs/{job_id}/artifacts")
    assert resp.status_code == 200
    names = resp.json()
    assert "model.ply" in names
    assert "model.usdz" in names


def test_download_artifact(client, tmp_data_dir):
    job_id = _setup_job_with_artifacts(client, tmp_data_dir)
    resp = client.get(f"/jobs/{job_id}/artifacts/model.ply")
    assert resp.status_code == 200
    assert resp.content == b"ply content"


def test_download_missing_artifact(client, tmp_data_dir):
    job_id = _setup_job_with_artifacts(client, tmp_data_dir)
    resp = client.get(f"/jobs/{job_id}/artifacts/nonexistent.ply")
    assert resp.status_code == 404


def test_create_and_get_share(client, tmp_data_dir):
    job_id = _setup_job_with_artifacts(client, tmp_data_dir)
    resp = client.post(f"/jobs/{job_id}/share")
    assert resp.status_code == 200
    share = resp.json()
    assert "token" in share

    info_resp = client.get(f"/share/{share['token']}")
    assert info_resp.status_code == 200
    assert info_resp.json()["job_id"] == job_id
