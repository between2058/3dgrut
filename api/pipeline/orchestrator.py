import asyncio
import logging
from api.pipeline.job_store import JobStore
from api.pipeline.event_bus import EventBus
from api.pipeline.steps.base import BaseStep
from api.models import JobStatus

logger = logging.getLogger("api")


class PipelineOrchestrator:
    def __init__(self, store: JobStore, bus: EventBus, steps: list[BaseStep]):
        self.store = store
        self.bus = bus
        self.steps = steps
        self._resume_events: dict[str, asyncio.Event] = {}

    def resume(self, job_id: str):
        event = self._resume_events.get(job_id)
        if event:
            event.set()

    async def run_pipeline(self, job_id: str):
        context: dict = {"_bus": self.bus}

        for step in self.steps:
            job = self.store.get(job_id)
            self.store.update_status(job_id, step.status)
            await self.bus.publish(job_id, {
                "type": "progress",
                "step": step.name,
                "label": step.label,
            })

            logger.info(f"Job {job_id}: starting step '{step.name}'")

            try:
                result = await step.run(job_id, job, context)
            except Exception as e:
                logger.error(f"Job {job_id}: step '{step.name}' exception: {e}")
                self.store.update_status(job_id, JobStatus.FAILED, error=str(e))
                await self.bus.publish(job_id, {
                    "type": "failed",
                    "step": step.name,
                    "error": str(e),
                })
                return

            if not result.success:
                logger.warning(f"Job {job_id}: step '{step.name}' failed: {result.error}")
                self.store.update_status(job_id, JobStatus.FAILED, error=result.error)
                await self.bus.publish(job_id, {
                    "type": "failed",
                    "step": step.name,
                    "error": result.error,
                })
                return

            context.update(result.data)

            # Handle pause: if step requests user input, wait for resume
            if result.data.get("camera_select_required"):
                self.store.update_status(job_id, JobStatus.CAMERA_SELECT_REQUIRED)
                await self.bus.publish(job_id, {"type": "camera_select_required"})

                resume_event = asyncio.Event()
                self._resume_events[job_id] = resume_event
                logger.info(f"Job {job_id}: paused, waiting for camera model selection")
                await resume_event.wait()
                del self._resume_events[job_id]

                job = self.store.get(job_id)
                context["camera_model"] = job.get("camera_model", "SIMPLE_RADIAL")
                logger.info(f"Job {job_id}: resumed with camera_model={context['camera_model']}")
                continue

            await self.bus.publish(job_id, {
                "type": "step_complete",
                "step": step.name,
                **result.data,
            })

        artifacts = self.store.storage.list_artifacts(job_id)
        self.store.update_status(job_id, JobStatus.COMPLETED, artifacts=artifacts)
        await self.bus.publish(job_id, {
            "type": "completed",
            "artifacts": artifacts,
        })
        logger.info(f"Job {job_id}: pipeline completed")
