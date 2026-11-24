import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.db import connect, init_schema  # noqa: E402
from app.seed import seed_all  # noqa: E402
from app.sim.engine import SimulationEngine  # noqa: E402


@pytest.fixture
def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    app = create_app({"TESTING": True, "DATABASE_URL": "", "DATABASE_PATH": db_path, "SECRET_KEY": "test-secret"})
    init_schema(db_path)
    conn = connect(db_path)
    seed_all(conn, app.config, rng=random.Random(7))
    conn.commit()
    conn.close()
    yield app


@pytest.fixture
def engine(app):
    """요청과 무관하게 직접 조작하는 엔진 (전용 연결). 시간은 engine.step() 으로 결정적으로 진행한다."""
    eng = SimulationEngine(connect(app.config["DATABASE_PATH"]), seed=42)
    eng.load()
    yield eng
    eng.close()


@pytest.fixture
def db(app):
    conn = connect(app.config["DATABASE_PATH"])
    yield conn
    conn.close()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password=None):
    password = password or {"admin": "admin1234!", "operator": "operator1234!", "viewer": "viewer1234!"}[username]
    return client.post("/login", data={"username": username, "password": password})


@pytest.fixture
def login_as(client):
    def _login(username):
        r = login(client, username)
        assert r.status_code == 302, r.data
        return client
    return _login
