import os
import shutil
from pathlib import Path


class StorageManager:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)

    def job_dir(self, job_id: str) -> Path:
        return self.data_dir / job_id

    def ensure_job_dirs(self, job_id: str):
        base = self.job_dir(job_id)
        for sub in ["input", "images", "sparse/0", "runs", "output"]:
            (base / sub).mkdir(parents=True, exist_ok=True)
        return base

    def list_artifacts(self, job_id: str) -> list[str]:
        output_dir = self.job_dir(job_id) / "output"
        if not output_dir.exists():
            return []
        return [f.name for f in output_dir.iterdir() if f.is_file()]

    def artifact_path(self, job_id: str, name: str) -> Path:
        path = self.job_dir(job_id) / "output" / name
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {name}")
        return path
