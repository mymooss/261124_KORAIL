/* 장애 이력 · 리포트 · KPI 추이 · 로그 검색 */
(function(){
"use strict";
const K = window.KTX;
const { $, esc, store } = K.util;

function setTheme(th){ document.documentElement.dataset.theme = th; $("btnTheme").textContent = th === "dark" ? "☀ 화이트 모드" : "🌙 다크 모드"; store.set("ktx-theme", th); }
$("btnTheme").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
setTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
K.applyPerms(document);

const dt = s => s ? s.replace("T", " ") : "-";
const dur = s => { if (s == null) return "-"; const m = Math.floor(s/60), r = s%60; return m ? m + "분 " + r + "초" : r + "초"; };
const SEV = s => "<span class='badge " + (s === "주의" ? "b-warn" : "b-bad") + "'>" + s + "</span>";
const PH = { detected:"b-ai", analyzing:"b-ai", analyzed:"b-act", recovering:"b-warn", resolved:"b-ok" };

/* ---------------- 장애 목록 ---------------- */
let page = 1, total = 0, selCode = null;
const SIZE = 15;
async function loadFaults(){
  const st = $("fStatus").value;
  try {
    const r = await K.api.get("/api/faults?status=" + st + "&page=" + page + "&size=" + SIZE);
    total = r.total;
    $("fRows").innerHTML = r.items.length ? r.items.map(f =>
      "<tr data-code='" + esc(f.code) + "'" + (f.code === selCode ? " class='sel'" : "") + "><td class='num'>" + esc(f.code) + "</td><td>" + esc(f.type_name + (f.sub ? "(" + f.sub + ")" : "")) +
      (f.source === "demo" ? " <span class='badge b-info'>시연</span>" : "") + "</td><td>" + esc(f.line_name + " " + f.where) + "</td><td>" + SEV(f.severity) +
      "</td><td class='num'>" + dt(f.created_at) + "</td><td class='num'>" + (f.resolved_at ? dt(f.resolved_at) : "<span class='badge " + PH[f.phase] + "'>" + esc(f.phase_label) + "</span>") +
      "</td><td class='num'>" + dur(f.duration_sec) + "</td><td>" + esc(f.recovered_by || "-") + "</td></tr>").join("")
      : "<tr><td colspan='8' class='empty'>표시할 장애가 없습니다.</td></tr>";
    const pages = Math.max(1, Math.ceil(total / SIZE));
    $("fInfo").textContent = "총 " + total + "건 · " + page + " / " + pages + " 페이지";
    $("fPrev").disabled = page <= 1; $("fNext").disabled = page >= pages;
  } catch(e) { K.toast(e.message); }
}
$("fStatus").onchange = () => { page = 1; loadFaults(); };
$("fPrev").onclick = () => { if (page > 1) { page--; loadFaults(); } };
$("fNext").onclick = () => { page++; loadFaults(); };
$("fRows").addEventListener("click", e => { const tr = e.target.closest("tr[data-code]"); if (!tr) return; selCode = tr.dataset.code;
  document.querySelectorAll("#fRows tr").forEach(x => x.classList.toggle("sel", x === tr)); loadReport(selCode); });

/* ---------------- 리포트 · 타임라인 ---------------- */
async function loadReport(code){
  const box = $("report");
  try {
    const f = await K.api.get("/api/faults/" + encodeURIComponent(code));
    const steps = [
      ["장애 발생", f.created_at, f.created_by ? "등록 " + f.created_by : ""],
      ["AI 분석 시작", f.analysis_started_at, ""],
      ["AI 분석 완료 (가상)", f.analyzed_at, f.causes[0] ? "추정 원인 " + f.causes[0].label + " " + f.causes[0].probability + "%" : ""],
    ];
    f.actions.forEach(a => steps.push(["조치 " + a.seq + ". " + a.label, a.done_at, a.done_by ? "수행 " + a.done_by : ""]));
    steps.push(["정상 복구 개시", f.recovering_at, f.recovered_by ? "승인 " + f.recovered_by : ""]);
    steps.push(["정상 운행 재개", f.resolved_at, ""]);
    box.innerHTML = "<div class='card'><div class='thead'><b style='font-size:14px'>" + f.icon + " " + esc(f.type_name + (f.sub ? " (" + f.sub + ")" : "")) + " · " + esc(f.code) + "</b>" + SEV(f.severity) + "</div>" +
      "<dl class='kv'><dt>발생 구간</dt><dd>" + esc(f.line_name + " " + f.where) + "</dd><dt>발생 시각(시뮬레이션)</dt><dd class='num'>" + f.created_clock + "</dd>" +
      "<dt>총 소요 시간</dt><dd class='num'>" + dur(f.duration_sec) + "</dd><dt>영향 열차</dt><dd>" + (f.affected_trains.length ? esc(f.affected_trains.join(", ")) : "-") + " (추정 " + (f.impact_trains ?? "-") + "편)</dd>" +
      "<dt>예상 지연</dt><dd>최대 " + (f.expected_delay_min ?? "-") + "분</dd><dt>신뢰도</dt><dd>" + (f.confidence ?? "-") + "%</dd></dl>" +
      "<div class='mini-t'>AI 분석 요약 (가상 분석 결과)</div><div class='summary'>" + esc(f.summary || "-") + "</div>" +
      "<div class='mini-t'>추정 원인</div>" + f.causes.map(c => "<div class='cause'><div class='ct'><span>" + esc(c.label) + "</span><b class='num'>" + c.probability + "%</b></div><div class='cbar'><i style='width:" + c.probability + "%'></i></div></div>").join("") +
      "<div class='mini-t'>처리 타임라인</div><ul class='timeline'>" + steps.map(s => "<li class='" + (s[1] ? "" : "pending") + "'>" + esc(s[0]) + "<span class='tt'>" + (s[1] ? dt(s[1]) : "대기") + "</span>" + (s[2] ? "<div class='hint' style='margin:2px 0 0'>" + esc(s[2]) + "</div>" : "") + "</li>").join("") + "</ul>" +
      "<div class='mini-t'>관련 로그 (" + f.logs.length + "건)</div><div class='hlog' style='max-height:220px'>" + f.logs.map(logRow).join("") + "</div></div>";
  } catch(e) { box.innerHTML = "<div class='card empty'>" + esc(e.message) + "</div>"; }
}

/* ---------------- KPI 추이 ---------------- */
async function loadKpi(){
  const min = $("kMin").value; const svg = $("kChart");
  try {
    const r = await K.api.get("/api/kpi/history?minutes=" + min);
    const it = r.items;
    $("kInfo").textContent = it.length ? it.length + "개 스냅샷 (5초 간격, 일시정지 중 제외)" : "";
    if (it.length < 2) { svg.innerHTML = "<text x='400' y='115' text-anchor='middle'>표시할 KPI 데이터가 아직 없습니다.</text>"; return; }
    const W = 800, H = 220, L = 36, R = 36, T = 12, B = 24;
    const n = it.length, x = i => L + i / (n - 1) * (W - L - R);
    const lo = Math.min(60, ...it.map(k => Math.min(k.on_time, k.safety)));
    const y = v => T + (100 - v) / (100 - lo || 1) * (H - T - B);
    const dmax = Math.max(4, ...it.map(k => k.delayed));
    const y2 = v => T + (1 - v / dmax) * (H - T - B);
    const line = (f, col) => "<polyline fill='none' stroke='" + col + "' stroke-width='2' vector-effect='non-scaling-stroke' points='" + it.map((k,i) => x(i).toFixed(1) + "," + f(k).toFixed(1)).join(" ") + "'/>";
    let g = "";
    [lo, (lo+100)/2, 100].forEach(v => { g += "<line x1='" + L + "' x2='" + (W-R) + "' y1='" + y(v) + "' y2='" + y(v) + "' stroke='var(--line)' stroke-dasharray='3 4'/><text x='4' y='" + (y(v)+3) + "'>" + Math.round(v) + "</text>"; });
    g += "<text x='" + (W-R+4) + "' y='" + (y2(dmax)+3) + "'>" + dmax + "</text><text x='" + (W-R+4) + "' y='" + (y2(0)+3) + "'>0</text>";
    const ticks = [0, Math.floor((n-1)/2), n-1];
    ticks.forEach(i => { g += "<text x='" + x(i) + "' y='" + (H-6) + "' text-anchor='middle'>" + esc(it[i].created_at.slice(11,19)) + "</text>"; });
    svg.innerHTML = g + line(k => y(k.on_time), "var(--ok)") + line(k => y(k.safety), "var(--accent)") + line(k => y2(k.delayed), "var(--bad)");
  } catch(e) { K.toast(e.message); }
}
$("kMin").onchange = loadKpi;

/* ---------------- 로그 검색 ---------------- */
const LOGCAT = { info:["정보","b-info"], ok:["정상","b-ok"], warn:["주의","b-warn"], danger:["위험","b-bad"], ai:["AI","b-ai"], action:["조치","b-act"], audit:["감사","b-info"] };
function logRow(ev){
  const c = LOGCAT[ev.category] || LOGCAT.info;
  return "<div class='le c-" + ev.category + "'><span class='t'>" + dt(ev.created_at) + "</span><span class='t'>" + esc(ev.sim_clock) + "</span><span class='badge " + c[1] + "'>" + c[0] + "</span><span>" + esc(ev.message) + (ev.user_name ? " <span style='color:var(--muted)'>· " + esc(ev.user_name) + "</span>" : "") + "</span></div>";
}
let nextBefore = null, shown = 0;
function filterQuery(){
  const cats = [...document.querySelectorAll("#eCats input:checked")].map(i => i.value);
  const q = new URLSearchParams();
  if (cats.length) q.set("category", cats.join(","));
  if ($("eFrom").value) q.set("from", $("eFrom").value);
  if ($("eTo").value) q.set("to", $("eTo").value);
  return q;
}
async function searchLogs(more){
  const q = filterQuery(); q.set("limit", "100");
  if (more && nextBefore) q.set("before_id", nextBefore);
  try {
    const r = await K.api.get("/api/events?" + q.toString());
    const html = r.items.map(logRow).join("");
    if (more) $("eList").insertAdjacentHTML("beforeend", html); else { $("eList").innerHTML = html || "<div class='card empty'>조건에 맞는 로그가 없습니다.</div>"; shown = 0; }
    shown += r.items.length; nextBefore = r.next_before_id;
    $("eInfo").textContent = shown + "건 표시"; $("eMore").disabled = !nextBefore;
  } catch(e) { K.toast(e.message); }
}
$("eSearch").onclick = () => searchLogs(false);
$("eMore").onclick = () => searchLogs(true);
$("eCsv").onclick = () => { location.href = "/api/events/export.csv?" + filterQuery().toString(); };
$("eDelete").onclick = () => {
  if (!confirm("저장된 이벤트 로그를 모두 삭제합니다. 되돌릴 수 없습니다. 계속할까요?")) return;
  K.api.act($("eDelete"), async () => { const r = await K.api.del("/api/events", { confirm:"DELETE" }); K.toast(r.deleted + "건을 삭제했습니다.", "info"); searchLogs(false); });
};

loadFaults(); loadKpi(); searchLogs(false);
setInterval(loadKpi, 15000);
})();
