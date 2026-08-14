import os
from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-only-used-by-pytest")
os.environ.setdefault("REDIS_URL", "")

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db_session_factory() -> Generator[sessionmaker[Session], None, None]:
    # Workflow endpoints execute in a background thread while tests poll from
    # another request thread. A StaticPool-backed in-memory SQLite database
    # shares one connection across those threads and corrupts concurrent ORM
    # result reads. Give every test a small file-backed database so each thread
    # receives an independent connection to the same isolated database.
    with TemporaryDirectory(prefix="mini-agent-test-", dir=Path(__file__).parent) as directory:
        database_path = Path(directory) / "test.db"
        engine = create_engine(
            f"sqlite+pysqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        testing_session = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            class_=Session,
        )
        Base.metadata.create_all(engine)

        yield testing_session

        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(
    db_session_factory: sessionmaker[Session],
) -> Generator[TestClient, None, None]:

    def override_get_db() -> Generator[Session, None, None]:
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
