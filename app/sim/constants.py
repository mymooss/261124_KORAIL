"""시뮬레이션 공통 상수."""

TYPE_META = {
    "signal": {"name": "신호 장애", "code": "SIG", "icon": "⚠"},
    "track": {"name": "선로 이상", "code": "TRK", "icon": "⛓"},
    "weather": {"name": "기상 악화", "code": "WTH", "icon": "☔"},
    "delay": {"name": "열차 지연", "code": "DLY", "icon": "⏱"},
}

SEVERITY_WEIGHT = {"심각": 22, "위험": 15, "주의": 7}

INSP_ITEMS = ["제동장치", "출입문", "대차·차륜", "전력·팬터그래프", "신호수신(ATP)", "객실 공조"]

# 미해결 장애가 영향 열차의 점검 항목에 주는 덮어쓰기 (7-6)
INSP_OVERRIDES = {
    "signal": {"신호수신(ATP)": "bad"},
    "track": {"대차·차륜": "warn"},
    "weather": {"전력·팬터그래프": "warn"},
    "delay": {"출입문": "bad", "제동장치": "warn"},
}

CATEGORIES = ("info", "ok", "warn", "danger", "ai", "action", "audit")
PHASES = ("detected", "analyzing", "analyzed", "recovering", "resolved")
PHASE_LABEL = {
    "detected": "AI 분석 대기",
    "analyzing": "AI 분석 중",
    "analyzed": "대응 조치 중",
    "recovering": "복구 진행 중",
    "resolved": "해결됨",
}

START_SIM_TIME = 8 * 3600
ANALYSIS_SEC = 1.7
RECOVER_SEC = 3.0
SPEED_MULS = (1, 2, 5)
