import pytest
from api.config import Settings


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def test_settings(tmp_data_dir, tmp_path):
    return Settings(
        data_dir=str(tmp_data_dir),
        log_dir=str(tmp_path / "logs"),
        redis_url="redis://localhost:6379/15",
    )


@pytest.fixture
def app(test_settings):
    from api.main import create_app
    return create_app(test_settings)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)
