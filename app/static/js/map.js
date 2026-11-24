/* SVG 지도 · 열차 렌더링 (원본 buildMap / placeTrain 이식) */
(function(){
"use strict";
const K = window.KTX;
const { $, clamp, store } = K.util;
const NS = "http://www.w3.org/2000/svg";
function S(tag, attrs, parent){ const e = document.createElementNS(NS, tag); if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
K.util.S = S;

const PX = lon => 20 + (lon - 125.9) * 153.9;
const PY = lat => 15 + (38.7 - lat) * 190;
const COAST=[[37.75,126.12],[37.95,126.65],[38.12,127.1],[38.3,127.55],[38.3,128.05],[38.62,128.36],[38.2,128.6],[37.78,128.95],[37.45,129.18],[37.05,129.42],[36.6,129.42],[36.08,129.57],[35.85,129.45],[35.5,129.45],[35.3,129.3],[35.12,129.12],[35.05,128.9],[34.95,128.6],[34.85,128.4],[34.9,128.1],[34.7,127.8],[34.6,127.5],[34.5,127.2],[34.6,126.9],[34.35,126.6],[34.3,126.4],[34.6,126.3],[34.95,126.35],[35.3,126.45],[35.6,126.5],[35.9,126.6],[36.05,126.62],[36.35,126.48],[36.6,126.3],[36.9,126.35],[36.95,126.75],[37.15,126.7],[37.4,126.55],[37.55,126.6],[37.7,126.45]];
const STCOL = {"정상운행":"ok","주의운행":"warn","서행":"warn","정차":"bad","지연":"bad"};
K.util.STCOL = STCOL;
let STATE_MS = 1000;  // polling 간격에 맞춰 보간한다
K.setStateInterval = ms => { STATE_MS = Math.max(200, ms); };

const M = K.map = { P:{}, segs:{}, els:{}, net:null };
let svg, gSeg, gTrain, ring, ringLbl, tip, bound = false;
const VB0 = { x:0, y:0, w:610, h:880 };
let vb = { ...VB0 };
try {
  const s = JSON.parse(store.get("ktx-vb") || "null");
  if (s && [s.x,s.y,s.w,s.h].every(Number.isFinite) && s.w >= 100 && s.w <= VB0.w * 1.3) vb = s;
} catch(e) {}
let saveTimer = null;
function applyVB(){
  svg.setAttribute("viewBox", vb.x + " " + vb.y + " " + vb.w + " " + vb.h);
  clearTimeout(saveTimer); saveTimer = setTimeout(() => store.set("ktx-vb", JSON.stringify(vb)), 300);
}
function svgPt(cx, cy){ const r = svg.getBoundingClientRect(); const s = Math.max(vb.w/r.width, vb.h/r.height); const ox = (r.width*s - vb.w)/2, oy = (r.height*s - vb.h)/2; return { x: vb.x - ox + (cx - r.left)*s, y: vb.y - oy + (cy - r.top)*s }; }
function zoomAt(f, cx, cy){ const nw = clamp(vb.w*f, 110, VB0.w*1.3); const k = nw/vb.w; vb.x = cx-(cx-vb.x)*k; vb.y = cy-(cy-vb.y)*k; vb.w = nw; vb.h = vb.h*k; applyVB(); }
M.focusOn = function(x, y, w){ vb.w = w; vb.h = w*VB0.h/VB0.w; vb.x = x - vb.w/2; vb.y = y - vb.h/2; applyVB(); };
M.fit = function(){ vb = { ...VB0 }; applyVB(); };
M.zoomW = () => vb.w;

let drag = null, dragMoved = false, hoverNo = null;
function bindEvents(){
  if (bound) return; bound = true;
  tip = $("tip");
  svg.addEventListener("wheel", e => { e.preventDefault(); const p = svgPt(e.clientX, e.clientY); zoomAt(e.deltaY > 0 ? 1.15 : 1/1.15, p.x, p.y); }, { passive:false });
  svg.addEventListener("pointerdown", e => { dragMoved = false; drag = { x:e.clientX, y:e.clientY, vx:vb.x, vy:vb.y }; });
  window.addEventListener("pointermove", e => {
    if (drag) { const dx = e.clientX-drag.x, dy = e.clientY-drag.y; if (Math.abs(dx)+Math.abs(dy) > 4) { dragMoved = true; svg.classList.add("drag"); }
      if (dragMoved) { const r = svg.getBoundingClientRect(); const s = Math.max(vb.w/r.width, vb.h/r.height); vb.x = drag.vx - dx*s; vb.y = drag.vy - dy*s; applyVB(); } }
    const el = hoverNo && M.els[hoverNo];
    if (el && el.data) { const r = $("mapPanel").getBoundingClientRect(); tip.style.display = "block"; tip.style.left = (e.clientX - r.left + 14) + "px"; tip.style.top = (e.clientY - r.top + 12) + "px";
      const t = el.data; const ln = M.net.lineById[t.line];
      tip.innerHTML = "<b>" + t.no + "</b> · " + (ln ? ln.name : "") + "<br>속도 <b class='num'>" + Math.round(t.speed) + "</b> km/h · " + t.status; }
  });
  window.addEventListener("pointerup", () => { drag = null; svg.classList.remove("drag"); setTimeout(() => dragMoved = false, 0); });
  $("zIn").onclick = () => zoomAt(1/1.35, vb.x + vb.w/2, vb.y + vb.h/2);
  $("zOut").onclick = () => zoomAt(1.35, vb.x + vb.w/2, vb.y + vb.h/2);
  $("zFit").onclick = () => M.fit();
}

M.build = function(net){
  svg = $("map"); M.net = net;
  net.lineById = {}; net.lines.forEach(l => net.lineById[l.id] = l);
  net.segByKey = {}; net.segments.forEach(s => net.segByKey[s.key] = s);
  net.stByName = {}; net.stations.forEach(s => { net.stByName[s.name] = s; M.P[s.name] = { x:s.x, y:s.y }; });
  svg.innerHTML = ""; M.els = {}; M.segs = {};
  const defs = S("defs", null, svg);
  const f = S("filter", { id:"glow", x:"-50%", y:"-50%", width:"200%", height:"200%" }, defs);
  S("feGaussianBlur", { stdDeviation:"3", result:"b" }, f);
  const m = S("feMerge", null, f); S("feMergeNode", { in:"b" }, m); S("feMergeNode", { in:"SourceGraphic" }, m);
  [["ok","var(--ok)"],["warn","var(--warn)"],["bad","var(--bad)"]].forEach(([n,c]) => {
    const g = S("linearGradient", { id:"tail-"+n, x1:"0", x2:"1", y1:"0", y2:"0" }, defs);
    S("stop", { offset:"0", style:"stop-color:"+c+";stop-opacity:0" }, g); S("stop", { offset:"1", style:"stop-color:"+c+";stop-opacity:.85" }, g);
  });
  const gg = S("g", { opacity:".5" }, svg);
  for (let la = 35; la <= 38; la++) { S("line", { x1:0, x2:610, y1:PY(la), y2:PY(la), stroke:"var(--grid)", "stroke-width":1.5 }, gg); S("text", { x:4, y:PY(la)-3, class:"stl", style:"font-size:9px;opacity:.6" }, gg).textContent = la + "°N"; }
  for (let lo = 126; lo <= 129; lo++) { S("line", { y1:0, y2:880, x1:PX(lo), x2:PX(lo), stroke:"var(--grid)", "stroke-width":1.5 }, gg); S("text", { y:874, x:PX(lo)+3, class:"stl", style:"font-size:9px;opacity:.6" }, gg).textContent = lo + "°E"; }
  S("text", { x:40, y:470, class:"sea" }, svg).textContent = "서 해";
  S("text", { x:545, y:290, class:"sea" }, svg).textContent = "동 해";
  S("text", { x:300, y:860, class:"sea" }, svg).textContent = "남 해";
  S("polygon", { points: COAST.map(c => PX(c[1]).toFixed(1)+","+PY(c[0]).toFixed(1)).join(" "), fill:"var(--land)", stroke:"var(--coast)", "stroke-width":1.4, "stroke-linejoin":"round", filter:"url(#glow)" }, svg);
  const P = M.P;
  const gBase = S("g", null, svg);
  net.segments.forEach(s => S("line", { x1:P[s.a].x, y1:P[s.a].y, x2:P[s.b].x, y2:P[s.b].y, stroke:"var(--track)", "stroke-width":8, "stroke-linecap":"round" }, gBase));
  const gLine = S("g", { filter:"url(#glow)" }, svg), gFlow = S("g", null, svg);
  net.lines.forEach((L, i) => {
    const d = "M" + L.stations.map(n => P[n].x.toFixed(1) + " " + P[n].y.toFixed(1)).join(" L");
    const cv = "--l-" + L.id;
    S("path", { d, fill:"none", style:"stroke:var("+cv+")", "stroke-width":3.4, "stroke-linejoin":"round", "stroke-linecap":"round", opacity:".55" }, gLine);
    S("path", { d, class:"flow", style:"stroke:var("+cv+");animation-duration:"+(1.4 + i*.25)+"s" }, gFlow);
  });
  gSeg = S("g", null, svg);
  net.segments.forEach(s => {
    const a = P[s.a], b = P[s.b]; const o = { cls:"ok" };
    o.halo = S("line", { x1:a.x, y1:a.y, x2:b.x, y2:b.y, class:"seg-halo" }, gSeg);
    o.el = S("line", { x1:a.x, y1:a.y, x2:b.x, y2:b.y, class:"seg-st ok" }, gSeg);
    const mx = (a.x+b.x)/2, my = (a.y+b.y)/2;
    o.icon = S("g", { transform:"translate("+mx+","+(my-14)+")", style:"display:none" }, gSeg);
    S("path", { d:"M0 -9 L9 7 L-9 7 Z", fill:"var(--bad)", stroke:"#fff", "stroke-width":1.2 }, o.icon);
    S("text", { x:0, y:5, "text-anchor":"middle", fill:"#fff", style:"font-size:10px;font-weight:900" }, o.icon).textContent = "!";
    M.segs[s.key] = o;
  });
  const gSt = S("g", null, svg);
  net.stations.forEach(st => {
    const p = P[st.name];
    if (st.is_major) { const pr = S("circle", { cx:p.x, cy:p.y, r:6, fill:"none", stroke:"var(--accent)", "stroke-width":1.2 }, gSt);
      const dur = (2.4 + Math.random()).toFixed(2) + "s";
      S("animate", { attributeName:"r", values:"5;12;5", dur, repeatCount:"indefinite" }, pr);
      S("animate", { attributeName:"stroke-opacity", values:".8;0;.8", dur, repeatCount:"indefinite" }, pr); }
    S("circle", { cx:p.x, cy:p.y, r:st.is_major ? 5 : 3.4, fill:"var(--bg)", stroke:st.is_major ? "var(--accent)" : "var(--maptext)", "stroke-width":st.is_major ? 2.2 : 1.5 }, gSt);
    S("text", { x:p.x + st.label_dx, y:p.y + st.label_dy + 3, "text-anchor":st.label_anchor, class:"stl" + (st.is_major ? " major" : "") }, gSt).textContent = st.name;
  });
  gTrain = S("g", null, svg);
  const gTop = S("g", { style:"pointer-events:none" }, svg);
  ring = S("circle", { r:12, fill:"none", stroke:"var(--accent)", "stroke-width":2, style:"display:none" }, gTop);
  S("animate", { attributeName:"r", values:"9;20;9", dur:"1.4s", repeatCount:"indefinite" }, ring);
  S("animate", { attributeName:"stroke-opacity", values:"1;.15;1", dur:"1.4s", repeatCount:"indefinite" }, ring);
  ringLbl = S("text", { class:"tlabel", "text-anchor":"middle", style:"display:none" }, gTop);
  applyVB(); bindEvents();
};

function ensureTrain(no){
  let e = M.els[no]; if (e) return e;
  const g = S("g", { class:"train" }, gTrain);
  S("circle", { r:13, fill:"transparent" }, g);
  e = { g, colorCls:"ok", cx:0, cy:0, fx:0, fy:0, tx:0, ty:0, t0:0, segId:null, ang:0, data:null };
  e.tail = S("rect", { x:-26, y:-2.6, width:22, height:5.2, rx:2.6, fill:"url(#tail-ok)" }, g);
  e.body = S("rect", { x:-6, y:-3.6, width:14, height:7.2, rx:3.4, fill:"var(--ok)", stroke:"#fff", "stroke-width":1.1 }, g);
  S("circle", { cx:5, cy:0, r:1.3, fill:"#fff" }, g);
  g.addEventListener("click", ev => { if (dragMoved) return; ev.stopPropagation(); K.selectTrain && K.selectTrain(no, false); });
  g.addEventListener("pointerenter", () => { hoverNo = no; });
  g.addEventListener("pointerleave", () => { if (hoverNo === no) hoverNo = null; tip.style.display = "none"; });
  M.els[no] = e; return e;
}

/* polling 으로 들어오는 위치를 목표로 잡고, rAF 에서 선형 보간한다. 구간이 바뀌면 바로 이동. */
M.setTrains = function(trains, now){
  const seen = new Set();
  trains.forEach(t => {
    seen.add(t.no);
    const e = ensureTrain(t.no);
    const segId = t.line + ":" + t.st_idx + ":" + t.dir;
    if (e.segId !== segId || !e.data) { e.fx = t.x; e.fy = t.y; e.cx = t.x; e.cy = t.y; }
    else { e.fx = e.cx; e.fy = e.cy; }
    e.tx = t.x; e.ty = t.y; e.t0 = now; e.segId = segId; e.ang = t.angle; e.data = t;
    const c = STCOL[t.status] || "ok";
    if (c !== e.colorCls) { e.colorCls = c; e.body.setAttribute("fill", "var(--"+c+")"); e.tail.setAttribute("fill", "url(#tail-"+c+")"); }
    const w = t.speed > 5 ? (8 + t.speed/300*16) : 0;
    e.tail.setAttribute("width", w.toFixed(1)); e.tail.setAttribute("x", t.speed > 5 ? (-4 - w).toFixed(1) : "-4");
  });
  for (const no in M.els) if (!seen.has(no)) { M.els[no].g.remove(); delete M.els[no]; }
};
M.pos = no => { const e = M.els[no]; return e ? { x:e.cx, y:e.cy } : null; };

M.frame = function(now, selNo){
  for (const no in M.els) {
    const e = M.els[no]; if (!e.data) continue;
    const a = clamp((now - e.t0) / STATE_MS, 0, 1);
    e.cx = e.fx + (e.tx - e.fx) * a; e.cy = e.fy + (e.ty - e.fy) * a;
    e.g.setAttribute("transform", "translate(" + e.cx.toFixed(2) + "," + e.cy.toFixed(2) + ") rotate(" + e.ang.toFixed(1) + ")");
  }
  const sel = selNo && M.els[selNo];
  if (sel) { ring.style.display = ""; ring.setAttribute("cx", sel.cx); ring.setAttribute("cy", sel.cy); ringLbl.style.display = ""; ringLbl.setAttribute("x", sel.cx); ringLbl.setAttribute("y", sel.cy - 16); ringLbl.textContent = selNo; }
  else { ring.style.display = "none"; ringLbl.style.display = "none"; }
};

M.setSegments = function(levels){
  for (const k in M.segs) {
    const s = M.segs[k]; const c = levels[k] || "ok";
    if (c !== s.cls) { s.cls = c; s.el.setAttribute("class", "seg-st " + c); s.halo.setAttribute("class", "seg-halo" + (c === "danger" ? " on" : "")); s.icon.style.display = c === "danger" ? "" : "none"; }
  }
};
})();
