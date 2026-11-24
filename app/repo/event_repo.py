"""이벤트 로그. 커밋은 호출자가 한다."""
from ..util import ago_str, fmt_clock, iso, now_str

_SELECT = (
    "SELECT e.id, e.sim_time, e.created_at, e.category, e.message, e.fault_id, e.train_id, e.user_id,"
    " f.code AS fault_code, t.train_no AS train_no, u.display_name AS user_name"
    " FROM event_logs e"
    " LEFT JOIN faults f ON f.id = e.fault_id"
    " LEFT JOIN trains t ON t.id = e.train_id"
    " LEFT JOIN users u ON u.id = e.user_id"
)


def insert(conn, sim_time, category, message, fault_id=None, train_id=None, user_id=None):
    created = now_str()
    eid = conn.insert(
        "INSERT INTO event_logs(sim_time, created_at, category, message, fault_id, train_id, user_id)"
        " VALUES (?,?,?,?,?,?,?)", (int(sim_time), created, category, message, fault_id, train_id, user_id))
    return eid, created


def audit(conn, message, user_id=None):
    """엔진 없이 감사 로그를 남긴다 (로그인·로그아웃 등)."""
    sim = conn.scalar("SELECT sim_time FROM sim_state WHERE id=1") or 0
    return insert(conn, sim, "audit", message, user_id=user_id)


def to_dict(r):
    return {"id": r["id"], "sim_time": r["sim_time"], "sim_clock": fmt_clock(r["sim_time"]),
            "created_at": iso(r["created_at"]), "category": r["category"], "message": r["message"],
            "fault_code": r["fault_code"], "train_no": r["train_no"], "user_name": r["user_name"]}


def query(conn, categories=None, since_id=None, before_id=None, limit=100, frm=None, to=None,
          fault_id=None, order="desc"):
    where, args = [], []
    if categories:
        where.append("e.category IN (%s)" % ",".join("?" * len(categories)))
        args += list(categories)
    if since_id is not None:
        where.append("e.id > ?")
        args.append(since_id)
    if before_id is not None:
        where.append("e.id < ?")
        args.append(before_id)
    if frm:
        where.append("e.created_at >= ?")
        args.append(frm)
    if to:
        where.append("e.created_at <= ?")
        args.append(to)
    if fault_id is not None:
        where.append("e.fault_id = ?")
        args.append(fault_id)
    sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY e.id " + ("ASC" if order == "asc" else "DESC")
    if limit:
        sql += " LIMIT ?"
        args.append(int(limit))
    return [to_dict(r) for r in conn.execute(sql, args)]


def delete_all(conn):
    return conn.execute("DELETE FROM event_logs").rowcount


def prune(conn, days):
    return conn.execute("DELETE FROM event_logs WHERE created_at < ?", (ago_str(days=int(days)),)).rowcount
