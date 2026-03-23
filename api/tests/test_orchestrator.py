import asyncio
import pytest
from api.pipeline.orchestrator import PipelineOrchestrator
from api.pipeline.steps.base import BaseStep, StepResult
from api.pipeline.event_bus import EventBus
from api.pipeline.job_store import JobStore
from api.models import JobStatus


class FakeStepA(BaseStep):
    name = "step_a"
    status = JobStatus.EXTRACTING
    label = "Running step A..."

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        return StepResult(success=True, data={"a": 1})


class FakeStepB(BaseStep):
    name = "step_b"
    status = JobStatus.TRAINING
    label = "Running step B..."

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        return StepResult(success=True, data={"b": 2})


class FailingStep(BaseStep):
    name = "failing"
    status = JobStatus.SFM_MAPPING
    label = "Failing..."

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        return StepResult(success=False, error="Something broke")


class CameraSelectStep(BaseStep):
    name = "camera"
    status = JobStatus.CAMERA_DETECTING
    label = "Detecting camera..."

    async def run(self, job_id: str, job: dict, context: dict) -> StepResult:
        if job.get("camera_model"):
            return StepResult(success=True, data={"camera_model": job["camera_model"]})
        return StepResult(success=True, data={"camera_select_required": True})


@pytest.mark.asyncio
async def test_runs_steps_in_order(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    bus = EventBus()
    orch = PipelineOrchestrator(store, bus, steps=[FakeStepA(), FakeStepB()])

    job = store.create()
    await orch.run_pipeline(job["id"])

    final = store.get(job["id"])
    assert final["status"] == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_stops_on_failure(tmp_data_dir):
    store = JobStore(str(tmp_data_dir))
    bus = EventBus()
    orch = PipelineOrchestrator(store, bus, steps=[FakeStepA(), FailingStep(), FakeStepB()])

    job = store.create()
    await orch.run_pipeline(job["id"])

    final = store.get(job["id"])
    assert final["status"] == JobStatus.FAILED
    assert "Something broke" in final["error"]


@pytest.mark.asyncio
async def test_pause_and_resume_for_camera_select(tmp_data_dir):
    """Test that orchestrator pauses when camera_select_required and resumes after resume()."""
    store = JobStore(str(tmp_data_dir))
    bus = EventBus()
    orch = PipelineOrchestrator(store, bus, steps=[CameraSelectStep(), FakeStepB()])

    job = store.create()
    job_id = job["id"]

    # Collect SSE events
    events = []

    async def collect_events():
        async for event in bus.subscribe(job_id):
            events.append(event)
            if event.get("type") in ("completed", "failed"):
                break

    collector = asyncio.create_task(collect_events())

    # Run pipeline in background (it will pause at camera step)
    pipeline_task = asyncio.create_task(orch.run_pipeline(job_id))

    # Wait a bit for pipeline to reach pause point
    await asyncio.sleep(0.1)

    # Verify it's paused
    paused_job = store.get(job_id)
    assert paused_job["status"] == JobStatus.CAMERA_SELECT_REQUIRED

    # Simulate user selecting camera model
    store.update_fields(job_id, camera_model="OPENCV_FISHEYE")
    orch.resume(job_id)

    # Wait for pipeline to complete
    await pipeline_task
    await collector

    final = store.get(job_id)
    assert final["status"] == JobStatus.COMPLETED

    # Verify camera_select_required event was published
    event_types = [e.get("type") for e in events]
    assert "camera_select_required" in event_types
    assert "completed" in event_types
