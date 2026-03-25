import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import Settings, settings as default_settings
from api.logging_config import setup_logging
from api.models import HealthResponse

gpu_lock = asyncio.Lock()


def create_app(app_settings: Settings | None = None) -> FastAPI:
    s = app_settings or default_settings

    app = FastAPI(title="3DGRUT API")
    app.state.settings = s
    app.state.gpu_lock = gpu_lock

    from api.pipeline.event_bus import EventBus
    from api.pipeline.job_store import JobStore
    from api.pipeline.queue import JobQueue
    from api.pipeline.orchestrator import PipelineOrchestrator
    from api.pipeline.steps.extract_frames import ExtractFramesStep
    from api.pipeline.steps.sfm import ColmapSfmStep
    from api.pipeline.steps.train_gs import TrainGsStep
    from api.pipeline.steps.mesh import MeshStep

    app.state.event_bus = EventBus()

    app.state.job_store = JobStore(s.data_dir)
    app.state.job_queue = JobQueue(max_gpu_jobs=s.max_gpu_jobs)
    app.state.orchestrator = PipelineOrchestrator(
        store=app.state.job_store,
        bus=app.state.event_bus,
        steps=[
            ExtractFramesStep(data_dir=s.data_dir, fps=1),
            ColmapSfmStep(data_dir=s.data_dir),
            TrainGsStep(data_dir=s.data_dir, config=s.train_config),
            MeshStep(data_dir=s.data_dir, resolution=s.mesh_resolution),
        ],
    )

    origins = [o.strip() for o in s.allowed_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        return {"status": "ok", "gpu_busy": gpu_lock.locked()}

    from api.routes.jobs import router as jobs_router
    from api.routes.artifacts import router as artifacts_router
    from api.routes.stream import router as stream_router

    app.include_router(jobs_router)
    app.include_router(artifacts_router)
    app.include_router(stream_router)

    return app


def main():
    logger = setup_logging(default_settings.log_dir)
    logger.info(f"Starting 3DGRUT API on {default_settings.host}:{default_settings.port}")
    app = create_app()
    uvicorn.run(app, host=default_settings.host, port=default_settings.port)


if __name__ == "__main__":
    main()
