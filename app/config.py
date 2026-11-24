"""설정 로딩 (.env / 환경변수 → app.config)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_config(app, test_config=None):
    load_dotenv(ROOT / ".env")
    from .util import env
    secret = env("SECRET_KEY")
    if not secret:
        secret = secrets.token_hex(32)
        app.logger.warning("SECRET_KEY 가 설정되지 않아 임시 키를 사용합니다 (.env 또는 환경변수를 확인하세요).")
    app.config.from_mapping(
        SECRET_KEY=secret,
        # Postgres(Supabase) 접속 문자열. 비어 있으면 DATABASE_PATH 의 SQLite 를 쓴다.
        DATABASE_URL=env("DATABASE_URL"),
        DATABASE_PATH=env("DATABASE_PATH", "instance/ktx.db") or "instance/ktx.db",
        ADMIN_PASSWORD=env("ADMIN_PASSWORD", "admin1234!"),
        OPERATOR_PASSWORD=env("OPERATOR_PASSWORD", "operator1234!"),
        VIEWER_PASSWORD=env("VIEWER_PASSWORD", "viewer1234!"),
        POLL_MS=int(env("POLL_MS", "1000") or 1000),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["DATABASE_URL"]:
        p = Path(app.config["DATABASE_PATH"])
        if not p.is_absolute():
            p = ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        app.config["DATABASE_PATH"] = str(p)
