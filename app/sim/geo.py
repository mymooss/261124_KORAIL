"""좌표 투영·거리 계산."""
import math

VIEWBOX = (0, 0, 610, 880)


def px(lon):
    return 20 + (lon - 125.9) * 153.9


def py(lat):
    return 15 + (38.7 - lat) * 190


def haversine_km(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    dla = (lat2 - lat1) * r
    dlo = (lon2 - lon1) * r
    s = math.sin(dla / 2) ** 2 + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin(dlo / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(s))


def seg_key(a, b):
    """역명을 정렬해 'A|B' 형태의 구간 키를 만든다."""
    return f"{a}|{b}" if a < b else f"{b}|{a}"
