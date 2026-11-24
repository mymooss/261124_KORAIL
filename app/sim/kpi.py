"""KPI 계산 (지시서 7-6)."""
from ..util import clamp
from .constants import SEVERITY_WEIGHT
from .faults import active, effective_inspection


def compute(eng):
    trains = eng.trains
    total = len(trains)
    delayed_list = [t for t in trains if t.delay >= 3]
    delayed = len(delayed_list)
    on_time = (total - delayed) / total * 100 if total else 100.0
    s = 100.0
    act = active(eng)
    for f in act:
        s -= SEVERITY_WEIGHT[f.severity] * (0.4 if f.phase == "recovering" else 1)
    for t in trains:
        for v in effective_inspection(eng, t).values():
            if v == "bad":
                s -= 3
            elif v == "warn":
                s -= 1
    s -= delayed * 0.5
    return {
        "total": total,
        "on_time": round(on_time, 1),
        "safety": round(clamp(s, 0, 100), 1),
        "delayed": delayed,
        "moving": sum(1 for t in trains if t.speed > 1),
        "avg_delay": round(sum(t.delay for t in delayed_list) / delayed, 1) if delayed else 0.0,
        "active_faults": len(act),
    }
