"""장애·원인·조치·영향 열차, 장애 분석 템플릿."""
from ..sim.constants import PHASE_LABEL, TYPE_META
from ..util import fmt_clock, iso, now_str, parse_dt

_BASE = (
    "SELECT f.*, l.name AS line_name, cu.display_name AS created_by_name, ru.display_name AS recovered_by_name,"
    " t.train_no AS target_train_no"
    " FROM faults f JOIN lines l ON l.id = f.line_id"
    " LEFT JOIN users cu ON cu.id = f.created_by"
    " LEFT JOIN users ru ON ru.id = f.recovered_by"
    " LEFT JOIN trains t ON t.id = f.target_train_id"
)


# ------------------------------------------------------------------ 쓰기
def insert_fault(conn, f, net, analysis_started_at=None):
    fid = conn.insert(
        "INSERT INTO faults(code, fault_type, sub_type, line_id, target_train_id, location_text, severity, phase,"
        " summary, confidence, impact_trains, expected_delay_min, source, created_by, created_sim, created_at,"
        " analysis_started_at, ana_epoch) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (f.code, f.type, f.sub, f.line, f.target_train_id, f.where, f.severity, f.phase, f.summary, f.confidence,
         f.impact, f.expected_delay, f.source, f.created_by, f.created_sim, now_str(), analysis_started_at,
         f.ana_start))
    conn.executemany("INSERT INTO fault_segments(fault_id, segment_id, level) VALUES (?,?,?)",
                     [(fid, net["segments"][k]["id"], f.seg_lv[k]) for k in f.segs])
    conn.executemany("INSERT INTO fault_causes(fault_id, rank, label, probability) VALUES (?,?,?,?)",
                     [(fid, i + 1, lbl, p) for i, (lbl, p) in enumerate(f.causes)])
    conn.executemany("INSERT INTO fault_actions(fault_id, seq, label) VALUES (?,?,?)",
                     [(fid, a["seq"], a["label"]) for a in f.actions])
    conn.executemany("INSERT INTO fault_affected_trains(fault_id, train_id) VALUES (?,?) ON CONFLICT DO NOTHING",
                     [(fid, tid) for tid in f.affected])
    return fid


def update_fault(conn, fid, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE faults SET {cols} WHERE id=?", list(fields.values()) + [fid])


def add_affected(conn, fid, train_id):
    conn.execute("INSERT INTO fault_affected_trains(fault_id, train_id) VALUES (?,?) ON CONFLICT DO NOTHING",
                 (fid, train_id))


def action_done(conn, fid, seq, user_id):
    conn.execute("UPDATE fault_actions SET done=1, done_at=?, done_by=? WHERE fault_id=? AND seq=?",
                 (now_str(), user_id, fid, seq))


# ------------------------------------------------------------------ 읽기
def max_code_seq(conn):
    mx = 0
    for r in conn.execute("SELECT code FROM faults"):
        try:
            mx = max(mx, int(str(r["code"]).split("-")[-1]))
        except ValueError:
            pass
    return mx


def find_code(conn, code):
    return conn.execute("SELECT id, phase FROM faults WHERE code=?", (code,)).fetchone()


def load_active(conn):
    """재시작 복구용: 미해결 장애와 하위 데이터."""
    out = []
    for r in conn.execute("SELECT * FROM faults WHERE phase <> 'resolved' ORDER BY id").fetchall():
        fid = r["id"]
        segs = conn.execute(
            "SELECT s.seg_key, fs.level FROM fault_segments fs JOIN segments s ON s.id = fs.segment_id"
            " WHERE fs.fault_id=? ORDER BY s.id", (fid,)).fetchall()
        d = dict(r)
        d["segs"] = [(s["seg_key"], s["level"]) for s in segs]
        d["causes"] = [(c["label"], c["probability"]) for c in
                       conn.execute("SELECT label, probability FROM fault_causes WHERE fault_id=? ORDER BY rank",
                                    (fid,))]
        d["actions"] = [{"seq": a["seq"], "label": a["label"], "done": bool(a["done"])} for a in
                        conn.execute("SELECT seq, label, done FROM fault_actions WHERE fault_id=? ORDER BY seq",
                                     (fid,))]
        d["affected"] = {a["train_id"] for a in
                         conn.execute("SELECT train_id FROM fault_affected_trains WHERE fault_id=?", (fid,))}
        out.append(d)
    return out


def _duration(r):
    a, b = parse_dt(r["created_at"]), parse_dt(r["resolved_at"])
    return int((b - a).total_seconds()) if a and b else None


def _base(r):
    meta = TYPE_META[r["fault_type"]]
    return {
        "id": r["id"], "code": r["code"], "type": r["fault_type"], "type_name": meta["name"],
        "type_code": meta["code"], "icon": meta["icon"], "sub": r["sub_type"],
        "line_id": r["line_id"], "line_name": r["line_name"], "where": r["location_text"],
        "severity": r["severity"], "phase": r["phase"], "phase_label": PHASE_LABEL[r["phase"]],
        "summary": r["summary"], "confidence": r["confidence"], "impact_trains": r["impact_trains"],
        "expected_delay_min": r["expected_delay_min"], "source": r["source"],
        "created_sim": r["created_sim"], "created_clock": fmt_clock(r["created_sim"]),
        "created_at": iso(r["created_at"]), "analysis_started_at": iso(r["analysis_started_at"]),
        "analyzed_at": iso(r["analyzed_at"]), "recovering_at": iso(r["recovering_at"]),
        "resolved_at": iso(r["resolved_at"]), "duration_sec": _duration(r),
        "created_by": r["created_by_name"], "recovered_by": r["recovered_by_name"],
        "target_train": r["target_train_no"], "virtual": True,
    }


def get_detail(conn, code=None, fid=None, with_logs=False):
    if fid is not None:
        r = conn.execute(_BASE + " WHERE f.id=?", (fid,)).fetchone()
    else:
        r = conn.execute(_BASE + " WHERE f.code=?", (code,)).fetchone()
    if not r:
        return None
    fid = r["id"]
    d = _base(r)
    d["segments"] = [{"key": s["seg_key"], "level": s["level"]} for s in conn.execute(
        "SELECT s.seg_key, fs.level FROM fault_segments fs JOIN segments s ON s.id = fs.segment_id"
        " WHERE fs.fault_id=? ORDER BY s.id", (fid,))]
    d["causes"] = [{"rank": c["rank"], "label": c["label"], "probability": c["probability"]} for c in
                   conn.execute("SELECT rank, label, probability FROM fault_causes WHERE fault_id=? ORDER BY rank",
                                (fid,))]
    d["actions"] = [{"seq": a["seq"], "label": a["label"], "done": bool(a["done"]), "done_at": iso(a["done_at"]),
                     "done_by": a["done_by_name"]} for a in conn.execute(
        "SELECT a.seq, a.label, a.done, a.done_at, u.display_name AS done_by_name FROM fault_actions a"
        " LEFT JOIN users u ON u.id = a.done_by WHERE a.fault_id=? ORDER BY a.seq", (fid,))]
    d["affected_trains"] = [t["train_no"] for t in conn.execute(
        "SELECT t.train_no FROM fault_affected_trains fa JOIN trains t ON t.id = fa.train_id"
        " WHERE fa.fault_id=? ORDER BY t.id", (fid,))]
    if with_logs:
        from . import event_repo
        d["logs"] = event_repo.query(conn, fault_id=fid, limit=200, order="asc")
    return d


def list_faults(conn, status="all", page=1, size=20, detail=False):
    where = {"active": " WHERE f.phase <> 'resolved'", "resolved": " WHERE f.phase = 'resolved'"}.get(status, "")
    total = conn.scalar("SELECT COUNT(*) AS n FROM faults f" + where)
    rows = conn.execute(_BASE + where + " ORDER BY f.id DESC LIMIT ? OFFSET ?",
                        (size, (page - 1) * size)).fetchall()
    items = [get_detail(conn, fid=r["id"]) if detail else _base(r) for r in rows]
    return {"items": items, "total": total, "page": page, "size": size}


def export_rows(conn):
    rows = conn.execute(_BASE + " ORDER BY f.id").fetchall()
    out = []
    for r in rows:
        b = _base(r)
        top = conn.execute("SELECT label, probability FROM fault_causes WHERE fault_id=? ORDER BY rank LIMIT 1",
                           (r["id"],)).fetchone()
        out.append([
            b["code"], b["type_name"], b["sub"] or "", b["line_name"], b["where"], b["severity"], b["phase_label"],
            r["created_at"] or "", b["created_clock"], r["analyzed_at"] or "", r["recovering_at"] or "",
            r["resolved_at"] or "", b["duration_sec"] if b["duration_sec"] is not None else "",
            b["created_by"] or "", b["recovered_by"] or "",
            f"{top['label']} ({top['probability']}%)" if top else "",
            b["impact_trains"] if b["impact_trains"] is not None else "", b["expected_delay_min"] or "",
            "시연" if b["source"] == "demo" else "수동",
        ])
    return out


# ------------------------------------------------------------------ 템플릿 (F10)
def _template_dict(conn, r):
    return {
        "id": r["id"], "fault_type": r["fault_type"], "sub_type": r["sub_type"], "name": r["name"],
        "code_prefix": r["code_prefix"], "default_severity": r["default_severity"],
        "summary_tpl": r["summary_tpl"], "delay_min": r["delay_min"], "delay_max": r["delay_max"],
        "causes": [{"label": c["label"], "base_prob": c["base_prob"]} for c in conn.execute(
            "SELECT label, base_prob FROM template_causes WHERE template_id=? ORDER BY id", (r["id"],))],
        "actions": [{"seq": a["seq"], "label": a["label"]} for a in conn.execute(
            "SELECT seq, label FROM template_actions WHERE template_id=? ORDER BY seq", (r["id"],))],
    }


def get_template(conn, fault_type, sub_type=None):
    r = conn.execute("SELECT * FROM fault_templates WHERE fault_type=? AND sub_type IS NOT DISTINCT FROM ?",
                     (fault_type, sub_type)).fetchone()
    return _template_dict(conn, r) if r else None


def get_template_by_id(conn, tid):
    r = conn.execute("SELECT * FROM fault_templates WHERE id=?", (tid,)).fetchone()
    return _template_dict(conn, r) if r else None


def list_templates(conn):
    return [_template_dict(conn, r) for r in conn.execute("SELECT * FROM fault_templates ORDER BY id").fetchall()]


def update_template(conn, tid, data):
    fields = {k: data[k] for k in ("name", "default_severity", "summary_tpl", "delay_min", "delay_max") if k in data}
    if fields:
        cols = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE fault_templates SET {cols} WHERE id=?", list(fields.values()) + [tid])
    if "causes" in data:
        conn.execute("DELETE FROM template_causes WHERE template_id=?", (tid,))
        conn.executemany("INSERT INTO template_causes(template_id, label, base_prob) VALUES (?,?,?)",
                         [(tid, c["label"], int(c["base_prob"])) for c in data["causes"]])
    if "actions" in data:
        conn.execute("DELETE FROM template_actions WHERE template_id=?", (tid,))
        conn.executemany("INSERT INTO template_actions(template_id, seq, label) VALUES (?,?,?)",
                         [(tid, i + 1, lbl) for i, lbl in enumerate(data["actions"])])
