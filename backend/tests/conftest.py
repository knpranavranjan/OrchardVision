import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import REPO_ROOT, Settings, get_settings
from app.db.tables import Base
from app.main import create_app

TEST_DB = "orchardvision_test"


@pytest.fixture
def models_dir(tmp_path: Path) -> Path:
    """A private copy of the repository's models folder, safe to tamper with."""
    dst = tmp_path / "models"
    shutil.copytree(REPO_ROOT / "models", dst)
    return dst


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """A separate, empty database so tests never touch real orchards and flights."""
    base = get_settings().database_url
    admin = create_engine(base, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
    try:
        with admin.connect() as c:
            exists = c.execute(
                text("select 1 from pg_database where datname = :n"), {"n": TEST_DB}
            ).scalar()
            if not exists:
                c.execute(text(f'create database "{TEST_DB}"'))
    except OperationalError:
        pytest.skip("database container is not running")
    finally:
        admin.dispose()
    url = base.rsplit("/", 1)[0] + "/" + TEST_DB
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


@pytest.fixture
def client(models_dir: Path, test_db_url: str, tmp_path: Path):
    settings = Settings(models_dir=models_dir, database_url=test_db_url, data_dir=tmp_path / "data")
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def offline_client(models_dir: Path, tmp_path: Path):
    """The application with no database behind it."""
    settings = Settings(
        models_dir=models_dir,
        database_url="postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
        data_dir=tmp_path / "data",
    )
    with TestClient(create_app(settings)) as c:
        yield c
