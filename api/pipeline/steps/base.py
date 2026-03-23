import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from api.models import JobStatus


@dataclass
class StepResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseStep(ABC):
    name: str = ""
    status: JobStatus = JobStatus.CREATED
    label: str = ""
    needs_gpu: bool = False

    @abstractmethod
    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        """Execute this pipeline step. Return StepResult."""
        ...
