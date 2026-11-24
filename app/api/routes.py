"""REST API (지시서 8장)."""
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, request

from .. import get_engine
from ..auth.decorators import current_user, login_required, role_required
from ..db import get_db
from ..repo import event_repo, fault_repo, kpi_repo, network_repo
from ..sim.constants import CATEGORIES
from ..sim.faults import analysis_progress
from ..util import norm_dt_param

bp = Blueprint("api", __name__, url_prefix="/api")


def engine(write=True):
    return get_engine(write)


def err(code, message, status):
    return jsonify(error={"code": code, "message": message}), status


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _int_arg(name, default, lo=None, hi=None):
    v = request.args.get(name)
    if v in (None, ""):
        return default
    try:
        v = int(v)
    except ValueError:
        raise ValueError(name)
    if lo is not None and v < lo:
        raise ValueError(name)
    if hi is not None:
        v = min(v, hi)
    return v


def _csv(header, rows, filename):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    data = ("﻿" + buf.getvalue()).encode("utf-8")
    return Response(data, content_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ------------------------------------------------------------------ 조회
@bp.get("/health")
def health():
    db_ok = "ok"
    try:
        get_db().execute("SELECT 1 AS x FROM sim_state").fetchone()
    except Exception:
        db_ok = "error"
    return jsonify(status="ok" if db_ok == "ok" else "degraded", db=db_ok,
                   engine="request-driven", database="postgres" if current_app.config["DATABASE_URL"] else "sqlite")


@bp.get("/me")
@login_required
def me():
    return jsonify(current_user())


@bp.get("/network")
@login_required
def network():
    return jsonify(network_repo.public_network(network_repo.load_network(get_db())))


@bp.get("/state")
@login_required
def state():
    return jsonify(engine(write=False).snapshot())


@bp.get("/poll")
@login_required
def poll():
    """SSE 대신 쓰는 1초 polling: 상태 스냅샷 + since_id 이후의 새 로그."""
    eng = engine(write=False)
    res = {"state": eng.snapshot(), "logs": []}
    since = request.args.get("since_id", "")
    if since.isdigit():
        logs = event_repo.query(get_db(), since_id=int(since), limit=200, order="asc")
        res["logs"] = logs
    return jsonify(res)


@bp.get("/trains/<train_no>")
@login_required
def train_detail(train_no):
    return jsonify(engine(write=False).train_detail(train_no))


@bp.get("/faults")
@login_required
def faults_list():
    status = request.args.get("status", "all")
    if status not in ("active", "resolved", "all"):
        return err("BAD_REQUEST", "status 는 active, resolved, all 중 하나여야 합니다.", 400)
    try:
        page = _int_arg("page", 1, lo=1)
        size = _int_arg("size", 20, lo=1, hi=100)
    except ValueError as e:
        return err("BAD_REQUEST", f"{e} 값이 올바르지 않습니다.", 400)
    detail = request.args.get("detail") in ("1", "true")
    res = fault_repo.list_faults(get_db(), status, page, size, detail=detail)
    if detail:
        eng = engine(write=False)
        prog = {f.code: f for f in eng.faults}
        now = eng.clock()
        for d in res["items"]:
            f = prog.get(d["code"])
            d["progress"] = analysis_progress(eng, f, now) if f else 1.0
    return jsonify(res)


@bp.get("/faults/export.csv")
@login_required
def faults_export():
    header = ["장애번호", "유형", "세부", "노선", "구간", "심각도", "단계", "발생(실제)", "발생(시뮬레이션)", "분석 완료",
              "복구 개시", "해결", "소요 시간(초)", "발생자", "복구자", "추정 원인 1순위", "영향 열차", "예상 지연(분)", "출처"]
    return _csv(header, fault_repo.export_rows(get_db()), f"faults_{_stamp()}.csv")


@bp.get("/faults/<code>")
@login_required
def fault_detail(code):
    d = fault_repo.get_detail(get_db(), code=code, with_logs=True)
    if d is None:
        return err("NOT_FOUND", f"장애를 찾을 수 없습니다: {code}", 404)
    return jsonify(d)


def _event_filters():
    cats = [c for c in (request.args.get("category") or "").split(",") if c]
    bad = [c for c in cats if c not in CATEGORIES]
    if bad:
        raise ValueError("category")
    frm = norm_dt_param(request.args.get("from"))
    to = norm_dt_param(request.args.get("to"), end=True)
    return cats, frm, to


@bp.get("/events")
@login_required
def events():
    try:
        cats, frm, to = _event_filters()
        limit = _int_arg("limit", 100, lo=1, hi=500)
        since_id = _int_arg("since_id", None, lo=0)
        before_id = _int_arg("before_id", None, lo=0)
    except ValueError as e:
        return err("BAD_REQUEST", f"{e} 값이 올바르지 않습니다.", 400)
    order = "asc" if since_id is not None and before_id is None else "desc"
    items = event_repo.query(get_db(), categories=cats, since_id=since_id, before_id=before_id, limit=limit,
                             frm=frm, to=to, order=order)
    if order == "asc":
        items.reverse()  # 응답은 항상 최신순
    next_before = items[-1]["id"] if len(items) == limit else None
    return jsonify(items=items, next_before_id=next_before)


@bp.get("/events/export.csv")
@login_required
def events_export():
    try:
        cats, frm, to = _event_filters()
    except ValueError as e:
        return err("BAD_REQUEST", f"{e} 값이 올바르지 않습니다.", 400)
    rows = event_repo.query(get_db(), categories=cats, frm=frm, to=to, limit=None, order="asc")
    label = {"info": "정보", "ok": "정상", "warn": "주의", "danger": "위험", "ai": "AI", "action": "조치", "audit": "감사"}
    header = ["로그ID", "실제 시각", "시뮬레이션 시각", "분류", "메시지", "장애번호", "열차", "사용자"]
    data = [[r["id"], (r["created_at"] or "").replace("T", " "), r["sim_clock"], label.get(r["category"], r["category"]),
             r["message"], r["fault_code"] or "", r["train_no"] or "", r["user_name"] or ""] for r in rows]
    return _csv(header, data, f"events_{_stamp()}.csv")


@bp.get("/kpi/history")
@login_required
def kpi_history():
    try:
        minutes = _int_arg("minutes", 30, lo=1, hi=7 * 24 * 60)
    except ValueError:
        return err("BAD_REQUEST", "minutes 값이 올바르지 않습니다.", 400)
    return jsonify(items=kpi_repo.history(get_db(), minutes), minutes=minutes)


# ------------------------------------------------------------------ 조작 (operator 이상)
@bp.post("/faults")
@role_required("operator")
def fault_create():
    b = body()
    ftype = b.get("type")
    if not ftype:
        return err("BAD_REQUEST", "type 이 필요합니다. (signal, track, weather, delay)", 400)
    d = engine().create_fault(ftype, line_id=b.get("line_id"), segment_key=b.get("segment_key"),
                              train_no=b.get("train_no"), user=current_user())
    return jsonify(d), 201


@bp.post("/faults/<code>/analyze")
@role_required("operator")
def fault_analyze(code):
    return jsonify(engine().analyze(code, user=current_user()))


@bp.post("/faults/<code>/actions/<int:seq>/complete")
@role_required("operator")
def fault_action(code, seq):
    return jsonify(engine().complete_action(code, seq, user=current_user()))


@bp.post("/faults/<code>/recover")
@role_required("operator")
def fault_recover(code):
    return jsonify(engine().recover(code, user=current_user()))


@bp.post("/sim/pause")
@role_required("operator")
def sim_pause():
    return jsonify(engine().set_paused(True, user=current_user()))


@bp.post("/sim/resume")
@role_required("operator")
def sim_resume():
    return jsonify(engine().set_paused(False, user=current_user()))


@bp.post("/sim/speed")
@role_required("operator")
def sim_speed():
    mul = body().get("mul")
    if isinstance(mul, bool) or not isinstance(mul, int):
        return err("BAD_REQUEST", "배속은 1, 2, 5 중 하나여야 합니다.", 400)
    return jsonify(engine().set_speed(mul, user=current_user()))


@bp.post("/demo/start")
@role_required("operator")
def demo_start():
    return jsonify(engine().demo_start(user=current_user()))


@bp.post("/demo/stop")
@role_required("operator")
def demo_stop():
    return jsonify(engine().demo_stop(user=current_user()))


# ------------------------------------------------------------------ 관리 (admin)
@bp.post("/sim/reset")
@role_required("admin")
def sim_reset():
    return jsonify(engine().reset(user=current_user()))


@bp.delete("/events")
@role_required("admin")
def events_delete():
    if body().get("confirm") != "DELETE":
        return err("BAD_REQUEST", '삭제하려면 본문에 {"confirm":"DELETE"} 가 필요합니다.', 400)
    conn = get_db()
    n = event_repo.delete_all(conn)
    user = current_user()
    event_repo.audit(conn, f"이벤트 로그 전체 삭제 ({n}건) · 수행자 {user['display_name']}", user["id"])
    return jsonify(deleted=n)


@bp.get("/admin/templates")
@role_required("admin")
def templates_list():
    return jsonify(items=fault_repo.list_templates(get_db()))


@bp.get("/admin/templates/<int:tid>")
@role_required("admin")
def template_get(tid):
    t = fault_repo.get_template_by_id(get_db(), tid)
    if t is None:
        return err("NOT_FOUND", "템플릿을 찾을 수 없습니다.", 404)
    return jsonify(t)


@bp.put("/admin/templates/<int:tid>")
@role_required("admin")
def template_put(tid):
    conn = get_db()
    cur = fault_repo.get_template_by_id(conn, tid)
    if cur is None:
        return err("NOT_FOUND", "템플릿을 찾을 수 없습니다.", 404)
    b = body()
    data = {}
    for k in ("name", "summary_tpl"):
        if k in b:
            if not isinstance(b[k], str) or not b[k].strip():
                return err("BAD_REQUEST", f"{k} 는 비어 있지 않은 문자열이어야 합니다.", 400)
            data[k] = b[k].strip()
    if "default_severity" in b:
        if b["default_severity"] not in ("주의", "위험", "심각"):
            return err("BAD_REQUEST", "default_severity 는 주의, 위험, 심각 중 하나여야 합니다.", 400)
        data["default_severity"] = b["default_severity"]
    dmin, dmax = b.get("delay_min", cur["delay_min"]), b.get("delay_max", cur["delay_max"])
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (dmin, dmax)) or dmin > dmax:
        return err("BAD_REQUEST", "delay_min, delay_max 는 0 이상의 정수이고 delay_min ≤ delay_max 여야 합니다.", 400)
    if "delay_min" in b:
        data["delay_min"] = dmin
    if "delay_max" in b:
        data["delay_max"] = dmax
    if "causes" in b:
        cs = b["causes"]
        if (not isinstance(cs, list) or not cs or not all(
                isinstance(c, dict) and isinstance(c.get("label"), str) and c["label"].strip()
                and isinstance(c.get("base_prob"), int) and 0 <= c["base_prob"] <= 100 for c in cs)):
            return err("BAD_REQUEST", "causes 는 {label, base_prob(0~100)} 목록이어야 합니다.", 400)
        data["causes"] = cs
    if "actions" in b:
        acts = b["actions"]
        if isinstance(acts, list):
            acts = [a.get("label") if isinstance(a, dict) else a for a in acts]
        if not isinstance(acts, list) or not acts or not all(isinstance(a, str) and a.strip() for a in acts):
            return err("BAD_REQUEST", "actions 는 비어 있지 않은 문자열 목록이어야 합니다.", 400)
        data["actions"] = [a.strip() for a in acts]
    fault_repo.update_template(conn, tid, data)
    user = current_user()
    event_repo.audit(conn, f"장애 템플릿 수정: {cur['name']}{'(' + cur['sub_type'] + ')' if cur['sub_type'] else ''}"
                           f" · 수행자 {user['display_name']}", user["id"])
    return jsonify(fault_repo.get_template_by_id(conn, tid))


@bp.errorhandler(ValueError)
def _value_error(e):
    return err("BAD_REQUEST", f"입력 값이 올바르지 않습니다: {e}", 400)
