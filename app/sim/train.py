"""열차 이동·제약 계산 (지시서 7-3, 7-4)."""
import math

from ..util import clamp
from .geo import seg_key

_RANK = {"stop": 3, "slow": 2, "caution": 1}


class Constraint:
    __slots__ = ("stop", "cap", "mode", "fault")

    def __init__(self):
        self.stop = False
        self.cap = 999.0
        self.mode = None
        self.fault = None

    def set(self, mode, cap, fault):
        if mode == "stop":
            self.stop = True
        self.cap = min(self.cap, cap)
        if self.mode is None or _RANK[mode] > _RANK[self.mode]:
            self.mode = mode
            self.fault = fault


def constraint(eng, t, key):
    """장애가 열차에 주는 제약. 우선순위 stop > slow > caution, cap 은 최솟값."""
    c = Constraint()
    for f in eng.faults:
        if f.phase == "resolved":
            continue
        rec = f.phase == "recovering"
        if f.type == "delay":
            if f.target_train_id == t.id:
                c.set("caution", 200, f) if rec else c.set("stop", 0, f)
            continue
        if key not in f.segs:
            continue
        if f.type == "signal":
            c.set("caution", 150, f) if rec else c.set("stop", 0, f)
        elif f.type == "track":
            c.set("caution", 150, f) if rec else c.set("slow", 60, f)
        elif f.type == "weather":
            c.set("caution", 200 if rec else (110 if f.seg_lv.get(key) == "danger" else 150), f)
    return c


def seg_name(net, key):
    s = net["segments"][key]
    return f"{s['a']}–{s['b']}"


def step_train(eng, t, dt):
    net = eng.net
    line = net["lines"][t.line]
    st = line["stations"]
    key = seg_key(st[t.st_idx], st[t.st_idx + t.dir])
    seg = net["segments"][key]
    c = constraint(eng, t, key)
    base = seg["max_speed"] * (0.93 + 0.05 * math.sin(eng.t / 45 + t.phase))
    mode = None
    if t.dwell > 0:
        t.speed = 0.0
        if c.stop:
            mode = "stop"
            t.dwell = max(t.dwell, 1)
            t.delay += dt / 60
        else:
            t.dwell -= dt
            t.delay = max(0.0, t.delay - dt / 60 * 4)
            if t.dwell <= 0:
                t.dwell = 0.0
                t.pax = int(clamp(t.pax + eng.rng.randint(-120, 120), 200, 950))
                if eng.rng.random() < 0.22:
                    late = t.delay >= 1
                    eng.log("warn" if late else "info",
                            f"{t.no} {st[t.st_idx]}역 " + (f"{round(t.delay)}분 지연 출발" if late else "정시 출발")
                            + f" ({line['name']})", train=t)
    else:
        target = base
        if c.stop:
            target = 0.0
            mode = "stop"
        elif c.cap < target:
            target = c.cap
            mode = c.mode
        remain = (1 - t.p) * seg["length_km"]
        if not c.stop:
            target = min(target, max(25.0, math.sqrt(max(0.0, remain)) * 160))
        if t.speed < target:
            t.speed = min(target, t.speed + 3 * dt)
        else:
            t.speed = max(target, t.speed - 7 * dt)
        t.p += t.speed / 3600 * dt / seg["length_km"]
        if mode:
            t.delay += dt / 60 * clamp(1 - t.speed / max(base, 1), 0, 1)
        else:
            t.delay = max(0.0, t.delay - dt / 60 * 4)
        if t.p >= 1:
            t.st_idx += t.dir
            t.p = 0.0
            t.speed = 0.0
            if t.st_idx + t.dir < 0 or t.st_idx + t.dir >= len(st):
                t.dir = -t.dir
                t.dwell = 150.0
                eng.log("info", f"{t.no} {st[t.st_idx]}역 도착 · 회차 준비 ({line['name']})", train=t)
            else:
                t.dwell = 50.0
    if mode and c.fault is not None:
        eng.mark_affected(c.fault, t)
    t.mode = mode
    if mode == "stop":
        ns = "정차"
    elif mode == "slow":
        ns = "서행"
    elif mode == "caution":
        ns = "주의운행"
    elif t.delay >= 3:
        ns = "지연"
    else:
        ns = "정상운행"
    if ns != t.status:
        where = f"{st[t.st_idx]}역" if t.dwell > 0 else seg_name(net, key)
        cat = "danger" if ns == "정차" else ("ok" if ns == "정상운행" else "warn")
        eng.log(cat, f"{t.no} 상태 변경: {t.status} → {ns} ({where})", train=t)
        t.status = ns
