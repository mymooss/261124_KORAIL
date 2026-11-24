"""장애 생성·분석·조치·복구 상태머신 (지시서 7-5)."""
from dataclasses import dataclass, field

from ..repo import fault_repo, train_repo
from ..util import clamp, now_str
from .constants import ANALYSIS_SEC, INSP_OVERRIDES, RECOVER_SEC, TYPE_META
from .geo import seg_key
from .train import seg_name


class EngineError(Exception):
    """API 로 그대로 전달되는 엔진 오류."""

    def __init__(self, code, message, status=409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class Fault:
    id: int
    code: str
    type: str
    sub: str
    line: str
    target_train_id: int
    segs: list
    seg_lv: dict
    severity: str
    phase: str
    where: str
    summary: str
    confidence: int
    impact: int
    expected_delay: int
    causes: list
    actions: list
    affected: set = field(default_factory=set)
    created_sim: int = 0
    source: str = "manual"
    created_by: int = None
    ana_start: float = None
    rec_start: float = None

    @classmethod
    def from_db(cls, d):
        return cls(
            id=d["id"], code=d["code"], type=d["fault_type"], sub=d["sub_type"], line=d["line_id"],
            target_train_id=d["target_train_id"], segs=[k for k, _ in d["segs"]], seg_lv=dict(d["segs"]),
            severity=d["severity"], phase=d["phase"], where=d["location_text"], summary=d["summary"],
            confidence=d["confidence"], impact=d["impact_trains"], expected_delay=d["expected_delay_min"],
            causes=[list(c) for c in d["causes"]], actions=d["actions"], affected=set(d["affected"]),
            created_sim=d["created_sim"], source=d["source"], created_by=d["created_by"],
            ana_start=d.get("ana_epoch"), rec_start=d.get("rec_epoch"))


def _uid(user):
    return user["id"] if user else None


def _by(user):
    return f" · 수행자 {user['display_name']}" if user else ""


def active(eng):
    return [f for f in eng.faults if f.phase != "resolved"]


def jitter_causes(rng, causes):
    """원인 확률을 ±5 흔든 뒤 합이 100이 되게 맞추고 내림차순 정렬."""
    a = [[lbl, max(3, p + rng.randint(-5, 5))] for lbl, p in causes]
    s = sum(p for _, p in a) or 1
    a = [[lbl, round(p / s * 100)] for lbl, p in a]
    a.sort(key=lambda c: -c[1])
    a[0][1] += 100 - sum(p for _, p in a)
    a.sort(key=lambda c: -c[1])
    return a


def _render(tpl, **kw):
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", v or "")
    return tpl


def create_fault(eng, ftype, line_id=None, segment_key=None, train_no=None, user=None, source="manual",
                 defer=False):
    if ftype not in TYPE_META:
        raise EngineError("BAD_REQUEST", "알 수 없는 장애 유형입니다. (signal, track, weather, delay)", 400)
    net, rng = eng.net, eng.rng
    target = None
    if train_no:
        target = eng.train_by_no.get(train_no)
        if target is None:
            raise EngineError("NOT_FOUND", f"열차를 찾을 수 없습니다: {train_no}", 404)
        if line_id and line_id not in ("rand", target.line):
            raise EngineError("BAD_REQUEST", "열차가 지정한 노선에 속하지 않습니다.", 400)
        line_id = target.line
    if segment_key:
        if segment_key not in net["segments"]:
            raise EngineError("BAD_REQUEST", f"구간을 찾을 수 없습니다: {segment_key}", 400)
        seg_lines = net["segments"][segment_key]["lines"]
        if line_id and line_id != "rand" and line_id not in seg_lines:
            raise EngineError("BAD_REQUEST", "구간이 지정한 노선에 속하지 않습니다.", 400)
        if not line_id or line_id == "rand":
            line_id = seg_lines[0]
    if not line_id or line_id == "rand":
        line_id = rng.choice(net["line_order"])
    if line_id not in net["lines"]:
        raise EngineError("BAD_REQUEST", f"알 수 없는 노선입니다: {line_id}", 400)

    L = net["lines"][line_id]
    st = L["stations"]
    act = active(eng)
    busy = {k for f in act for k in f.segs}
    on_line = [t for t in eng.trains if t.line == line_id]
    segs, lv, sub, tgt_id, affected = [], {}, None, None, set()
    t = None
    if ftype == "delay":
        busy_trains = {f.target_train_id for f in act if f.type == "delay"}
        if target is not None:
            if target.id in busy_trains:
                raise EngineError("NO_TARGET_TRAIN", f"{target.no}에는 이미 지연 장애가 진행 중입니다.", 409)
            t = target
        else:
            cand = [x for x in on_line if x.id not in busy_trains]
            if not cand:
                raise EngineError("NO_TARGET_TRAIN", f"{L['name']}에 지연 장애를 추가로 발생시킬 열차가 없습니다.", 409)
            t = rng.choice(cand)
        tgt_id = t.id
        k = eng.train_seg(t)
        segs, lv[k] = [k], "warn"
        affected.add(t.id)
    elif ftype == "weather":
        t = target or rng.choice(on_line)
        i0 = int(clamp(min(t.st_idx, t.st_idx + t.dir) - 1, 0, len(st) - 4))
        for i in range(i0, i0 + 3):
            k = seg_key(st[i], st[i + 1])
            segs.append(k)
            lv[k] = "danger" if i == i0 + 1 else "warn"
        sub = "폭설" if line_id == "gr" else rng.choice(["폭우", "강풍"])
    else:
        key = segment_key
        if not key:
            src = [target] if target else on_line
            cand = [eng.train_seg(x) for x in src if eng.train_seg(x) not in busy]
            if cand:
                key = rng.choice(cand)
            else:
                i = rng.randint(0, len(st) - 2)
                key = seg_key(st[i], st[i + 1])
        segs, lv[key] = [key], "danger"

    tpl = fault_repo.get_template(eng.conn, ftype, sub)
    if not tpl or not tpl["causes"] or not tpl["actions"]:
        raise EngineError("TEMPLATE_MISSING", "장애 분석 템플릿이 없습니다. 관리자에게 문의하세요.", 500)
    causes = jitter_causes(rng, [(c["label"], c["base_prob"]) for c in tpl["causes"]])
    actions = [{"seq": i + 1, "label": a["label"], "done": False} for i, a in enumerate(tpl["actions"])]
    if ftype == "delay":
        where = f"{t.no} ({seg_name(net, segs[0])})"
    elif ftype == "weather":
        where = f"{seg_name(net, segs[0]).split('–')[0]}–{net['segments'][segs[2]]['b']} 일대"
    else:
        where = seg_name(net, segs[0])
    summary = _render(tpl["summary_tpl"], segment=seg_name(net, segs[0]), line=L["name"], where=where, sub=sub)

    eng.fault_seq += 1
    now = eng.clock()
    f = Fault(id=None, code=f"F-{eng.fault_seq:03d}", type=ftype, sub=sub, line=line_id, target_train_id=tgt_id,
              segs=segs, seg_lv=lv, severity=tpl["default_severity"], phase="detected" if defer else "analyzing",
              where=where, summary=summary, confidence=rng.randint(88, 97), impact=None,
              expected_delay=rng.randint(tpl["delay_min"], tpl["delay_max"]), causes=causes, actions=actions,
              affected=affected, created_sim=int(eng.t), source=source, created_by=_uid(user),
              ana_start=None if defer else now)
    f.id = fault_repo.insert_fault(eng.conn, f, net, analysis_started_at=None if defer else now_str())
    train_repo.save_sim_state(eng.conn, eng)
    eng.faults.append(f)
    tn = TYPE_META[ftype]["name"] + (f"({sub})" if sub else "")
    eng.log("danger", f"[{tn}] {L['name']} {where} 장애 발생 · 장애번호 {f.code}", fault=f, user=user)
    eng.log("danger", f"위험 경보 발령: {L['name']} {where} · 심각도 {f.severity}", fault=f)
    if not defer:
        eng.log("ai", f"AI 원인 분석 시작 ({f.code}) · 센서·신호·기상 데이터 상관 분석", fault=f)
    eng.broadcast("alarm", {"code": f.code, "severity": f.severity})
    eng.emit_fault(f)
    return f


def analyze(eng, f, user=None):
    if f.phase != "detected":
        raise EngineError("INVALID_PHASE", "AI 분석 대기 상태의 장애만 분석을 시작할 수 있습니다.")
    f.phase = "analyzing"
    f.ana_start = eng.clock()
    fault_repo.update_fault(eng.conn, f.id, phase="analyzing", analysis_started_at=now_str(), ana_epoch=f.ana_start)
    eng.log("ai", f"AI 원인 분석 시작 ({f.code}) · 센서·신호·기상 데이터 상관 분석", fault=f, user=user)
    eng.emit_fault(f)


def finish_analysis(eng, f):
    f.phase = "analyzed"
    near = set(f.affected)
    for t in eng.trains:
        st = eng.net["lines"][t.line]["stations"]
        for k in f.segs:
            s = eng.net["segments"][k]
            if s["a"] not in st or s["b"] not in st:
                continue
            lo = min(st.index(s["a"]), st.index(s["b"]))
            if abs(t.st_idx - lo) <= 2:
                near.add(t.id)
    f.impact = max(1, len(near))
    fault_repo.update_fault(eng.conn, f.id, phase="analyzed", analyzed_at=now_str(), impact_trains=f.impact)
    top = f.causes[0]
    eng.log("ai", f"AI 분석 완료 ({f.code}): 추정 원인 '{top[0]}' {top[1]}% · 영향 열차 {f.impact}편 · "
                  f"예상 지연 최대 {f.expected_delay}분 (가상 분석 결과)", fault=f)
    eng.emit_fault(f)


def complete_action(eng, f, seq, user=None):
    if f.phase != "analyzed":
        if f.phase == "recovering":
            raise EngineError("INVALID_PHASE", "이미 복구가 진행 중입니다.")
        raise EngineError("INVALID_PHASE", "AI 분석이 끝난 뒤에 조치할 수 있습니다.")
    a = next((x for x in f.actions if x["seq"] == seq), None)
    if a is None:
        raise EngineError("NOT_FOUND", f"조치 {seq}번을 찾을 수 없습니다.", 404)
    if a["done"]:
        raise EngineError("ALREADY_DONE", "이미 완료된 조치입니다.")
    a["done"] = True
    fault_repo.action_done(eng.conn, f.id, seq, _uid(user))
    eng.log("action", f"조치 수행: {a['label']} ({f.code}){_by(user)}", fault=f, user=user)
    if all(x["done"] for x in f.actions):
        eng.log("ok", f"필수 대응 조치 완료 · 정상 복구 승인 대기 ({f.code})", fault=f)
    eng.emit_fault(f)


def recover(eng, f, user=None):
    if f.phase != "analyzed":
        if f.phase == "recovering":
            raise EngineError("INVALID_PHASE", "이미 복구가 진행 중입니다.")
        raise EngineError("INVALID_PHASE", "AI 분석이 끝난 뒤에 복구할 수 있습니다.")
    if not all(x["done"] for x in f.actions):
        raise EngineError("ACTIONS_INCOMPLETE", "모든 대응 조치를 완료한 뒤 복구할 수 있습니다.")
    f.phase = "recovering"
    f.rec_start = eng.clock()
    fault_repo.update_fault(eng.conn, f.id, phase="recovering", recovering_at=now_str(), recovered_by=_uid(user),
                            rec_epoch=f.rec_start)
    eng.log("action", f"정상 복구 절차 개시 ({f.code}) · 구간 점검 후 단계적 운행 재개{_by(user)}", fault=f, user=user)
    eng.emit_fault(f)


def resolve(eng, f):
    f.phase = "resolved"
    for tid in f.affected:
        t = eng.train_by_id.get(tid)
        if t:
            t.last_check = eng.t
    fault_repo.update_fault(eng.conn, f.id, phase="resolved", resolved_at=now_str())
    L = eng.net["lines"][f.line]
    eng.log("ok", f"정상 복구 완료: {L['name']} {f.where} 정상 운행 재개 ({f.code})", fault=f)
    eng.faults.remove(f)
    eng.emit_fault(f)


def process_timers(eng, now):
    """실제 시간 기준 자동 전이: 분석 1.7초, 복구 3초."""
    for f in list(eng.faults):
        if f.phase == "analyzing" and f.ana_start is not None and now - f.ana_start >= ANALYSIS_SEC:
            finish_analysis(eng, f)
        elif f.phase == "recovering" and f.rec_start is not None and now - f.rec_start >= RECOVER_SEC:
            resolve(eng, f)


def analysis_progress(eng, f, now):
    if f.phase == "detected":
        return 0.0
    if f.phase == "analyzing":
        return round(clamp((now - (f.ana_start or now)) / ANALYSIS_SEC, 0, 1), 3)
    return 1.0


def segment_levels(eng):
    lv = {}
    for f in active(eng):
        for k in f.segs:
            if f.phase == "recovering":
                lvl = "warn"
            elif f.type in ("signal", "track"):
                lvl = "danger"
            else:
                lvl = f.seg_lv.get(k, "warn")
            if lv.get(k) != "danger":
                lv[k] = lvl
    return lv


def effective_inspection(eng, t):
    r = dict(t.insp)
    for f in active(eng):
        if t.id in f.affected:
            r.update(INSP_OVERRIDES[f.type])
    return r
