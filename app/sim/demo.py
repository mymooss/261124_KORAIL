"""발표용 시연 모드 — 서버 타임라인 (지시서 7-7)."""
from dataclasses import dataclass, field

from ..repo import train_repo
from . import faults as faultmod
from .faults import EngineError

DSTEP = [0, 8, 14, 22, 32, 40]
CAPS = [
    "1단계 · 정상 운행: 전 노선이 초록색으로 표시되고 KPI가 안정적입니다. 열차들이 노선을 따라 정시 운행 중입니다.",
    "2단계 · 장애 발생: 경부선 대전–김천구미 구간에 신호 장애가 발생했습니다. 구간이 빨갛게 점멸하고 위험 경보가 발령됩니다. 진입 열차는 정차합니다.",
    "3단계 · AI 분석: AI가 센서·신호 이력 데이터를 분석해 추정 원인과 영향 범위, 권고 대응 절차를 제시합니다.",
    "4단계 · 대응 조치: 관제사가 권고 절차에 따라 후속 열차 정차, 유지보수팀 출동, 시스템 재부팅을 차례로 수행합니다.",
    "5단계 · 정상 복구: 구간이 노랑을 거쳐 초록으로 돌아오고, 열차가 정상 속도를 회복하며 KPI도 회복됩니다.",
]
END_CAPTION = "시연이 끝났습니다. '다시 보기'로 처음부터 재생하거나 '닫기'로 수동 관제를 계속할 수 있습니다."
TIMELINE = [("s1", 0), ("s2", 8), ("s3", 14), ("s4", 22), ("a0", 23.5), ("a1", 26.5), ("a2", 29.5),
            ("s5", 32), ("toast", 36), ("end", 40)]
DEMO_SEGMENT = "김천구미|대전"


@dataclass
class DemoState:
    active: bool = False
    elapsed: float = 0.0
    fired: set = field(default_factory=set)
    fault_code: str = None
    user: dict = None
    result: str = None  # 'done' | 'stopped' | None

    @classmethod
    def restore(cls, st, faults, user=None):
        d = cls(active=bool(st["demo_active"]), elapsed=float(st["demo_elapsed"]), user=user,
                result=st.get("demo_result"))
        if d.active:
            # 이미 지난 시점의 동작은 다시 실행하지 않는다
            d.fired = {k for k, tm in TIMELINE if tm <= d.elapsed}
            demo_f = [f for f in faults if f.source == "demo"]
            d.fault_code = demo_f[-1].code if demo_f else None
        return d


def step_index(t):
    for i in range(5):
        if DSTEP[i] <= t < DSTEP[i + 1]:
            return i
    return 4


def public(eng):
    """화면은 이 값(경과 시간)으로 스포트라이트·포커스·토스트 같은 연출을 직접 계산한다."""
    d = eng.demo
    if not d.active:
        return {"active": False, "result": d.result, "end_caption": END_CAPTION} if d.result == "done" else None
    i = step_index(d.elapsed)
    return {"active": True, "elapsed": round(d.elapsed, 2), "total": DSTEP[-1], "step": i + 1, "caption": CAPS[i],
            "fault_code": d.fault_code}


def _event(eng, **kw):
    d = eng.demo
    i = step_index(d.elapsed)
    payload = {"step": i + 1, "elapsed": round(d.elapsed, 2), "caption": CAPS[i], "spotlight": None, "focus": None,
               "select": None, "toast": None, "flash_action": None, "fit": False, "done": False, "stopped": False}
    payload.update(kw)
    eng.broadcast("demo", payload)


def _demo_fault(eng):
    code = eng.demo.fault_code
    return next((f for f in eng.faults if f.code == code), None) if code else None


def _fire(eng, key):
    d = eng.demo
    f = _demo_fault(eng)
    if key == "s1":
        _event(eng, spotlight="kpis")
    elif key == "s2":
        try:
            nf = faultmod.create_fault(eng, "signal", line_id="gb", segment_key=DEMO_SEGMENT, user=d.user,
                                       source="demo", defer=True)
            d.fault_code = nf.code
        except EngineError:
            d.fault_code = None
        _event(eng, spotlight="map", focus="대전", select="KTX 002")
    elif key == "s3":
        if f and f.phase == "detected":
            faultmod.analyze(eng, f, d.user)
        _event(eng, spotlight="fault")
    elif key == "s4":
        _event(eng, spotlight="fault")
    elif key in ("a0", "a1", "a2"):
        i = int(key[1])
        if f and f.phase == "analyzed" and not f.actions[i]["done"]:
            faultmod.complete_action(eng, f, i + 1, d.user)
        _event(eng, spotlight="fault", flash_action=i + 1)
    elif key == "s5":
        if f and f.phase == "analyzed" and all(a["done"] for a in f.actions):
            faultmod.recover(eng, f, d.user)
        _event(eng, spotlight="kpis", fit=True)
    elif key == "toast":
        eng.log("ok", "시연 완료: 정상 운행 복구 완료")
        _event(eng, spotlight="kpis", toast="✔ 정상 운행 복구 완료")
    elif key == "end":
        d.active = False
        d.result = "done"
        train_repo.save_sim_state(eng.conn, eng)
        _event(eng, done=True, caption=END_CAPTION, step=5)


def tick(eng, rdt):
    d = eng.demo
    if not d.active:
        return
    d.elapsed += rdt
    for key, tm in TIMELINE:
        if not d.active:
            break
        if d.elapsed >= tm and key not in d.fired:
            d.fired.add(key)
            try:
                _fire(eng, key)
            except EngineError:
                pass  # 다른 사용자가 이미 조작한 경우 등 — 시연은 계속 진행
