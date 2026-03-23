import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from api.models import JobStatus
from api.storage.manager import StorageManager

TW_TZ = timezone(timedelta(hours=8))


class JobStore:
    def __init__(self, data_dir: str):
        self.storage = StorageManager(data_dir)

    def create(self, user_id: str | None = None, camera_model: str | None = None) -> dict:
        job_id = uuid.uuid4().hex[:12]
        now = datetime.now(TW_TZ).isoformat()
        job = {
            "id": job_id,
            "status": JobStatus.CREATED,
            "user_id": user_id,
            "camera_model": camera_model,
            "error": None,
            "artifacts": [],
            "created_at": now,
            "updated_at": now,
        }
        self.storage.ensure_job_dirs(job_id)
        self._save(job)
        return job

    def get(self, job_id: str) -> dict:
        path = self._job_file(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job not found: {job_id}")
        with open(path) as f:
            return json.load(f)

    def update_status(self, job_id: str, status: JobStatus, **fields):
        job = self.get(job_id)
        job["status"] = status
        job["updated_at"] = datetime.now(TW_TZ).isoformat()
        job.update(fields)
        self._save(job)
        return job

    def update_fields(self, job_id: str, **fields):
        job = self.get(job_id)
        job["updated_at"] = datetime.now(TW_TZ).isoformat()
        job.update(fields)
        self._save(job)
        return job

    def _job_file(self, job_id: str) -> Path:
        return self.storage.job_dir(job_id) / "job.json"

    def _save(self, job: dict):
        path = self._job_file(job["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(job, f, indent=2, default=str)
