"""API·권한·CSV·SSE (지시서 8장, 11장)."""


def test_health_without_login(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_requires_login_401(client):
    r = client.get("/api/state")
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_page_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_bad_login(client):
    r = client.post("/login", data={"username": "operator", "password": "wrong"})
    assert r.status_code == 401


def test_viewer_cannot_operate_403(login_as):
    c = login_as("viewer")
    assert c.get("/api/state").status_code == 200
    r = c.post("/api/faults", json={"type": "signal"})
    assert r.status_code == 403
    assert r.get_json()["error"]["code"] == "FORBIDDEN"
    assert c.post("/api/sim/pause").status_code == 403


def test_operator_creates_fault_201(login_as):
    c = login_as("operator")
    r = c.post("/api/faults", json={"type": "signal", "line_id": "gb"})
    assert r.status_code == 201
    d = r.get_json()
    assert d["code"].startswith("F-") and d["created_by"] == "관제사"
    r2 = c.post(f"/api/faults/{d['code']}/actions/1/complete")
    assert r2.status_code == 409 and r2.get_json()["error"]["code"] == "INVALID_PHASE"
    assert c.post("/api/sim/reset").status_code == 403  # admin 전용


def test_invalid_speed_400(login_as):
    c = login_as("operator")
    assert c.post("/api/sim/speed", json={"mul": 3}).status_code == 400
    assert c.post("/api/sim/speed", json={"mul": "2"}).status_code == 400
    r = c.post("/api/sim/speed", json={"mul": 5})
    assert r.status_code == 200 and r.get_json()["mul"] == 5


def test_cross_origin_post_rejected(login_as):
    c = login_as("operator")
    r = c.post("/api/sim/pause", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def _age_analysis(db, code, sec=5):
    """분석 시작 시각을 과거로 돌려 다음 요청에서 분석이 끝나게 한다."""
    db.execute("UPDATE faults SET ana_epoch = ana_epoch - ? WHERE code=?", (sec, code))
    db.commit()


def test_action_log_records_user(db, login_as):
    c = login_as("operator")
    code = c.post("/api/faults", json={"type": "track", "line_id": "hn"}).get_json()["code"]
    _age_analysis(db, code)
    assert c.post(f"/api/faults/{code}/actions/1/complete").status_code == 200
    detail = c.get(f"/api/faults/{code}").get_json()
    assert detail["actions"][0]["done_by"] == "관제사"
    assert any(log["category"] == "action" and log["user_name"] == "관제사" for log in detail["logs"])


def test_events_pagination(db, login_as):
    from app.repo import event_repo
    for i in range(12):
        event_repo.insert(db, 28800, "info", f"테스트 로그 {i}")
    db.commit()
    c = login_as("viewer")
    r1 = c.get("/api/events?limit=5").get_json()
    assert len(r1["items"]) == 5 and r1["next_before_id"]
    ids1 = [e["id"] for e in r1["items"]]
    assert ids1 == sorted(ids1, reverse=True)
    r2 = c.get(f"/api/events?limit=5&before_id={r1['next_before_id']}").get_json()
    assert max(e["id"] for e in r2["items"]) < min(ids1)
    r3 = c.get(f"/api/events?since_id={ids1[1]}").get_json()
    assert [e["id"] for e in r3["items"]] == [ids1[0]]
    assert c.get("/api/events?category=bogus").status_code == 400


def test_csv_has_bom_and_header(login_as):
    c = login_as("viewer")
    r = c.get("/api/events/export.csv")
    assert r.status_code == 200
    assert r.data.startswith(b"\xef\xbb\xbf")
    first = r.data[3:].decode("utf-8").splitlines()[0]
    assert first.startswith("로그ID,실제 시각,시뮬레이션 시각,분류,메시지")
    r2 = c.get("/api/faults/export.csv")
    assert r2.data.startswith(b"\xef\xbb\xbf") and "장애번호" in r2.data.decode("utf-8-sig").splitlines()[0]


def test_admin_delete_events_requires_confirm(login_as):
    c = login_as("admin")
    assert c.delete("/api/events", json={}).status_code == 400
    r = c.delete("/api/events", json={"confirm": "DELETE"})
    assert r.status_code == 200


def test_admin_template_update(login_as):
    c = login_as("admin")
    t = c.get("/api/admin/templates/1").get_json()
    r = c.put("/api/admin/templates/1", json={"delay_min": 1, "delay_max": 2})
    assert r.status_code == 200 and r.get_json()["delay_max"] == 2
    assert c.put("/api/admin/templates/1", json={"delay_min": 5, "delay_max": 2}).status_code == 400
    assert t["fault_type"] == "signal"


def test_train_detail(login_as):
    c = login_as("viewer")
    d = c.get("/api/trains/KTX%20001").get_json()
    assert d["no"] == "KTX 001" and len(d["inspections"]) == 6
    assert c.get("/api/trains/KTX%20999").status_code == 404


def test_poll_returns_state_and_new_logs(db, login_as):
    c = login_as("viewer")
    r = c.get("/api/poll?since_id=0").get_json()
    assert len(r["state"]["trains"]) == 14
    assert "fault_ver" in r["state"]
    last = max([e["id"] for e in r["logs"]] or [0])
    from app.repo import event_repo
    event_repo.insert(db, 28800, "info", "새 로그")
    db.commit()
    r2 = c.get(f"/api/poll?since_id={last}").get_json()
    assert [e["message"] for e in r2["logs"]] == ["새 로그"]


def test_request_driven_time_advances(db, login_as):
    """요청 사이에 흐른 실제 시간만큼 시뮬레이션이 진행된다 (서버리스 엔진)."""
    c = login_as("operator")
    t0 = c.get("/api/state").get_json()["sim"]["time"]
    db.execute("UPDATE sim_state SET last_real = last_real - 2")  # 실제 2초가 흐른 것으로
    db.commit()
    c.post("/api/sim/speed", json={"mul": 1})  # 쓰기 요청이 시간을 진행시킨다
    t1 = c.get("/api/state").get_json()["sim"]["time"]
    assert 110 <= t1 - t0 <= 140  # 2초 × 60배 ≈ 120초


def test_full_fault_flow_over_requests(db, login_as):
    c = login_as("operator")
    code = c.post("/api/faults", json={"type": "signal", "line_id": "gb"}).get_json()["code"]
    _age_analysis(db, code)
    for seq in (1, 2, 3):
        assert c.post(f"/api/faults/{code}/actions/{seq}/complete").status_code == 200
    assert c.post(f"/api/faults/{code}/recover").status_code == 200
    db.execute("UPDATE faults SET rec_epoch = rec_epoch - 5 WHERE code=?", (code,))
    db.commit()
    c.post("/api/sim/speed", json={"mul": 1})
    assert c.get(f"/api/faults/{code}").get_json()["phase"] == "resolved"


def test_demo_runs_to_done(db, login_as):
    c = login_as("operator")
    assert c.post("/api/demo/start").status_code == 200
    for _ in range(9):  # 실제 시간 5초씩 9번 = 45초
        db.execute("UPDATE sim_state SET last_real = last_real - 5")
        db.execute("UPDATE faults SET ana_epoch = ana_epoch - 5 WHERE ana_epoch IS NOT NULL")
        db.execute("UPDATE faults SET rec_epoch = rec_epoch - 5 WHERE rec_epoch IS NOT NULL")
        db.commit()
        c.post("/api/sim/speed", json={"mul": 1})
    demo = c.get("/api/state").get_json()["demo"]
    assert demo == {"active": False, "result": "done", "end_caption": demo["end_caption"]}
    faults = c.get("/api/faults?status=resolved").get_json()["items"]
    assert any(f["source"] == "demo" and f["recovered_by"] == "관제사" for f in faults)
