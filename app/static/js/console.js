/* 진입점: 초기 동기화 · polling 처리 · 버튼 · 렌더 루프 */
(function(){
"use strict";
const K = window.KTX;
const { $, store } = K.util;
const UI = K.ui;

K.state = null;
K.faults = new Map();
K.selTrain = null;
K.selFault = null;
K.detail = null;
K.demoFaultCode = null;
const POLL_MS = parseInt(document.body.dataset.pollMs || "1000", 10) || 1000;

/* 조작 직후에는 다음 polling 을 기다리지 않고 바로 상태·로그·장애를 다시 받는다 */
async function refreshNow(){
  try { const res = await K.api.get("/api/poll?since_id=" + (UI.maxLogId || 0)); onState(res.state); res.logs.forEach(UI.addLog); } catch(e) {}
  loadFaults();
}
K.onActed = refreshNow;

/* ---------------- 상태 수신 ---------------- */
let lastStateAt = 0, emaInterval = 1000, faultVer = null, knownFaults = null;
function onState(st){
  const now = performance.now();
  if (lastStateAt) { emaInterval = emaInterval * 0.7 + Math.min(3000, now - lastStateAt) * 0.3; K.setStateInterval(emaInterval); }
  lastStateAt = now;
  K.state = st;
  // 장애가 바뀌었으면 장애 상세를 다시 받는다 (SSE 'fault' 이벤트 대체)
  if (faultVer !== null && st.fault_ver !== faultVer) loadFaults();
  faultVer = st.fault_ver;
  // 새 장애가 생기면 경보음 (SSE 'alarm' 이벤트 대체)
  const codes = st.faults.map(f => f.code);
  if (knownFaults && codes.some(c => !knownFaults.has(c))) UI.beep();
  knownFaults = new Set(codes);
  K.map.setTrains(st.trains, now);
  K.map.setSegments(st.segments);
  UI.renderHeader(); UI.kpiSubs(); UI.renderList(); UI.renderDetail(); UI.updateAnalysis(); UI.renderDemo();
  // 누락 대비: 상태에는 있는데 패널에 없는 장애는 상세를 받아 오고, 사라진 장애는 패널에서 뺀다
  let missing = st.faults.some(f => !K.faults.has(f.code));
  let stale = false;
  for (const [code] of K.faults) if (!knownFaults.has(code)) { K.faults.delete(code); stale = true; }
  if (stale) UI.renderFaults();
  if (missing) loadFaults();
}
let faultsLoading = false;
async function loadFaults(){
  if (faultsLoading) return; faultsLoading = true;
  try {
    const r = await K.api.get("/api/faults?status=active&detail=1&size=100");
    K.faults = new Map(r.items.map(f => [f.code, f]));
    const demoF = r.items.find(f => f.source === "demo"); if (demoF) K.demoFaultCode = demoF.code;
    UI.renderFaults();
  } catch(e) {} finally { faultsLoading = false; }
}
async function syncAll(){
  try { onState(await K.api.get("/api/state")); } catch(e) {}
  await loadFaults();
}
async function loadLogs(){
  try { const r = await K.api.get("/api/events?limit=300"); UI.loadLogs(r.items); } catch(e) {}
}

/* ---------------- 열차 선택 ---------------- */
let detailTimer = null;
async function fetchDetail(){
  if (!K.selTrain) return;
  const no = K.selTrain;
  try { const d = await K.api.get("/api/trains/" + encodeURIComponent(no)); if (K.selTrain === no) { K.detail = d; UI.renderDetail(); } } catch(e) {}
}
K.selectTrain = function(no, focus){
  K.selTrain = no; K.detail = null;
  if (focus && K.map.zoomW() > 400) { const p = K.map.pos(no); if (p) K.map.focusOn(p.x, p.y, 330); }
  UI.renderDetail(); if (K.state) UI.renderList();
  clearInterval(detailTimer); fetchDetail(); detailTimer = setInterval(() => { if (!document.hidden) fetchDetail(); }, 2000);
};
$("btnDesel").onclick = () => { K.selTrain = null; K.detail = null; clearInterval(detailTimer); UI.renderDetail(); if (K.state) UI.renderList(); };
$("tlist").addEventListener("pointerdown", e => { const r = e.target.closest("[data-tid]"); if (r) K.selectTrain(r.dataset.tid, true); });

/* ---------------- 조작 버튼 ---------------- */
document.querySelectorAll("[data-fault]").forEach(b => b.onclick = () => K.api.act(b, async () => {
  const lid = $("lineSel").value;
  const f = await K.api.post("/api/faults", { type: b.dataset.fault, line_id: lid === "rand" ? null : lid });
  if (f) { K.selFault = f.code; if (!(K.state && K.state.demo)) $("secFault").scrollIntoView({ behavior:"smooth", block:"nearest" }); }
}));
$("btnPlay").onclick = () => K.api.act($("btnPlay"), () => K.api.post(K.state && K.state.sim.paused ? "/api/sim/resume" : "/api/sim/pause"));
document.querySelectorAll(".spd").forEach(b => b.onclick = () => K.api.act(b, () => K.api.post("/api/sim/speed", { mul: +b.dataset.spd })));
$("btnReset").onclick = () => {
  if (!confirm("시뮬레이션을 초기화할까요? 모든 열차가 초기 위치로 돌아가고 진행 중인 장애가 사라집니다. (이벤트 로그와 해결된 장애 이력은 보존됩니다)")) return;
  K.api.act($("btnReset"), async () => { await K.api.post("/api/sim/reset"); UI.hideDemo(); K.map.fit(); });
};
const startDemo = btn => K.api.act(btn, async () => { await K.api.post("/api/demo/start"); UI.demo.done = false; UI.demo.lastElapsed = null; refreshNow(); });
$("btnDemo").onclick = () => startDemo($("btnDemo"));
$("btnReplay").onclick = () => startDemo($("btnReplay"));
$("btnDemoStop").onclick = () => {
  if (UI.demo.done || !(K.state && K.state.demo)) { UI.hideDemo(); return; }
  if (!K.can("operator")) { UI.hideDemo(); return; }  // 조회자는 자신의 화면에서만 닫는다
  K.api.act($("btnDemoStop"), () => K.api.post("/api/demo/stop"));
};
$("faultPanel").addEventListener("click", e => {
  const c = e.target.closest("[data-fid]"); if (c) { K.selFault = c.dataset.fid; UI.renderFaults(); return; }
  const code = K.selFault; if (!code) return;
  const a = e.target.closest("[data-act]");
  if (a && !a.disabled) { K.api.act(a, () => K.api.post("/api/faults/" + encodeURIComponent(code) + "/actions/" + a.dataset.act + "/complete")).then(r => { if (r) UI.flashAction(code, +a.dataset.act); }); return; }
  const rb = e.target.closest("#btnRecover"); if (rb && !rb.disabled) { K.api.act(rb, () => K.api.post("/api/faults/" + encodeURIComponent(code) + "/recover")); return; }
  const an = e.target.closest("#btnAnalyze"); if (an && !an.disabled) { K.api.act(an, () => K.api.post("/api/faults/" + encodeURIComponent(code) + "/analyze")); }
});
document.querySelectorAll(".lf").forEach(b => b.onclick = () => { document.querySelectorAll(".lf").forEach(x => x.classList.toggle("on", x === b)); $("log").dataset.filter = b.dataset.f; });
$("btnClearLog").onclick = () => UI.clearLogs();

function setMute(m){ K.muted = m; store.set("ktx-muted", m ? "1" : "0"); $("btnMute").textContent = m ? "🔕 경보음 꺼짐" : "🔔 경보음 켜짐"; }
$("btnMute").onclick = () => { setMute(!K.muted); if (!K.muted) UI.beep(); };
setMute(K.muted);
function setTheme(th){ document.documentElement.dataset.theme = th; $("btnTheme").textContent = th === "dark" ? "☀ 화이트 모드" : "🌙 다크 모드"; store.set("ktx-theme", th); }
$("btnTheme").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
setTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
K.applyPerms(document);

/* ---------------- 렌더 루프 ---------------- */
let last = performance.now(), accSample = 0;
function frame(now){
  const rdt = Math.min(.1, (now - last) / 1000); last = now;
  K.map.frame(now, K.selTrain);
  UI.kpiFrame(rdt);
  if (K.state && !K.state.sim.paused) { accSample += rdt; if (accSample >= 1) { accSample = 0; UI.kpiSample(); } }
  requestAnimationFrame(frame);
}

/* ---------------- 시작 ---------------- */
async function init(){
  try { K.net = await K.api.get("/api/network"); }
  catch(e) { K.toast("지도 데이터를 불러오지 못했습니다: " + e.message); return; }
  K.map.build(K.net);
  await syncAll();
  await loadLogs();
  UI.renderFaults();
  K.api.poll({
    status(ok, reconnected){ UI.setConn(ok); if (ok && reconnected) loadFaults(); },
    since: () => UI.maxLogId,
    data(res){ onState(res.state); res.logs.forEach(UI.addLog); },
  }, POLL_MS);
  if (document.body.dataset.pwNotice) K.toast("기본 비밀번호로 로그인했습니다. 오른쪽 위 '비밀번호 변경'에서 바꾸세요.", "info");
  requestAnimationFrame(frame);
}
init();
})();
