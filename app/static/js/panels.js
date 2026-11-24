/* KPI · 열차 목록/상세 · 장애 패널 · 헤더 · 로그 · 시연 바 · 경보음 */
(function(){
"use strict";
const K = window.KTX;
const { $, clamp, fmtT, esc, store, STCOL } = K.util;
const UI = K.ui = {};

/* ---------------- 경보음 ---------------- */
let audioCtx = null;
K.muted = store.get("ktx-muted") === "1";
UI.beep = function(){
  if (K.muted) return;
  try { audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)(); if (audioCtx.state === "suspended") audioCtx.resume();
    const t0 = audioCtx.currentTime; [0,.22,.44].forEach((o,i) => { const os = audioCtx.createOscillator(), g = audioCtx.createGain(); os.type = "square"; os.frequency.value = i%2 ? 660 : 880;
      g.gain.setValueAtTime(0, t0+o); g.gain.linearRampToValueAtTime(.06, t0+o+.02); g.gain.linearRampToValueAtTime(0, t0+o+.18); os.connect(g).connect(audioCtx.destination); os.start(t0+o); os.stop(t0+o+.2); });
  } catch(e) {}
};

/* ---------------- KPI ---------------- */
const kpiCur = { total:0, ontime:0, safety:0, delay:0 };
const kpiHist = { total:[], ontime:[], safety:[], delay:[] };
UI.kpiTargets = k => k ? { total:k.total, ontime:k.on_time, safety:k.safety, delay:k.delayed } : null;
function kcol(name, v){
  if (name === "ontime") return v >= 95 ? "var(--ok)" : v >= 85 ? "var(--warn)" : "var(--bad)";
  if (name === "safety") return v >= 90 ? "var(--ok)" : v >= 70 ? "var(--warn)" : "var(--bad)";
  if (name === "delay") return v === 0 ? "var(--ok)" : v <= 2 ? "var(--warn)" : "var(--bad)";
  return "var(--ok)";
}
function drawSpark(id, arr, name){
  const el = $(id); if (arr.length < 2) { el.innerHTML = ""; return; }
  let lo, hi; if (name === "ontime" || name === "safety") { lo = Math.min(60, ...arr); hi = 100; } else { lo = 0; hi = Math.max(4, ...arr) + 1; }
  const pts = arr.map((v,i) => (i/59*120).toFixed(1) + "," + (40 - (v-lo)/(hi-lo||1)*36).toFixed(1));
  const col = kcol(name, arr[arr.length-1]);
  el.innerHTML = "<polyline points='0,42 " + pts.join(" ") + " " + (((arr.length-1)/59)*120).toFixed(1) + ",42' fill='" + col + "' fill-opacity='.10' stroke='none'/><polyline points='" + pts.join(" ") + "' fill='none' stroke='" + col + "' stroke-width='1.8' stroke-linejoin='round'/>";
}
UI.kpiFrame = function(rdt){
  const st = K.state; if (!st) return;
  const tg = UI.kpiTargets(st.kpi);
  for (const k in tg) { kpiCur[k] += (tg[k] - kpiCur[k]) * Math.min(1, rdt*5); if (Math.abs(tg[k] - kpiCur[k]) < .05) kpiCur[k] = tg[k]; }
  $("kv-total").textContent = Math.round(kpiCur.total); $("kv-ontime").textContent = kpiCur.ontime.toFixed(1);
  $("kv-safety").textContent = Math.round(kpiCur.safety); $("kv-delay").textContent = Math.round(kpiCur.delay);
  for (const k of ["total","ontime","safety","delay"]) $("kpi-"+k).style.setProperty("--kc", kcol(k, tg[k]));
};
UI.kpiSample = function(){
  const st = K.state; if (!st) return;
  const tg = UI.kpiTargets(st.kpi);
  for (const k in tg) { kpiHist[k].push(tg[k]); if (kpiHist[k].length > 60) kpiHist[k].shift(); }
  drawSpark("sp-total", kpiHist.total, "total"); drawSpark("sp-ontime", kpiHist.ontime, "ontime");
  drawSpark("sp-safety", kpiHist.safety, "safety"); drawSpark("sp-delay", kpiHist.delay, "delay");
};
UI.kpiSubs = function(){
  const k = K.state.kpi;
  $("ks-total").textContent = "주행 " + k.moving + " · 정차 " + (k.total - k.moving) + " · " + K.net.lines.length + "개 노선";
  $("ks-ontime").textContent = "정시 " + (k.total - k.delayed) + " / " + k.total + "편";
  $("ks-safety").textContent = k.active_faults ? "활성 장애 " + k.active_faults + "건 반영" : "전 구간 정상 · 점검 양호";
  $("ks-delay").textContent = k.delayed ? "평균 지연 " + k.avg_delay.toFixed(1) + "분" : "3분 이상 지연 기준";
};

/* ---------------- 헤더 ---------------- */
UI.renderHeader = function(){
  const st = K.state; const act = st.faults;
  const bad = act.filter(f => f.phase !== "recovering" && f.severity !== "주의");
  const ss = $("sysStat"); let cls = "", txt = "전 구간 정상 운영";
  if (bad.length) { cls = "bad"; txt = "비상 상황 · 활성 장애 " + act.length + "건"; }
  else if (act.length) { cls = "warn"; txt = "주의 운영 · 활성 장애 " + act.length + "건"; }
  else if (st.trains.some(t => t.delay >= 3)) { cls = "warn"; txt = "정상 운영 · 지연 회복 중"; }
  ss.className = "sysstat " + cls; $("sysText").textContent = txt;
  const live = act.filter(f => f.phase !== "recovering");
  const al = $("alert");
  if (live.length) { const f = live[live.length-1]; al.classList.add("show");
    $("alertText").textContent = f.type_name + (f.sub ? "(" + f.sub + ")" : "") + " · " + f.line_name + " " + f.where + " · 심각도 " + f.severity + (live.length > 1 ? " · 외 " + (live.length-1) + "건" : ""); }
  else al.classList.remove("show");
  document.body.classList.toggle("alarm", live.some(f => f.severity !== "주의"));
  const s = st.sim;
  $("runState").textContent = (s.paused ? "일시정지" : "실행 중") + " · " + s.mul + "배속"; $("runState").classList.toggle("paused", s.paused);
  $("clock").textContent = s.clock;
  const bp = $("btnPlay"); bp.textContent = s.paused ? "▶ 재생" : "⏸ 일시정지"; bp.classList.toggle("on", s.paused);
  document.querySelectorAll(".spd").forEach(x => x.classList.toggle("on", +x.dataset.spd === s.mul));
};
UI.setConn = function(ok){
  const c = $("connStat"); c.className = "sysstat " + (ok ? "" : "warn"); $("connText").textContent = ok ? "실시간 연결" : "연결 끊김";
};

/* ---------------- 열차 목록 · 상세 ---------------- */
UI.renderList = function(){
  const st = K.state;
  $("tlist").innerHTML = st.trains.map(t => "<div class='trow" + (t.no === K.selTrain ? " sel" : "") + "' data-tid='" + esc(t.no) + "'><span class='dot' style='background:var(--" + STCOL[t.status] + ")'></span><span><span class='tn'>" + esc(t.no) + "</span> <span class='tl'>" + esc(K.net.lineById[t.line].name) + " " + (t.dir > 0 ? "하행" : "상행") + "</span></span><span class='ts'>" + Math.round(t.speed) + "</span></div>").join("");
};
const INSP_LBL = { ok:["정상","b-ok"], warn:["주의","b-warn"], bad:["이상","b-bad"] };
function badgeFor(s){ return "<span class='badge b-" + STCOL[s] + "'>" + s + "</span>"; }
UI.renderDetail = function(){
  const box = $("trainDetail");
  const t = K.state && K.state.trains.find(x => x.no === K.selTrain);
  if (!t) { box.innerHTML = "<div class='card empty'>지도 또는 열차 목록에서 열차를 선택하세요.</div>"; return; }
  const net = K.net, L = net.lineById[t.line], st = L.stations;
  const from = t.dir > 0 ? st[0] : st[st.length-1], to = t.dir > 0 ? st[st.length-1] : st[0];
  const seg = net.segByKey[t.seg]; const next = st[t.st_idx + t.dir];
  const pos = t.dwell > 0 ? st[t.st_idx] + "역 정차 중" : st[t.st_idx] + " → " + next;
  const remain = t.dwell > 0 ? "-" : ((1 - t.p) * seg.length_km).toFixed(1) + " km";
  const col = "var(--" + STCOL[t.status] + ")";
  const d = K.detail && K.detail.no === t.no ? K.detail : null;
  const ins = {}; (d ? d.inspections : []).forEach(x => ins[x.item] = x.status);
  const items = ["제동장치","출입문","대차·차륜","전력·팬터그래프","신호수신(ATP)","객실 공조"];
  const histArr = d ? d.speed_history : [];
  const hist = histArr.length > 1 ? histArr.map((v,i) => (i/59*300).toFixed(1) + "," + (56 - v/320*52).toFixed(1)).join(" ") : "";
  box.innerHTML = "<div class='card'>" +
   "<div class='thead'><span class='tname'>" + esc(t.no) + "</span>" + badgeFor(t.status) + "</div>" +
   "<div class='speed'><div class='sv num' style='color:" + col + "'>" + Math.round(t.speed) + "<small>km/h</small></div><div style='text-align:right;font-size:11.5px;color:var(--muted)'>구간 최고 " + seg.max_speed + " km/h</div></div>" +
   "<div class='gauge'><i style='width:" + clamp(t.speed/300*100, 0, 100) + "%;background:" + col + ";box-shadow:0 0 10px " + col + "'></i></div>" +
   "<dl class='kv'><dt>노선</dt><dd>" + esc(L.name) + " · " + (t.dir > 0 ? "하행" : "상행") + "</dd><dt>출발역</dt><dd>" + esc(from) + "</dd><dt>도착역</dt><dd>" + esc(to) + "</dd>" +
   "<dt>현재 위치</dt><dd>" + esc(pos) + "</dd><dt>다음 역까지</dt><dd class='num'>" + remain + "</dd>" +
   "<dt>운행 상태</dt><dd style='color:" + col + "'>" + t.status + "</dd><dt>지연 시간</dt><dd class='num'>" + (t.delay < 0.05 ? "없음" : t.delay.toFixed(1) + " 분") + "</dd><dt>승객 수(가상)</dt><dd class='num'>" + t.pax + " 명</dd></dl>" +
   "<div class='mini-t'>속도 추이 (최근 60초)</div><svg viewBox='0 0 300 58' preserveAspectRatio='none' style='width:100%;height:58px;display:block;border-radius:6px;background:var(--chip)'><line x1='0' x2='300' y1='" + (56-300/320*52) + "' y2='" + (56-300/320*52) + "' stroke='var(--line2)' stroke-dasharray='3 4'/>" + (hist ? "<polyline points='" + hist + "' fill='none' stroke='" + col + "' stroke-width='2'/>" : "") + "</svg>" +
   "<div class='mini-t'>안전점검 현황 <span style='font-weight:500'>· 마지막 점검 " + (d ? d.last_check_clock : "-") + "</span></div>" +
   "<div class='insp'>" + items.map(n => { const v = ins[n] || "ok"; return "<div><span>" + n + "</span><span class='badge " + INSP_LBL[v][1] + "'>" + INSP_LBL[v][0] + "</span></div>"; }).join("") + "</div></div>";
};

/* ---------------- 장애 패널 ---------------- */
const SEV_CLS = s => s === "주의" ? "b-warn" : "b-bad";
const PHASE_LBL = { detected:["AI 분석 대기","b-ai"], analyzing:["AI 분석 중","b-ai"], analyzed:["대응 조치 중","b-act"], recovering:["복구 진행 중","b-warn"] };
const revealed = new Set();
let flashSeq = null;
UI.flashAction = function(code, seq){ flashSeq = { code, seq }; UI.renderFaults(); };
UI.activeFaults = function(){ return [...K.faults.values()].filter(f => f.phase !== "resolved").sort((a,b) => a.id - b.id); };
UI.renderFaults = function(){
  const box = $("faultPanel"); const act = UI.activeFaults();
  if (!act.length) { box.innerHTML = "<div class='card empty'><span class='badge b-ok'>● 전 구간 정상</span><br><br>현재 활성 장애가 없습니다.<br>좌측 '비상 상황 발생' 버튼으로 장애를 만들어 보세요.</div>"; return; }
  if (!act.some(f => f.code === K.selFault)) K.selFault = act[act.length-1].code;
  const f = act.find(x => x.code === K.selFault);
  let h = "<div class='fchips'>" + act.map(x => "<span class='fchip" + (x.code === K.selFault ? " sel" : "") + "' data-fid='" + esc(x.code) + "'><span class='dot' style='background:" + (x.phase === "recovering" || x.severity === "주의" ? "var(--warn)" : "var(--bad)") + "'></span>" + esc(x.code) + " " + esc(x.type_name) + "</span>").join("") + "</div>";
  const tn = f.type_name + (f.sub ? " (" + f.sub + ")" : "");
  const seqNo = String(1000 + parseInt(f.code.split("-")[1], 10)).slice(1);
  h += "<div class='card'><div class='thead'><b style='font-size:14px'>" + f.icon + " " + esc(tn) + "</b><span class='badge " + PHASE_LBL[f.phase][1] + "'>" + PHASE_LBL[f.phase][0] + "</span></div>" +
    "<dl class='kv'><dt>장애번호</dt><dd class='num'>" + esc(f.code) + " · " + f.type_code + "-" + seqNo + "</dd><dt>발생 구간</dt><dd>" + esc(f.line_name + " " + f.where) + "</dd><dt>심각도</dt><dd><span class='badge " + SEV_CLS(f.severity) + "'>" + f.severity + "</span></dd><dt>발생 시각</dt><dd class='num'>" + f.created_clock + "</dd>" +
    (f.created_by ? "<dt>발생 등록</dt><dd>" + esc(f.created_by) + (f.source === "demo" ? " (시연)" : "") + "</dd>" : "") + "</dl>";
  if (f.phase === "detected") {
    h += "<div class='aibox'><h4>AI 원인 분석</h4><div class='summary' style='color:var(--muted)'>장애 신호가 접수되었습니다. AI 분석 대기 중…</div><button class='btn' style='width:100%;margin-top:8px' id='btnAnalyze' data-perm='operator'>▶ AI 분석 시작</button></div>";
  } else if (f.phase === "analyzing") {
    const pr = Math.round((f.progress || 0) * 100);
    h += "<div class='aibox'><h4><span>AI 원인 분석 중…</span><span class='num' id='anaPct'>" + pr + "%</span></h4><div class='prog'><i id='anaBar' style='width:" + pr + "%'></i></div><div class='summary' style='color:var(--muted)'>운행 데이터 · 센서 로그 · 신호 이력 · 기상 정보를 상관 분석하고 있습니다.</div></div>";
  } else {
    const rv = !revealed.has(f.code); revealed.add(f.code);
    const R = d => rv ? " class='reveal' style='animation-delay:" + d + "s'" : "";
    h += "<div class='aibox'><h4><span>AI 원인 분석 결과 (가상)</span><span>신뢰도 " + f.confidence + "%</span></h4>" +
      "<div" + R(0) + "><div class='summary'>" + esc(f.summary) + "</div></div>" +
      "<div" + R(.25) + "><div class='mini-t'>추정 원인</div>" + f.causes.map(c => "<div class='cause'><div class='ct'><span>" + esc(c.label) + "</span><b class='num'>" + c.probability + "%</b></div><div class='cbar'><i style='width:" + c.probability + "%'></i></div></div>").join("") + "</div>" +
      "<div" + R(.5) + "><div class='mini-t'>영향 범위</div><div style='display:flex;gap:6px;flex-wrap:wrap'><span class='badge b-warn'>영향 열차 " + f.impact_trains + "편</span><span class='badge b-warn'>예상 지연 최대 " + f.expected_delay_min + "분</span></div></div>" +
      "<div" + R(.75) + "><div class='mini-t'>권고 대응 절차</div><ul class='chk'>" + f.actions.map(a => "<li class='" + (a.done ? "done" : "") + "'><span class='bx'>" + (a.done ? "✓" : "") + "</span>" + a.seq + ". " + esc(a.label) + (a.done && a.done_by ? " <span style='color:var(--muted);font-size:11px'>(" + esc(a.done_by) + ")</span>" : "") + "</li>").join("") +
        "<li class='" + (f.phase === "recovering" ? "done" : "") + "'><span class='bx'>" + (f.phase === "recovering" ? "✓" : "") + "</span>" + (f.actions.length + 1) + ". 정상 복구 승인 및 운행 재개</li></ul></div></div>";
    const fl = flashSeq && flashSeq.code === f.code ? flashSeq.seq : null;
    h += "<div class='mini-t'>대응 조치</div><div class='acts'>" + f.actions.map(a => "<button class='btn" + (a.done ? " done" : "") + (fl === a.seq ? " flash" : "") + "' data-act='" + a.seq + "' data-perm='operator' " + (a.done || f.phase !== "analyzed" ? "disabled" : "") + ">" + (a.done ? "✔ " : "▶ ") + esc(a.label) + "</button>").join("") + "</div>";
    const ready = f.phase === "analyzed" && f.actions.every(a => a.done);
    h += "<button class='btn recover' id='btnRecover' data-perm='operator' " + (ready ? "" : "disabled") + ">" + (f.phase === "recovering" ? "복구 진행 중… 구간 점검 및 단계적 운행 재개" : ready ? "✔ 정상 복구 실행" : "정상 복구 (모든 대응 조치 완료 후 활성화)") + "</button>";
  }
  h += "</div>"; box.innerHTML = h; flashSeq = null;
  K.applyPerms(box);
};
UI.updateAnalysis = function(){
  if (!K.state) return;
  K.state.faults.forEach(sf => {
    const f = K.faults.get(sf.code); if (!f) return;
    f.progress = sf.progress;
    if (sf.code === K.selFault && f.phase === "analyzing") {
      const bar = $("anaBar"); if (bar) { bar.style.width = sf.progress*100 + "%"; $("anaPct").textContent = Math.round(sf.progress*100) + "%"; }
    }
  });
};

/* ---------------- 로그 ---------------- */
const LOGCAT = { info:["정보","b-info"], ok:["정상","b-ok"], warn:["주의","b-warn"], danger:["위험","b-bad"], ai:["AI","b-ai"], action:["조치","b-act"], audit:["감사","b-info"] };
const MAX_LOG = 300;
UI.maxLogId = 0;
UI.clearedId = parseInt(store.get("ktx-log-cleared") || "0", 10) || 0;
function logEl(){ return $("log"); }
function makeLogRow(ev){
  const d = document.createElement("div"); d.className = "le c-" + ev.category; d.dataset.id = ev.id;
  const c = LOGCAT[ev.category] || LOGCAT.info;
  d.innerHTML = "<span class='t'>" + esc(ev.sim_clock) + "</span><span class='badge " + c[1] + "'>" + c[0] + "</span><span></span>";
  d.lastChild.textContent = ev.message; return d;
}
function updateCount(){ const n = logEl().children.length; $("logCount").textContent = n ? "· " + n + "건" : ""; }
UI.addLog = function(ev){
  if (ev.id <= UI.maxLogId) return;
  UI.maxLogId = ev.id;
  if (ev.id <= UI.clearedId) return;
  const el = logEl(); el.prepend(makeLogRow(ev));
  while (el.children.length > MAX_LOG) el.lastChild.remove();
  el.scrollTop = 0; updateCount();
};
UI.loadLogs = function(items){ /* items: 최신순 */
  const el = logEl(); el.innerHTML = "";
  items.forEach(ev => { if (ev.id > UI.clearedId) el.appendChild(makeLogRow(ev)); });
  if (items.length) UI.maxLogId = Math.max(UI.maxLogId, items[0].id);
  updateCount();
};
UI.clearLogs = function(){ UI.clearedId = UI.maxLogId; store.set("ktx-log-cleared", String(UI.clearedId)); logEl().innerHTML = ""; updateCount(); };

/* ---------------- 시연 바 ---------------- */
const CAP_END = "시연이 끝났습니다. '다시 보기'로 처음부터 재생하거나 '닫기'로 수동 관제를 계속할 수 있습니다.";
UI.demo = { shown:false, done:false, lastElapsed:null };
/* 서버 타임라인(7-7)과 같은 시점. polling 으로 받은 경과 시간이 이 시점을 지나면 화면 연출을 실행한다. */
const DEMO_TL = [["s1",0],["s2",8],["s3",14],["s4",22],["a0",23.5],["a1",26.5],["a2",29.5],["s5",32],["toast",36]];
function demoEffect(key, d){
  if (key === "s1") UI.spot("kpis");
  else if (key === "s2") { UI.spot("map"); const p = K.map.P["대전"]; if (p) K.map.focusOn(p.x + 40, p.y, 380); K.selectTrain("KTX 002", false); }
  else if (key === "s3" || key === "s4") { UI.spot("fault"); $("secFault").scrollIntoView({ behavior:"smooth", block:"start" }); }
  else if (key[0] === "a") { UI.spot("fault"); if (d.fault_code) UI.flashAction(d.fault_code, +key[1] + 1); }
  else if (key === "s5") { UI.spot("kpis"); K.map.fit(); $("rightPanel").scrollTo({ top:0, behavior:"smooth" }); }
  else if (key === "toast") { const t = $("toast"); t.textContent = "✔ 정상 운행 복구 완료"; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2600); }
}
UI.spot = function(name){
  document.querySelectorAll(".spot").forEach(e => e.classList.remove("spot"));
  const id = { kpis:"kpis", map:"mapPanel", fault:"secFault" }[name];
  if (id) $(id).classList.add("spot");
};
UI.renderDemo = function(){
  const d = K.state && K.state.demo; const bar = $("demoBar");
  if (d && d.active) {
    const prev = UI.demo.lastElapsed;
    if (prev === null || d.elapsed < prev) {          // 처음 보거나 다시 시작된 시연: 현재 단계 연출만
      UI.demo.done = false;
      demoEffect(["s1","s2","s3","s4","s5"][d.step - 1], d);
    } else {
      DEMO_TL.forEach(([k, tm]) => { if (prev < tm && tm <= d.elapsed) demoEffect(k, d); });
    }
    UI.demo.lastElapsed = d.elapsed;
    UI.demo.shown = true; bar.classList.add("show");
    $("btnReplay").style.display = "none"; $("btnDemoStop").textContent = "■ 시연 중지";
    const step = d.step - 1;
    [...$("steps").children].forEach((e,i) => e.className = "step" + (i < step ? " done" : i === step ? " cur" : ""));
    $("demoProg").style.width = clamp(d.elapsed / d.total * 100, 0, 100) + "%";
    $("demoCap").textContent = d.caption;
  } else if (d && d.result === "done" && UI.demo.lastElapsed !== null) {
    // 시연이 끝까지 진행됨 → '다시 보기 / 닫기' 상태로
    UI.demo.lastElapsed = null; UI.demo.done = true; UI.spot(null); UI.renderDemo();
  } else if (UI.demo.done) {
    bar.classList.add("show");
    [...$("steps").children].forEach(e => e.className = "step done");
    $("demoProg").style.width = "100%"; $("demoCap").textContent = CAP_END;
    $("btnReplay").style.display = ""; $("btnDemoStop").textContent = "닫기";
  } else if (UI.demo.shown) {
    UI.demo.shown = false; UI.demo.lastElapsed = null; bar.classList.remove("show"); UI.spot(null);
  }
};
UI.hideDemo = function(){ UI.demo.shown = false; UI.demo.done = false; UI.demo.lastElapsed = null; $("demoBar").classList.remove("show"); UI.spot(null); };
})();
