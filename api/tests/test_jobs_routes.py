import io


def test_create_job_with_video(client, tmp_data_dir):
    fake_video = io.BytesIO(b"fake video content")
    resp = client.post(
        "/jobs",
        files={"file": ("test.mp4", fake_video, "video/mp4")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["status"] == "created"


def test_create_job_rejects_bad_format(client):
    fake = io.BytesIO(b"not a video")
    resp = client.post(
        "/jobs",
        files={"file": ("test.txt", fake, "text/plain")},
    )
    assert resp.status_code == 422


def test_get_job(client, tmp_data_dir):
    fake_video = io.BytesIO(b"fake video content")
    create_resp = client.post(
        "/jobs",
        files={"file": ("test.mp4", fake_video, "video/mp4")},
    )
    job_id = create_resp.json()["id"]

    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


def test_get_nonexistent_job(client):
    resp = client.get("/jobs/nonexistent")
    assert resp.status_code == 404


def test_set_camera_model(client, tmp_data_dir):
    fake_video = io.BytesIO(b"fake video content")
    create_resp = client.post(
        "/jobs",
        files={"file": ("test.mp4", fake_video, "video/mp4")},
    )
    job_id = create_resp.json()["id"]

    resp = client.post(f"/jobs/{job_id}/camera_model", json={"model": "OPENCV_FISHEYE"})
    assert resp.status_code == 200

    job = client.get(f"/jobs/{job_id}").json()
    assert job["camera_model"] == "OPENCV_FISHEYE"
