"""SimulationEngine — 요청 기반(서버리스) 시뮬레이션.

Vercel 같은 서버리스 환경에서는 백그라운드 스레드가 계속 돌 수 없다. 그래서
요청이 올 때마다 DB에서 상태를 읽고 → 마지막 진행 시각 이후 흐른 실제 시간만큼 시뮬레이션을 진행하고
→ 다시 DB에 저장한다. 여러 요청이 동시에 오면 sim_state 행 잠금(FOR UPDATE)으로 한 번에 하나만 진행한다.
"""
import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from ..repo import event_repo, fault_repo, kpi_repo, network_repo, train_repo
from ..util import fmt_clock
from . import demo as demomod
from . import faults as faultmod
from . import kpi as kpimod
from . import train as trainmod
from .constants import INSP_ITEMS, SPEED_MULS, TYPE_META
from .faults import EngineError, Fault  # noqa: F401  (EngineError 는 앱에서 import)
from .geo import seg_key

logger = logging.getLogger(__name__)

# 노선·역·구간은 바뀌지 않으므로 프로세스 안에서 한 번만 읽는다.
_NET_CACHE = {}


@dataclass
class Train:
    id: int
    no: str
    line: str
    dir: int
    st_idx: int
    p: float
    speed: float
    dwell: float
    delay: float
    status: str
    pax: int
    phase: float
    last_check: float
    insp: dict
    mode: str = None
    hist: deque = field(default_factory=lambda: deque(maxlen=60))

    @classmethod
    def from_db(cls, d):
        return cls(id=d["id"], no=d["train_no"], line=d["line_id"], dir=d["direction"], st_idx=d["st_idx"],
                   p=d["progress"], speed=d["speed_kmh"], dwell=d["dwell_sec"], delay=d["delay_min"],
                   status=d["status"], pax=d["passengers"], phase=d["phase_seed"],
                   last_check=d["last_check_sim"], insp=d["insp"], hist=deque(d.get("hist", []), maxlen=60))


class SimulationEngine:
    MAX_CATCHUP = 10.0   # 한 번에 따라잡는 최대 실제 시간(초). 오래 비어 있던 뒤 순간이동 방지.
    MIN_TICK = 0.3       # 이보다 짧은 간격의 조회는 시간을 진행하지 않고 읽기만 한다.
    HIST_INTERVAL = 1.0
    KPI_INTERVAL = 5.0

    def __init__(self, conn, clock=time.time, seed=None):
        import random
        self.conn = conn
        self.clock = clock
        self.rng = random.Random(seed)
        self.lock = threading.RLock()  # 같은 요청 안에서의 재진입용
        self.loaded = False
        self.dirty = False
        self.demo = demomod.DemoState()

    # ------------------------------------------------------------ 적재·진행
    @classmethod
    def open(cls, conn, write=True, now=None):
        """요청용 엔진. write=True 이면 상태 행을 잠그고 흐른 시간만큼 진행한다."""
        eng = cls(conn)
        now = eng.clock() if now is None else now
        if not write:
            last = conn.scalar("SELECT last_real FROM sim_state WHERE id=1")
            if last is not None and now - float(last) < cls.MIN_TICK:
                eng.load()
                return eng
        conn.lock_state()
        eng.load()
        eng.catch_up(now)
        return eng

    def load(self):
        c = self.conn
        st = train_repo.load_sim_state(c)
        if st is None:
            raise RuntimeError("데이터베이스가 준비되지 않았습니다. 스키마 적용 후 'flask seed' 를 먼저 실행하세요.")
        key = getattr(c, "target", "")
        if key not in _NET_CACHE or not _NET_CACHE[key]["lines"]:
            _NET_CACHE[key] = network_repo.load_network(c)
        self.net = _NET_CACHE[key]
        self.t = float(st["sim_time"])
        self.mul = int(st["speed_mul"])
        self.paused = bool(st["paused"])
        self.fault_seq = max(int(st["fault_seq"]), fault_repo.max_code_seq(c))
        self.last_real = float(st.get("last_real") or 0) or self.clock()
        self.last_hist_real = float(st.get("last_hist_real") or 0)
        self.last_kpi_real = float(st.get("last_kpi_real") or 0)
        self.fault_ver = int(st.get("fault_ver") or 0)
        self.trains = [Train.from_db(d) for d in train_repo.load_trains(c)]
        self.train_by_id = {t.id: t for t in self.trains}
        self.train_by_no = {t.no: t for t in self.trains}
        self.faults = [Fault.from_db(d) for d in fault_repo.load_active(c)]
        now = self.clock()
        for f in self.faults:
            if f.phase == "analyzing" and f.ana_start is None:
                f.ana_start = now
            if f.phase == "recovering" and f.rec_start is None:
                f.rec_start = now
        demo_user = None
        if st.get("demo_user_id"):
            r = c.execute("SELECT id, display_name FROM users WHERE id=?", (st["demo_user_id"],)).fetchone()
            demo_user = {"id": r["id"], "display_name": r["display_name"]} if r else None
        self.demo = demomod.DemoState.restore(st, self.faults, demo_user)
        self.loaded = True

    def ensure_loaded(self):
        if not self.loaded:
            self.load()

    def catch_up(self, now=None):
        """마지막 진행 이후 흐른 실제 시간만큼 시뮬레이션을 진행하고 저장한다."""
        now = self.clock() if now is None else now
        rdt = min(self.MAX_CATCHUP, max(0.0, now - self.last_real))
        self.last_real = now
        with self.lock:
            if not self.paused and rdt > 0:
                self.step(rdt * 60 * self.mul)
                demomod.tick(self, rdt)
            faultmod.process_timers(self, now)
            if not self.paused:
                if now - self.last_hist_real >= self.HIST_INTERVAL:
                    self.last_hist_real = now
                    for t in self.trains:
                        t.hist.append(round(t.speed, 1))
                if now - self.last_kpi_real >= self.KPI_INTERVAL:
                    self.last_kpi_real = now
                    k = kpimod.compute(self)
                    kpi_repo.insert(self.conn, self.t, k, k["active_faults"])
            self._persist()

    def tick(self, rdt, now=None):
        """테스트·호환용: rdt 초가 흐른 것으로 보고 진행한다."""
        now = self.clock() if now is None else now
        self.last_real = now - rdt
        self.catch_up(now)

    def step(self, sim_dt):
        """시뮬레이션 시간을 sim_dt 초 진행한다 (2초 이하 하위 스텝). 테스트에서 직접 호출한다."""
        if sim_dt <= 0:
            return
        with self.lock:
            self.t += sim_dt
            n = max(1, math.ceil(sim_dt / 2))
            d = sim_dt / n
            for _ in range(n):
                for t in self.trains:
                    trainmod.step_train(self, t, d)

    def process_timers(self, now=None):
        with self.lock:
            faultmod.process_timers(self, self.clock() if now is None else now)

    def _persist(self):
        train_repo.save_trains(self.conn, self.trains)
        train_repo.save_sim_state(self.conn, self)

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------ 이벤트 (polling 으로 전달)
    def broadcast(self, event, data, eid=None):
        """SSE 대신 polling 을 쓰므로 별도 전송은 없다. 장애 변경은 fault_ver 로 알린다."""
        if event in ("fault", "alarm"):
            self.fault_ver += 1

    def log(self, category, message, fault=None, train=None, user=None):
        eid, _created = event_repo.insert(
            self.conn, self.t, category, message,
            fault_id=fault.id if fault is not None else None,
            train_id=train.id if train is not None else None,
            user_id=user["id"] if user else None)
        return eid

    def audit(self, message, user=None):
        return self.log("audit", message, user=user)

    def emit_fault(self, f):
        self.fault_ver += 1

    def mark_affected(self, f, t):
        if t.id not in f.affected:
            f.affected.add(t.id)
            fault_repo.add_affected(self.conn, f.id, t.id)

    # ------------------------------------------------------------ 조회
    def train_seg(self, t):
        st = self.net["lines"][t.line]["stations"]
        return seg_key(st[t.st_idx], st[t.st_idx + t.dir])

    def train_xy(self, t):
        st = self.net["lines"][t.line]["stations"]
        a = self.net["stations"][st[t.st_idx]]
        b = self.net["stations"][st[t.st_idx + t.dir]]
        x = a["x"] + (b["x"] - a["x"]) * t.p
        y = a["y"] + (b["y"] - a["y"]) * t.p
        ang = math.degrees(math.atan2(b["y"] - a["y"], b["x"] - a["x"]))
        return x, y, ang

    def snapshot(self):
        self.ensure_loaded()
        now = self.clock()
        trains = []
        for t in self.trains:
            x, y, ang = self.train_xy(t)
            trains.append({"no": t.no, "line": t.line, "dir": t.dir, "st_idx": t.st_idx, "p": round(t.p, 4),
                           "x": round(x, 2), "y": round(y, 2), "angle": round(ang, 1),
                           "speed": round(t.speed, 1), "status": t.status, "delay": round(t.delay, 2),
                           "dwell": round(t.dwell, 1), "pax": t.pax, "seg": self.train_seg(t)})
        faults = [{"code": f.code, "type": f.type, "type_name": TYPE_META[f.type]["name"], "sub": f.sub,
                   "line": f.line, "line_name": self.net["lines"][f.line]["name"], "where": f.where,
                   "phase": f.phase, "severity": f.severity, "source": f.source,
                   "progress": faultmod.analysis_progress(self, f, now)} for f in faultmod.active(self)]
        return {
            "sim": {"time": int(self.t), "clock": fmt_clock(self.t), "mul": self.mul, "paused": self.paused},
            "trains": trains,
            "segments": faultmod.segment_levels(self),
            "kpi": kpimod.compute(self),
            "faults": faults,
            "fault_ver": self.fault_ver,
            "demo": demomod.public(self),
            "server_time": now,
        }

    def train_detail(self, no):
        self.ensure_loaded()
        t = self.train_by_no.get(no)
        if t is None:
            raise EngineError("NOT_FOUND", f"열차를 찾을 수 없습니다: {no}", 404)
        L = self.net["lines"][t.line]
        st = L["stations"]
        key = self.train_seg(t)
        seg = self.net["segments"][key]
        ins = faultmod.effective_inspection(self, t)
        x, y, ang = self.train_xy(t)
        return {
            "no": t.no, "line": t.line, "line_name": L["name"], "dir": t.dir,
            "dir_label": "하행" if t.dir > 0 else "상행",
            "from": st[0] if t.dir > 0 else st[-1], "to": st[-1] if t.dir > 0 else st[0],
            "current": st[t.st_idx], "next": st[t.st_idx + t.dir], "st_idx": t.st_idx, "p": round(t.p, 4),
            "x": round(x, 2), "y": round(y, 2), "angle": round(ang, 1),
            "seg": key, "seg_max": seg["max_speed"],
            "remain_km": None if t.dwell > 0 else round((1 - t.p) * seg["length_km"], 1),
            "speed": round(t.speed, 1), "status": t.status, "delay": round(t.delay, 2),
            "dwell": round(t.dwell, 1), "pax": t.pax,
            "last_check": int(t.last_check), "last_check_clock": fmt_clock(t.last_check),
            "inspections": [{"item": i, "status": ins.get(i, "ok")} for i in INSP_ITEMS],
            "speed_history": list(t.hist),
        }

    # ------------------------------------------------------------ 명령
    def _fault(self, code):
        for f in self.faults:
            if f.code == code:
                return f
        if fault_repo.find_code(self.conn, code):
            raise EngineError("INVALID_PHASE", "이미 해결된 장애입니다.")
        raise EngineError("NOT_FOUND", f"장애를 찾을 수 없습니다: {code}", 404)

    def _detail(self, f):
        d = fault_repo.get_detail(self.conn, fid=f.id)
        d["progress"] = faultmod.analysis_progress(self, f, self.clock())
        return d

    def _done(self):
        train_repo.save_sim_state(self.conn, self)

    def create_fault(self, ftype, line_id=None, segment_key=None, train_no=None, user=None):
        self.ensure_loaded()
        f = faultmod.create_fault(self, ftype, line_id=line_id, segment_key=segment_key, train_no=train_no, user=user)
        self._done()
        return self._detail(f)

    def analyze(self, code, user=None):
        self.ensure_loaded()
        f = self._fault(code)
        faultmod.analyze(self, f, user)
        self._done()
        return self._detail(f)

    def complete_action(self, code, seq, user=None):
        self.ensure_loaded()
        f = self._fault(code)
        faultmod.complete_action(self, f, seq, user)
        self._done()
        return self._detail(f)

    def recover(self, code, user=None):
        self.ensure_loaded()
        f = self._fault(code)
        faultmod.recover(self, f, user)
        self._done()
        return self._detail(f)

    def set_paused(self, paused, user=None):
        self.ensure_loaded()
        if self.paused != paused:
            self.paused = paused
            self.log("info", "시뮬레이션 " + ("일시정지" if paused else "재생"), user=user)
            self._done()
        return {"paused": self.paused}

    def set_speed(self, mul, user=None):
        if mul not in SPEED_MULS:
            raise EngineError("BAD_REQUEST", "배속은 1, 2, 5 중 하나여야 합니다.", 400)
        self.ensure_loaded()
        if self.mul != mul:
            self.mul = mul
            self.log("info", f"시뮬레이션 속도 변경: {mul}배속", user=user)
            self._done()
        return {"mul": self.mul}

    def _reset_core(self):
        from ..seed import reset_sim
        reset_sim(self.conn, self.rng)
        self.load()

    def reset(self, user=None):
        self.ensure_loaded()
        self._reset_core()
        name = user["display_name"] if user else "시스템"
        self.log("audit", f"시뮬레이션 초기화 · 수행자 {name}", user=user)
        self.log("info", "시뮬레이션 초기화 완료 · 전 열차 초기 위치로 복귀", user=user)
        self.fault_ver += 1
        self._done()
        return {"ok": True}

    def demo_start(self, user=None):
        self.ensure_loaded()
        self._reset_core()
        a, b = self.train_by_no["KTX 001"], self.train_by_no["KTX 002"]
        a.st_idx, a.dir, a.p, a.dwell, a.speed = 3, 1, 0.0, 30.0, 0.0
        b.st_idx, b.dir, b.p, b.speed, b.dwell = 4, 1, 0.05, 200.0, 0.0
        self.mul = 1
        self.paused = False
        self.demo = demomod.DemoState(active=True, elapsed=0.0, user=user)
        self.log("info", "발표용 시연 모드 시작", user=user)
        demomod.tick(self, 0.0)
        self.fault_ver += 1
        self._persist()
        return {"ok": True}

    def demo_stop(self, user=None):
        self.ensure_loaded()
        if self.demo.active:
            self.demo.active = False
            self.demo.result = "stopped"
            self.log("info", "시연 모드 중지 · 수동 관제 모드로 전환", user=user)
            self._done()
        return {"ok": True}
