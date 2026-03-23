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
    app.state.event_bus = EventBus()

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
