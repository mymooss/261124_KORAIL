"""장애 상태머신 (지시서 7-5, 11장)."""
import pytest

from app.sim.faults import EngineError


def _finish_analysis(engine):
    engine.process_timers(engine.clock() + 2.0)


def test_cause_probabilities_sum_to_100(engine):
    for ftype in ("signal", "track", "weather", "delay"):
        for _ in range(5):
            try:
                d = engine.create_fault(ftype)
            except EngineError as e:
                assert e.code == "NO_TARGET_TRAIN"
                continue
            probs = [c["probability"] for c in d["causes"]]
            assert sum(probs) == 100
            assert probs == sorted(probs, reverse=True)


def test_action_before_analysis_rejected(engine):
    d = engine.create_fault("signal", line_id="gb")
    assert d["phase"] == "analyzing"
    with pytest.raises(EngineError) as ei:
        engine.complete_action(d["code"], 1)
    assert ei.value.code == "INVALID_PHASE" and ei.value.status == 409


def test_recover_with_incomplete_actions_rejected(engine):
    d = engine.create_fault("track", line_id="hn")
    _finish_analysis(engine)
    engine.complete_action(d["code"], 1)
    with pytest.raises(EngineError) as ei:
        engine.recover(d["code"])
    assert ei.value.code == "ACTIONS_INCOMPLETE"


def test_already_done_action_rejected(engine):
    d = engine.create_fault("signal", line_id="gb")
    _finish_analysis(engine)
    engine.complete_action(d["code"], 1)
    with pytest.raises(EngineError) as ei:
        engine.complete_action(d["code"], 1)
    assert ei.value.code == "ALREADY_DONE"


def test_full_flow_to_resolved(engine):
    d = engine.create_fault("signal", line_id="gb")
    code = d["code"]
    _finish_analysis(engine)
    f = next(x for x in engine.faults if x.code == code)
    assert f.phase == "analyzed" and f.impact >= 1
    for seq in (1, 2, 3):
        engine.complete_action(code, seq)
    engine.recover(code)
    assert f.phase == "recovering"
    engine.process_timers(engine.clock() + 3.5)
    assert all(x.code != code for x in engine.faults)
    row = engine.conn.execute("SELECT phase, resolved_at FROM faults WHERE code=?", (code,)).fetchone()
    assert row["phase"] == "resolved" and row["resolved_at"]
    with pytest.raises(EngineError) as ei:
        engine.analyze(code)
    assert ei.value.code == "INVALID_PHASE"


def test_delay_without_target_train(engine):
    n = sum(1 for t in engine.trains if t.line == "gr")
    for _ in range(n):
        engine.create_fault("delay", line_id="gr")
    with pytest.raises(EngineError) as ei:
        engine.create_fault("delay", line_id="gr")
    assert ei.value.code == "NO_TARGET_TRAIN" and ei.value.status == 409


def test_weather_three_segments_middle_danger(engine):
    d = engine.create_fault("weather", line_id="gb")
    segs = d["segments"]
    assert len(segs) == 3
    f = next(x for x in engine.faults if x.code == d["code"])
    levels = [f.seg_lv[k] for k in f.segs]
    assert levels == ["warn", "danger", "warn"]
    assert d["sub"] in ("폭우", "강풍")


def test_restart_restores_unresolved_fault(app, engine):
    d = engine.create_fault("track", line_id="gb")
    _finish_analysis(engine)
    engine.complete_action(d["code"], 1)
    engine.step(30)
    engine._persist()
    engine.conn.commit()
    t_before = engine.t
    # 새 엔진 인스턴스로 다시 읽는다 (서버 재시작 / 다른 서버리스 인스턴스 흉내)
    from app.db import connect
    from app.sim.engine import SimulationEngine
    eng2 = SimulationEngine(connect(app.config["DATABASE_PATH"]))
    eng2.load()
    try:
        f2 = next(x for x in eng2.faults if x.code == d["code"])
        assert f2.phase == "analyzed"
        assert f2.actions[0]["done"] and not f2.actions[1]["done"]
        assert eng2.t == pytest.approx(t_before)
    finally:
        eng2.close()
