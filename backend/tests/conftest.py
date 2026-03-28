from collections.abc import Generator
import os

os.environ.setdefault("TRANSLATION_STRICT_REMOTE", "false")
os.environ.setdefault("TRUSTED_HOSTS", "localhost,127.0.0.1,backend,gateway,testserver,*.ngrok-free.dev")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app
from app.modules.capture.models import CaptureItemModel
from app.modules.context_memory.models import UserContextModel
from app.modules.learning_session.models import LearningSessionModel
from app.modules.users.models import UserModel
from app.modules.vocabulary.models import VocabularyItemModel

# Keep imports for SQLAlchemy metadata registration.
_ = (UserModel, VocabularyItemModel, CaptureItemModel, LearningSessionModel, UserContextModel)


test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def override_get_db() -> Generator[Session, None, None]:
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def prepare_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture()
def client() -> TestClient:
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
