"""열차 이동·정차·회차·장애 반응 (지시서 11장)."""
import pytest

from app.sim import kpi as kpimod


def _isolate(engine, keep):
    """다른 열차의 영향을 없애기 위해 한 편만 남긴다."""
    engine.trains = [keep]
    engine.train_by_id = {keep.id: keep}
    engine.train_by_no = {keep.no: keep}


def test_dwell_then_depart(engine):
    t = engine.train_by_no["KTX 001"]
    _isolate(engine, t)
    t.dwell, t.speed, t.p = 10.0, 0.0, 0.0
    engine.step(6)
    assert t.speed == 0 and 0 < t.dwell <= 4.0001
    engine.step(10)
    assert t.dwell == 0
    assert t.speed > 0 and t.p > 0


def test_terminal_reverses_direction(engine):
    t = engine.train_by_no["KTX 001"]  # 경부선 하행
    _isolate(engine, t)
    st = engine.net["lines"][t.line]["stations"]
    t.st_idx, t.dir, t.p, t.speed, t.dwell = len(st) - 2, 1, 0.9999, 100.0, 0.0
    engine.step(2)
    assert t.st_idx == len(st) - 1
    assert t.dir == -1
    assert t.dwell == pytest.approx(150, abs=2.1)  # 같은 스텝 안에서 일부 감소할 수 있음


def test_signal_fault_stops_and_accumulates_delay(engine):
    t = engine.train_by_no["KTX 002"]
    _isolate(engine, t)
    t.dwell, t.p, t.speed, t.delay = 0.0, 0.1, 250.0, 0.0
    engine.create_fault("signal", segment_key=engine.train_seg(t))
    engine.step(120)
    assert t.speed == 0
    assert t.status == "정차"
    assert t.delay > 0.5


def test_track_fault_limits_speed(engine):
    t = engine.train_by_no["KTX 002"]
    _isolate(engine, t)
    t.dwell, t.p, t.speed = 0.0, 0.05, 280.0
    engine.create_fault("track", segment_key=engine.train_seg(t))
    engine.step(60)
    assert t.speed <= 60.0001
    assert t.status == "서행"


def test_delay_recovers_4_per_minute_after_fault(engine):
    t = engine.train_by_no["KTX 002"]
    _isolate(engine, t)
    engine.faults = []
    t.dwell, t.p, t.speed, t.delay = 0.0, 0.1, 250.0, 10.0
    engine.step(60)
    assert t.delay == pytest.approx(6.0, abs=0.01)


def test_kpi_counts_and_safety(engine):
    k = kpimod.compute(engine)
    assert k["total"] == 14
    assert k["on_time"] == 100.0
    assert k["safety"] == 99.0  # 객실 공조 warn 1건
    engine.create_fault("track", line_id="gb")
    k2 = kpimod.compute(engine)
    assert k2["safety"] < k["safety"]


def test_snapshot_shape(engine):
    s = engine.snapshot()
    assert s["sim"]["clock"] == "08:00:00"
    assert len(s["trains"]) == 14
    t0 = s["trains"][0]
    for key in ("no", "line", "dir", "st_idx", "p", "x", "y", "angle", "speed", "status", "delay"):
        assert key in t0
    assert s["demo"] is None
