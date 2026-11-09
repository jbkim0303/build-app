import os
import tempfile

_db_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_dir}/test.db"
os.environ["SEED_ON_STARTUP"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed(session)
        yield session


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        yield c


def _token(client, email, password, name="Fan"):
    client.post("/api/auth/register", json={"email": email, "name": name, "password": password})
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def user_headers(client):
    return _token(client, "fan@example.com", "password123")


@pytest.fixture()
def other_headers(client):
    return _token(client, "other@example.com", "password123")


@pytest.fixture()
def admin_headers(client):
    r = client.post("/api/auth/login", data={"username": "admin@league.local", "password": "admin1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
