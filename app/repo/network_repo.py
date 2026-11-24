"""노선·역·구간 마스터."""
from ..sim.geo import px, py


def load_network(conn):
    lines = {}
    order = []
    for r in conn.execute("SELECT * FROM lines ORDER BY sort_order"):
        lines[r["id"]] = {"id": r["id"], "name": r["name"], "color_dark": r["color_dark"],
                          "color_light": r["color_light"], "stations": []}
        order.append(r["id"])
    stations = {}
    by_id = {}
    for r in conn.execute("SELECT * FROM stations ORDER BY id"):
        s = {"id": r["id"], "name": r["name"], "lat": r["lat"], "lon": r["lon"], "is_major": bool(r["is_major"]),
             "label_dx": r["label_dx"], "label_dy": r["label_dy"], "label_anchor": r["label_anchor"],
             "x": round(px(r["lon"]), 2), "y": round(py(r["lat"]), 2)}
        stations[r["name"]] = s
        by_id[r["id"]] = s
    for r in conn.execute("SELECT line_id, seq, station_id FROM line_stations ORDER BY line_id, seq"):
        lines[r["line_id"]]["stations"].append(by_id[r["station_id"]]["name"])
    segments = {}
    for r in conn.execute("SELECT * FROM segments ORDER BY id"):
        segments[r["seg_key"]] = {"id": r["id"], "key": r["seg_key"], "a": by_id[r["station_a_id"]]["name"],
                                  "b": by_id[r["station_b_id"]]["name"], "length_km": r["length_km"],
                                  "max_speed": r["max_speed_kmh"], "lines": []}
    for lid in order:
        st = lines[lid]["stations"]
        for i in range(len(st) - 1):
            a, b = st[i], st[i + 1]
            k = f"{a}|{b}" if a < b else f"{b}|{a}"
            if k in segments and lid not in segments[k]["lines"]:
                segments[k]["lines"].append(lid)
    return {"lines": lines, "line_order": order, "stations": stations, "segments": segments}


def public_network(net):
    """/api/network 응답 형식."""
    return {
        "viewBox": [0, 0, 610, 880],
        "lines": [{"id": lid, "name": net["lines"][lid]["name"], "color_dark": net["lines"][lid]["color_dark"],
                   "color_light": net["lines"][lid]["color_light"], "stations": net["lines"][lid]["stations"]}
                  for lid in net["line_order"]],
        "stations": list(net["stations"].values()),
        "segments": [{"key": s["key"], "a": s["a"], "b": s["b"], "length_km": round(s["length_km"], 2),
                      "max_speed": s["max_speed"], "lines": s["lines"]} for s in net["segments"].values()],
    }
