import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger("api")


class JobQueue:
    def __init__(self, max_gpu_jobs: int = 1):
        self._semaphore = asyncio.Semaphore(max_gpu_jobs)
        self._waiting: list[str] = []

    @asynccontextmanager
    async def acquire_gpu(self, job_id: str = ""):
        self._waiting.append(job_id)
        try:
            await self._semaphore.acquire()
            if job_id in self._waiting:
                self._waiting.remove(job_id)
            yield
        finally:
            self._semaphore.release()

    def position(self, job_id: str) -> int:
        try:
            return self._waiting.index(job_id)
        except ValueError:
            return 0

    @property
    def gpu_busy(self) -> bool:
        return self._semaphore._value == 0
