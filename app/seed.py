"""초기 데이터 (노선·역·구간·열차·장애 템플릿·계정)."""
import random
import time

from werkzeug.security import generate_password_hash

from .sim.constants import INSP_ITEMS, START_SIM_TIME
from .sim.geo import haversine_km, seg_key
from .util import now_str

# id, 이름, 다크 색, 라이트 색, 역 순서
LINES = [
    ("gb", "경부선", "#00E5FF", "#0891B2",
     ["서울", "광명", "천안아산", "오송", "대전", "김천구미", "동대구", "신경주", "울산", "부산"]),
    ("hn", "호남선", "#60A5FA", "#2563EB",
     ["용산", "광명", "천안아산", "오송", "공주", "익산", "정읍", "광주송정", "나주", "목포"]),
    ("gr", "강릉선", "#9B8CFF", "#7C3AED",
     ["서울", "청량리", "양평", "만종", "횡성", "평창", "진부", "강릉"]),
    ("jr", "전라선", "#2DE2C0", "#0F9F86",
     ["용산", "광명", "천안아산", "오송", "공주", "익산", "전주", "남원", "순천", "여수EXPO"]),
]
LINE_STATIONS = {lid: st for lid, _n, _d, _l, st in LINES}

# 이름, 위도, 경도, 주요역, 라벨 dx, dy, 정렬
STATIONS = [
    ("서울", 37.60, 126.96, 1, -9, -3, "end"),
    ("용산", 37.50, 126.93, 1, -9, 9, "end"),
    ("광명", 37.40, 126.86, 0, -9, 5, "end"),
    ("청량리", 37.63, 127.08, 0, 8, -6, "start"),
    ("천안아산", 36.794, 127.104, 0, 9, 4, "start"),
    ("오송", 36.620, 127.327, 1, 9, 1, "start"),
    ("대전", 36.332, 127.434, 1, 9, 5, "start"),
    ("김천구미", 36.114, 128.181, 0, 0, -10, "middle"),
    ("동대구", 35.879, 128.628, 1, 9, -4, "start"),
    ("신경주", 35.798, 129.139, 0, 9, -3, "start"),
    ("울산", 35.551, 129.138, 0, 9, 4, "start"),
    ("부산", 35.115, 129.042, 1, 9, 12, "start"),
    ("공주", 36.390, 127.060, 0, -9, 4, "end"),
    ("익산", 35.940, 126.946, 1, -9, 1, "end"),
    ("정읍", 35.575, 126.844, 0, -9, 4, "end"),
    ("광주송정", 35.137, 126.793, 1, -9, -2, "end"),
    ("나주", 35.012, 126.718, 0, -9, 9, "end"),
    ("목포", 34.792, 126.385, 1, -9, 4, "end"),
    ("양평", 37.492, 127.492, 0, 0, -9, "middle"),
    ("만종", 37.371, 127.902, 0, -4, 15, "middle"),
    ("횡성", 37.468, 127.989, 0, 4, -9, "middle"),
    ("평창", 37.558, 128.416, 0, 0, -9, "middle"),
    ("진부", 37.640, 128.565, 0, 0, 15, "middle"),
    ("강릉", 37.764, 128.899, 1, 9, 4, "start"),
    ("전주", 35.849, 127.161, 1, 9, 1, "start"),
    ("남원", 35.410, 127.395, 0, 9, 4, "start"),
    ("순천", 34.945, 127.503, 1, 9, 1, "start"),
    ("여수EXPO", 34.753, 127.746, 1, 9, 11, "start"),
]
STATION_LL = {s[0]: (s[1], s[2]) for s in STATIONS}

MAX_SPEED = {
    "서울|청량리": 130, "광명|서울": 160, "광명|용산": 150, "양평|청량리": 200,
    "만종|양평": 230, "만종|횡성": 230, "평창|횡성": 230, "진부|평창": 230,
    "강릉|진부": 220, "익산|전주": 180, "남원|전주": 200, "남원|순천": 200,
    "순천|여수EXPO": 160,
}

# 노선, 방향, st_idx, progress — KTX 001 ~ KTX 014 순서
INIT_TRAINS = [
    ("gb", 1, 0, .30), ("gb", 1, 4, .55), ("gb", -1, 9, .20), ("gb", -1, 6, .60),
    ("hn", 1, 1, .40), ("hn", 1, 6, .30), ("hn", -1, 9, .50), ("hn", -1, 5, .20),
    ("gr", 1, 1, .50), ("gr", -1, 7, .40), ("gr", -1, 4, .70),
    ("jr", 1, 3, .60), ("jr", -1, 9, .30), ("jr", 1, 6, .20),
]

_SIG_SUM = ("{segment} 구간 궤도회로가 실제 열차 위치와 다르게 '점유' 상태로 표시되는 패턴이 감지되었습니다. "
            "설비 단락 가능성이 가장 높아 해당 구간 진입을 금지합니다.")
_TRK_SUM = ("{segment} 구간 궤도 검측 센서에서 레일 틀림 값이 기준치를 넘었습니다. "
            "탈선 위험을 줄이기 위해 즉시 서행 운전이 필요합니다.")
_WTH_SUM = "{line} {where}에 {sub} 특보 수준의 기상 데이터가 들어왔습니다. 운행 안전을 위해 해당 구간 감속 운행이 필요합니다."
_DLY_SUM = "차량 상태 데이터에서 출입문 닫힘 신호가 반복적으로 확인되지 않았습니다. 열차를 정차시킨 뒤 기기 점검이 필요합니다."
_WACTS = ["감속 운행 지시 (150km/h 제한)", "기상 감시 강화 및 선로 순회 점검", "운행 제한 해제 기준 확인"]

# type, sub, 이름, 코드, 심각도, 요약, 지연 최소, 최대, 원인, 조치
TEMPLATES = [
    ("signal", None, "신호 장애", "SIG", "위험", _SIG_SUM, 12, 18,
     [("궤도회로 단락", 72), ("신호기 전원 이상", 18), ("통신망 전송 지연", 10)],
     ["후속 열차 정차 지시", "신호 유지보수팀 긴급 출동", "신호 시스템 재부팅 및 정상 동작 확인"]),
    ("track", None, "선로 이상", "TRK", "심각", _TRK_SUM, 8, 14,
     [("레일 온도 변형(장출)", 61), ("레일 체결장치 이완", 27), ("노반 침하", 12)],
     ["서행 운전 지시 (60km/h 제한)", "선로 보수팀 긴급 출동", "궤도 검측 및 응급 보수 완료 확인"]),
    ("weather", "폭우", "기상 악화", "WTH", "주의", _WTH_SUM, 5, 10,
     [("시간당 강우량 운행기준 초과", 64), ("노반 배수 불량 우려", 24), ("시계 불량", 12)], _WACTS),
    ("weather", "강풍", "기상 악화", "WTH", "위험", _WTH_SUM, 5, 10,
     [("순간 풍속 25m/s 초과 돌풍", 66), ("전차선 진동 증가", 22), ("비산물 유입 우려", 12)], _WACTS),
    ("weather", "폭설", "기상 악화", "WTH", "위험", _WTH_SUM, 5, 10,
     [("적설량 운행기준 초과", 61), ("분기기 결빙", 27), ("전차선 착빙", 12)], _WACTS),
    ("delay", None, "열차 지연", "DLY", "주의", _DLY_SUM, 6, 11,
     [("출입문 개폐 장치 이상", 54), ("승하차 지연 누적", 30), ("차량 기기 경고 신호", 16)],
     ["해당 열차 출입문 장치 점검 지시", "후속 열차 운행 간격 조정", "승객 안내 방송 송출"]),
]


def _users(cfg):
    get = (cfg.get if hasattr(cfg, "get") else (lambda k, d=None: d))
    return [
        ("admin", get("ADMIN_PASSWORD", "admin1234!"), "관리자", "admin"),
        ("operator", get("OPERATOR_PASSWORD", "operator1234!"), "관제사", "operator"),
        ("viewer", get("VIEWER_PASSWORD", "viewer1234!"), "조회자", "viewer"),
    ]


def segment_table():
    """노선 순서대로 훑으며 공유 구간을 한 번만 만든다. {key: (a, b, length_km, max)}"""
    segs = {}
    for _lid, _n, _d, _l, st in LINES:
        for i in range(len(st) - 1):
            k = seg_key(st[i], st[i + 1])
            if k in segs:
                continue
            (la1, lo1), (la2, lo2) = STATION_LL[st[i]], STATION_LL[st[i + 1]]
            segs[k] = (st[i], st[i + 1], haversine_km(la1, lo1, la2, lo2) * 1.12, MAX_SPEED.get(k, 300))
    return segs


def seed_all(conn, cfg=None, rng=None):
    """시드 데이터를 넣는다. 이미 있으면 None."""
    """커밋은 호출자가 한다."""
    rng = rng or random.Random()
    cfg = cfg or {}
    if conn.scalar("SELECT COUNT(*) AS n FROM lines"):
        return None
    for order, (lid, name, cd, cl, _st) in enumerate(LINES):
        conn.execute("INSERT INTO lines(id,name,color_dark,color_light,sort_order) VALUES (?,?,?,?,?)",
                     (lid, name, cd, cl, order))
    sid = {}
    for name, lat, lon, major, dx, dy, anchor in STATIONS:
        sid[name] = conn.insert(
            "INSERT INTO stations(name,lat,lon,is_major,label_dx,label_dy,label_anchor) VALUES (?,?,?,?,?,?,?)",
            (name, lat, lon, major, dx, dy, anchor))
    conn.executemany("INSERT INTO line_stations(line_id,seq,station_id) VALUES (?,?,?)",
                     [(lid, seq, sid[name]) for lid, _n, _d, _l, st in LINES for seq, name in enumerate(st)])
    segs = segment_table()
    conn.executemany(
        "INSERT INTO segments(seg_key,station_a_id,station_b_id,length_km,max_speed_kmh) VALUES (?,?,?,?,?)",
        [(k, sid[a], sid[b], length, mx) for k, (a, b, length, mx) in segs.items()])
    for (ftype, sub, name, prefix, sev, summ, dmin, dmax, causes, acts) in TEMPLATES:
        tid = conn.insert(
            "INSERT INTO fault_templates(fault_type,sub_type,name,code_prefix,default_severity,summary_tpl,delay_min,delay_max)"
            " VALUES (?,?,?,?,?,?,?,?)", (ftype, sub, name, prefix, sev, summ, dmin, dmax))
        conn.executemany("INSERT INTO template_causes(template_id,label,base_prob) VALUES (?,?,?)",
                         [(tid, lbl, p) for lbl, p in causes])
        conn.executemany("INSERT INTO template_actions(template_id,seq,label) VALUES (?,?,?)",
                         [(tid, i + 1, lbl) for i, lbl in enumerate(acts)])
    users = _users(cfg)
    for username, pw, display, role in users:
        conn.execute("INSERT INTO users(username,password_hash,display_name,role,created_at) VALUES (?,?,?,?,?)",
                     (username, generate_password_hash(pw), display, role, now_str()))
    now = time.time()
    conn.execute("INSERT INTO sim_state(id,sim_time,last_real,last_hist_real,last_kpi_real,updated_at)"
                 " VALUES (1,?,?,?,?,?)", (START_SIM_TIME, now, now, now, now_str()))
    write_initial_trains(conn, rng)
    return {"노선": len(LINES), "역": len(STATIONS), "구간": len(segs), "열차": len(INIT_TRAINS),
            "장애 템플릿": len(TEMPLATES), "계정": len(users)}


def write_initial_trains(conn, rng, sim_time=START_SIM_TIME):
    """열차 14편을 초기 값으로 쓴다 (없으면 INSERT, 있으면 UPDATE). 커밋은 호출자가 한다."""
    seg_max = {k: v[3] for k, v in segment_table().items()}
    warn_idx = rng.randrange(len(INIT_TRAINS))
    ts = now_str()
    for i, (lid, d, st_idx, p) in enumerate(INIT_TRAINS):
        no = f"KTX {i + 1:03d}"
        st = LINE_STATIONS[lid]
        speed = seg_max[seg_key(st[st_idx], st[st_idx + d])] * 0.95
        vals = (lid, d, st_idx, p, speed, 0, 0, "정상운행", rng.randint(320, 880), rng.uniform(0, 10),
                int(sim_time - rng.randint(600, 5400)), ts)
        tid = conn.scalar("SELECT id FROM trains WHERE train_no=?", (no,))
        if tid:
            conn.execute(
                "UPDATE trains SET line_id=?,direction=?,st_idx=?,progress=?,speed_kmh=?,dwell_sec=?,delay_min=?,"
                "status=?,passengers=?,phase_seed=?,last_check_sim=?,updated_at=?,speed_hist='[]' WHERE id=?",
                vals + (tid,))
        else:
            tid = conn.insert(
                "INSERT INTO trains(line_id,direction,st_idx,progress,speed_kmh,dwell_sec,delay_min,status,"
                "passengers,phase_seed,last_check_sim,updated_at,train_no) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                vals + (no,))
        conn.execute("DELETE FROM train_inspections WHERE train_id=?", (tid,))
        conn.executemany(
            "INSERT INTO train_inspections(train_id,item,base_status) VALUES (?,?,?)",
            [(tid, item, "warn" if (i == warn_idx and item == "객실 공조") else "ok") for item in INSP_ITEMS])


def reset_sim(conn, rng=None):
    """열차·미해결 장애·sim_state 를 시드 값으로 되돌린다. 이벤트 로그와 해결된 장애 이력은 보존한다.
    장애 코드 중복을 막기 위해 fault_seq 는 되돌리지 않는다."""
    rng = rng or random.Random()
    conn.execute("DELETE FROM faults WHERE phase <> 'resolved'")
    write_initial_trains(conn, rng)
    now = time.time()
    conn.execute(
        "UPDATE sim_state SET sim_time=?, speed_mul=1, paused=0, demo_active=0, demo_elapsed=0, demo_result=NULL,"
        " demo_user_id=NULL, last_real=?, last_hist_real=?, last_kpi_real=?, fault_ver=fault_ver+1, updated_at=?"
        " WHERE id=1", (START_SIM_TIME, now, now, now, now_str()))
