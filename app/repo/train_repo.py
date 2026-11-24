"""열차·점검 항목·시뮬레이션 상태(sim_state). 커밋은 호출자가 한다."""
import json

from ..util import now_str


def load_trains(conn):
    insp = {}
    for r in conn.execute("SELECT train_id, item, base_status FROM train_inspections"):
        insp.setdefault(r["train_id"], {})[r["item"]] = r["base_status"]
    out = []
    for r in conn.execute("SELECT * FROM trains ORDER BY id"):
        d = dict(r)
        d["insp"] = insp.get(r["id"], {})
        try:
            d["hist"] = [float(v) for v in json.loads(d.get("speed_hist") or "[]")][-60:]
        except (ValueError, TypeError):
            d["hist"] = []
        out.append(d)
    return out


def save_trains(conn, trains):
    ts = now_str()
    conn.executemany(
        "UPDATE trains SET direction=?, st_idx=?, progress=?, speed_kmh=?, dwell_sec=?, delay_min=?, status=?,"
        " passengers=?, last_check_sim=?, speed_hist=?, updated_at=? WHERE id=?",
        [(t.dir, t.st_idx, min(1.0, max(0.0, t.p)), t.speed, t.dwell, t.delay, t.status, t.pax,
          int(t.last_check), json.dumps(list(t.hist)), ts, t.id) for t in trains])


def load_sim_state(conn):
    try:
        r = conn.execute("SELECT * FROM sim_state WHERE id=1").fetchone()
        return dict(r) if r else None
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None


def save_sim_state(conn, eng):
    conn.execute(
        "UPDATE sim_state SET sim_time=?, speed_mul=?, paused=?, demo_active=?, demo_elapsed=?, fault_seq=?,"
        " last_real=?, last_hist_real=?, last_kpi_real=?, fault_ver=?, demo_user_id=?, demo_result=?,"
        " updated_at=? WHERE id=1",
        (eng.t, eng.mul, int(eng.paused), int(eng.demo.active), eng.demo.elapsed, eng.fault_seq,
         eng.last_real, eng.last_hist_real, eng.last_kpi_real, eng.fault_ver,
         eng.demo.user["id"] if eng.demo.user else None, eng.demo.result, now_str()))
