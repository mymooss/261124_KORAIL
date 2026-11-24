"""KPI 스냅샷. 커밋은 호출자가 한다."""
from ..util import ago_str, fmt_clock, iso, now_str


def insert(conn, sim_time, k, active_faults):
    conn.execute(
        "INSERT INTO kpi_snapshots(sim_time, created_at, total_trains, on_time_rate, safety_index, delayed_trains,"
        " active_faults) VALUES (?,?,?,?,?,?,?)",
        (int(sim_time), now_str(), k["total"], k["on_time"], k["safety"], k["delayed"], active_faults))


def history(conn, minutes=30):
    rows = conn.execute("SELECT * FROM kpi_snapshots WHERE created_at >= ? ORDER BY id",
                        (ago_str(minutes=int(minutes)),)).fetchall()
    return [{"sim_time": r["sim_time"], "sim_clock": fmt_clock(r["sim_time"]), "created_at": iso(r["created_at"]),
             "total": r["total_trains"], "on_time": r["on_time_rate"], "safety": r["safety_index"],
             "delayed": r["delayed_trains"], "active_faults": r["active_faults"]} for r in rows]


def prune(conn, days):
    return conn.execute("DELETE FROM kpi_snapshots WHERE created_at < ?", (ago_str(days=int(days)),)).rowcount
