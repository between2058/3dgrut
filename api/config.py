from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8191
    host: str = "0.0.0.0"
    data_dir: str = "data"
    log_dir: str = "logs"
    allowed_origins: str = "*"
    max_upload_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB
    redis_url: str = "redis://localhost:6379/0"
    max_gpu_jobs: int = 1
    share_token_expiry_days: int = 30
    cleanup_intermediate_after_days: int = 7
    cleanup_completed_after_days: int = 90

    # Pipeline defaults
    sharp_frames_fps: int = 10
    sharp_frames_num: int = 300
    sharp_frames_method: str = "best-n"
    default_camera_model: str = "SIMPLE_RADIAL"
    train_config: str = "apps/colmap_3dgut_mcmc"
    train_iterations: int = 30000
    mesh_resolution: float = 0.10

    class Config:
        env_prefix = "THREEDGRUT_"


settings = Settings()
