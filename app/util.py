"""공통 유틸리티."""
import math
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DT_FMT = "%Y-%m-%d %H:%M:%S"
# 서버리스(Vercel)는 UTC 로 돌기 때문에 화면·로그 시각은 APP_TZ 기준으로 만든다.
TZ = ZoneInfo(os.environ.get("APP_TZ", "Asia/Seoul"))


def now_local():
    return datetime.now(TZ).replace(tzinfo=None)


def ago_str(**delta):
    """현재 시각에서 delta 만큼 뺀 시각 문자열 (보존 기간·조회 기간 계산용)."""
    return (now_local() - timedelta(**delta)).strftime(DT_FMT)


def clamp(v, a, b):
    return max(a, min(b, v))


def fmt_clock(t):
    """시뮬레이션 초 → HH:MM:SS (하루 순환)."""
    t = int(math.floor(t)) % 86400
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def now_str():
    return now_local().strftime(DT_FMT)


def iso(s):
    """'YYYY-MM-DD HH:MM:SS' → ISO 8601 (로컬)."""
    return s.replace(" ", "T") if s else None


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, DT_FMT)
    except ValueError:
        return None


def norm_dt_param(s, end=False):
    """쿼리 파라미터의 날짜/시각을 DB 비교용 문자열로 바꾼다. 잘못된 값이면 ValueError."""
    if not s:
        return None
    s = s.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if fmt == "%Y-%m-%d" and end:
            return d.strftime("%Y-%m-%d") + " 23:59:59"
        if fmt == "%Y-%m-%d %H:%M" and end:
            return d.strftime("%Y-%m-%d %H:%M") + ":59"
        return d.strftime(DT_FMT)
    raise ValueError(s)
