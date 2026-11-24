"""DB 연결 (SQLite 로컬 / Postgres·Supabase 배포)과 CLI 명령.

- DATABASE_URL 이 postgres:// 로 시작하면 Postgres(psycopg)를, 아니면 DATABASE_PATH 의 SQLite 를 쓴다.
- SQL 은 '?' 자리표시자로 작성하고, Postgres 에서는 자동으로 '%s' 로 바꾼다.
- 저장소(repo) 함수는 커밋하지 않는다. 요청 단위로 after_request 에서 한 번 커밋한다.
"""
import os
import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

BASE = Path(__file__).resolve().parent
SCHEMA_SQLITE = BASE / "schema.sql"
SCHEMA_PG = BASE / "schema_pg.sql"


class DB:
    """sqlite3 / psycopg 연결을 같은 인터페이스로 감싼다."""

    def __init__(self, raw, kind, target=""):
        self.raw = raw
        self.kind = kind
        self.target = target

    @property
    def is_pg(self):
        return self.kind == "pg"

    def _sql(self, sql):
        return sql.replace("%", "%%").replace("?", "%s") if self.is_pg else sql

    def execute(self, sql, args=()):
        if self.is_pg:
            cur = self.raw.cursor()
            cur.execute(self._sql(sql), tuple(args))
            return cur
        return self.raw.execute(sql, tuple(args))

    def executemany(self, sql, seq):
        seq = [tuple(s) for s in seq]
        if not seq:
            return None
        if self.is_pg:
            cur = self.raw.cursor()
            cur.executemany(self._sql(sql), seq)
            return cur
        return self.raw.executemany(sql, seq)

    def executescript(self, script):
        if self.is_pg:
            self.raw.execute(script)
        else:
            self.raw.executescript(script)

    def insert(self, sql, args=()):
        """INSERT 후 새 id 를 돌려준다."""
        if self.is_pg:
            return self.execute(sql + " RETURNING id", args).fetchone()["id"]
        return self.raw.execute(sql, tuple(args)).lastrowid

    def scalar(self, sql, args=()):
        r = self.execute(sql, args).fetchone()
        if r is None:
            return None
        return list(r.values())[0] if isinstance(r, dict) else r[0]

    def lock_state(self):
        """시뮬레이션 상태 행을 잠가 동시에 두 요청이 시간을 진행하지 않게 한다."""
        if self.is_pg:
            self.execute("SELECT id FROM sim_state WHERE id=1 FOR UPDATE")
        elif not self.raw.in_transaction:
            self.raw.execute("BEGIN IMMEDIATE")

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def connect(target, check_same_thread=True):
    """target: postgres URL 또는 SQLite 파일 경로."""
    target = str(target)
    if target.startswith(("postgres://", "postgresql://")):
        import psycopg
        from psycopg.rows import dict_row
        raw = psycopg.connect(target, row_factory=dict_row, prepare_threshold=None, connect_timeout=10)
        return DB(raw, "pg", target)
    raw = sqlite3.connect(target, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=check_same_thread,
                          timeout=5)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode = WAL")
    raw.execute("PRAGMA foreign_keys = ON")
    raw.execute("PRAGMA busy_timeout = 5000")
    return DB(raw, "sqlite", target)


def db_target(config):
    return config.get("DATABASE_URL") or config["DATABASE_PATH"]


def get_db():
    if "db" not in g:
        g.db = connect(db_target(current_app.config))
    return g.db


def close_db(_e=None):
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.rollback()  # 커밋되지 않은 변경은 버린다
        except Exception:
            pass
        conn.close()


def commit_db(response):
    conn = g.get("db")
    if conn is not None and response.status_code < 500:
        conn.commit()
    return response


def init_schema(target):
    conn = connect(target)
    try:
        script = (SCHEMA_PG if conn.is_pg else SCHEMA_SQLITE).read_text(encoding="utf-8")
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


def remove_db_files(path):
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass


def _has_tables(conn):
    try:
        conn.execute("SELECT 1 FROM sim_state").fetchone()
        return True
    except Exception:
        conn.rollback()
        return False


# ---------------------------------------------------------------- CLI
@click.command("init-db")
@click.option("--force", is_flag=True, help="기존 DB를 삭제하고 다시 만든다 (SQLite 전용).")
def init_db_command(force):
    """스키마로 데이터베이스를 만든다."""
    target = db_target(current_app.config)
    if current_app.config.get("DATABASE_URL"):
        conn = connect(target)
        exists = _has_tables(conn)
        conn.close()
        if exists:
            click.echo("Postgres 에 이미 테이블이 있습니다. (Supabase 는 'supabase db push' 로 마이그레이션을 적용하세요)")
            return
        init_schema(target)
        click.echo("Postgres 스키마를 만들었습니다.")
        return
    if os.path.exists(target):
        if not force:
            click.echo(f"이미 데이터베이스가 있습니다: {target}")
            click.echo("다시 만들려면 'flask init-db --force' 를 사용하세요.")
            return
        remove_db_files(target)
    init_schema(target)
    click.echo(f"데이터베이스를 만들었습니다: {target}")


@click.command("seed")
def seed_command():
    """노선·역·구간·열차·템플릿·계정 초기 데이터를 넣는다."""
    from .seed import seed_all
    conn = connect(db_target(current_app.config))
    try:
        result = seed_all(conn, current_app.config)
        conn.commit()
    finally:
        conn.close()
    if result is None:
        click.echo("시드 데이터가 이미 있어 건너뜁니다.")
    else:
        click.echo("시드 데이터 입력 완료: " + ", ".join(f"{k} {v}" for k, v in result.items()))


@click.command("reset-sim")
def reset_sim_command():
    """열차·장애·sim_state 를 시드 값으로 되돌린다."""
    from .seed import reset_sim
    conn = connect(db_target(current_app.config))
    try:
        reset_sim(conn)
        conn.commit()
    finally:
        conn.close()
    click.echo("시뮬레이션 상태를 초기화했습니다.")


@click.command("prune")
@click.option("--days", default=30, show_default=True, help="이벤트 로그 보존 일수")
@click.option("--kpi-days", default=7, show_default=True, help="KPI 스냅샷 보존 일수")
def prune_command(days, kpi_days):
    """오래된 이벤트 로그·KPI 스냅샷을 정리한다."""
    from .repo import event_repo, kpi_repo
    conn = connect(db_target(current_app.config))
    try:
        n1 = event_repo.prune(conn, days)
        n2 = kpi_repo.prune(conn, kpi_days)
        conn.commit()
    finally:
        conn.close()
    click.echo(f"이벤트 로그 {n1}건, KPI 스냅샷 {n2}건을 삭제했습니다.")


@click.command("create-user")
@click.argument("username")
@click.option("--role", type=click.Choice(["viewer", "operator", "admin"]), default="operator", show_default=True)
@click.option("--display-name", default=None, help="화면에 표시할 이름")
@click.password_option("--password", prompt="비밀번호", confirmation_prompt="비밀번호 확인")
def create_user_command(username, role, display_name, password):
    """계정을 추가한다."""
    conn = connect(db_target(current_app.config))
    try:
        if conn.execute("SELECT 1 AS x FROM users WHERE username=?", (username,)).fetchone():
            raise click.ClickException(f"이미 있는 사용자입니다: {username}")
        conn.execute("INSERT INTO users(username,password_hash,display_name,role) VALUES (?,?,?,?)",
                     (username, generate_password_hash(password), display_name or username, role))
        conn.commit()
    finally:
        conn.close()
    click.echo(f"계정을 만들었습니다: {username} ({role})")


def init_app(app):
    app.after_request(commit_db)
    app.teardown_appcontext(close_db)
    for cmd in (init_db_command, seed_command, reset_sim_command, prune_command, create_user_command):
        app.cli.add_command(cmd)
