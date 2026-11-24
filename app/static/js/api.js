/* fetch 래퍼 · SSE 연결/재연결 · 공통 유틸 */
(function(){
"use strict";
const K = window.KTX = window.KTX || {};

const $ = id => document.getElementById(id);
const clamp = (v,a,b) => Math.max(a, Math.min(b, v));
const fmtT = t => { t = ((Math.floor(t)%86400)+86400)%86400; const h=Math.floor(t/3600), m=Math.floor(t%3600/60), s=t%60;
  return String(h).padStart(2,"0")+":"+String(m).padStart(2,"0")+":"+String(s).padStart(2,"0"); };
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const store = {
  get(k){ try { return localStorage.getItem(k); } catch(e) { return null; } },
  set(k,v){ try { localStorage.setItem(k, v); } catch(e) {} }
};
K.util = { $, clamp, fmtT, esc, store };

/* ---------- 토스트 (오류·안내) ---------- */
let toastTimer = null;
K.toast = function(msg, kind){
  const el = $("etoast"); if (!el) return;
  el.textContent = msg;
  el.className = "etoast show" + (kind === "info" ? " info" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = "etoast" + (kind === "info" ? " info" : ""); }, 3600);
};

/* ---------- 권한 ---------- */
const ROLE_LV = { viewer:1, operator:2, admin:3 };
K.role = document.body.dataset.role || "viewer";
K.can = need => (ROLE_LV[K.role] || 0) >= (ROLE_LV[need] || 9);
K.applyPerms = function(root){
  (root || document).querySelectorAll("[data-perm]").forEach(b => {
    if (!K.can(b.dataset.perm)) {
      b.disabled = true; b.classList.add("noperm");
      b.title = b.dataset.perm === "admin" ? "관리자 권한이 필요합니다" : "관제사 권한이 필요합니다";
    }
  });
};

/* ---------- REST ---------- */
async function req(method, url, body){
  const opt = { method, credentials:"same-origin", headers:{ "Accept":"application/json" } };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  let r;
  try { r = await fetch(url, opt); }
  catch(e) { const er = new Error("서버에 연결할 수 없습니다."); er.code = "NETWORK"; throw er; }
  let data = null; try { data = await r.json(); } catch(e) {}
  if (!r.ok) {
    if (r.status === 401) { location.href = "/login?next=" + encodeURIComponent(location.pathname); }
    const er = new Error(data && data.error ? data.error.message : "요청이 실패했습니다 (" + r.status + ")");
    er.code = data && data.error ? data.error.code : "HTTP_" + r.status; er.status = r.status; throw er;
  }
  return data;
}
K.api = {
  get: u => req("GET", u),
  post: (u, b) => req("POST", u, b || {}),
  put: (u, b) => req("PUT", u, b),
  del: (u, b) => req("DELETE", u, b),
  /* 버튼을 호출 중 비활성화하고, 실패하면 토스트로 알린다. 결과는 SSE 로 반영된다. */
  async act(btn, fn){
    if (btn) btn.disabled = true;
    try { const r = await fn(); if (K.onActed) K.onActed(); return r; }
    catch(e) { K.toast(e.message || "요청이 실패했습니다."); return null; }
    finally { if (btn) { btn.disabled = false; K.applyPerms(btn.parentNode || document); } }
  },
  /* 서버리스 환경이라 SSE 대신 polling 으로 상태를 받는다.
     h.since() 가 돌려준 로그 id 이후의 로그와 상태 스냅샷을 매번 받아 h.data(res) 로 넘긴다.
     탭이 숨겨져 있으면 요청을 멈춰 서버 부하를 줄인다. */
  poll(h, intervalMs){
    let ok = null, timer = null, busy = false;
    async function once(){
      if (busy) return; busy = true;
      try {
        const res = await req("GET", "/api/poll?since_id=" + (h.since() || 0));
        if (ok !== true) { const re = ok === false; ok = true; h.status && h.status(true, re); }
        h.data(res);
      } catch(e) {
        if (ok !== false) { ok = false; h.status && h.status(false); }
      } finally { busy = false; }
    }
    function schedule(){ clearTimeout(timer); timer = setTimeout(async () => { if (!document.hidden) await once(); schedule(); }, intervalMs); }
    document.addEventListener("visibilitychange", () => { if (!document.hidden) { once(); } });
    once().then(schedule);
  }
};
})();
