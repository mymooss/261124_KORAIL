"""배포용 시드 SQL 생성기.

임시 SQLite 에 seed_all() 로 시드를 넣은 뒤 Postgres INSERT 문으로 내보낸다 (supabase/seed.sql).
운영 계정 비밀번호는 무작위로 만들어 .env.production.local 에만 저장한다 (둘 다 git 제외).

사용: python scripts/make_seed_sql.py
"""
import os
import random
import secrets
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import connect, init_schema  # noqa: E402
from app.seed import seed_all  # noqa: E402

TABLES = ["lines", "stations", "line_stations", "segments", "fault_templates", "template_causes",
          "template_actions", "users", "sim_state", "trains", "train_inspections"]
IDENTITY = {"stations", "segments", "fault_templates", "template_causes", "template_actions", "users", "trains"}


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def main():
    env_file = ROOT / ".env.production.local"
    pw = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                pw[k.strip()] = v.strip()
    for k in ("ADMIN_PASSWORD", "OPERATOR_PASSWORD", "VIEWER_PASSWORD"):
        pw.setdefault(k, secrets.token_urlsafe(12))
    pw.setdefault("SECRET_KEY", secrets.token_hex(32))
    env_file.write_text("".join(f"{k}={v}\n" for k, v in pw.items()), encoding="utf-8")

    tmp = Path(tempfile.mkdtemp()) / "seed.db"
    init_schema(str(tmp))
    conn = connect(str(tmp))
    seed_all(conn, pw, rng=random.Random())
    conn.commit()
    out = ["-- 자동 생성 파일 (scripts/make_seed_sql.py). git 에 올리지 않는다.", "BEGIN;"]
    for t in TABLES:
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        if not rows:
            continue
        cols = rows[0].keys()
        for r in rows:
            out.append(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join(lit(r[c]) for c in cols)});")
        if t in IDENTITY:
            out.append(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT max(id) FROM {t}));")
    out.append("COMMIT;")
    conn.close()
    dest = ROOT / "supabase" / "seed.sql"
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.remove(tmp)
    print(f"seed SQL: {dest} ({len(out)} lines)")
    print(f"운영 계정 비밀번호·SECRET_KEY: {env_file}")


if __name__ == "__main__":
    main()
