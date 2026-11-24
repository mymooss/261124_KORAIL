"""/login, /logout."""
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db
from ..repo import event_repo
from .decorators import ROLE_LABEL, current_user, login_required

bp = Blueprint("auth", __name__)

DEFAULT_PASSWORDS = {"admin": "admin1234!", "operator": "operator1234!", "viewer": "viewer1234!"}


def _safe_next(nxt):
    if nxt and nxt.startswith("/") and not nxt.startswith("//") and not nxt.startswith("/\\"):
        return nxt
    return url_for("views.console")


def _audit(message, user):
    try:
        event_repo.audit(get_db(), message, user["id"] if user else None)
    except Exception:  # 감사 로그 실패가 로그인을 막지 않게 한다
        current_app.logger.exception("감사 로그 기록 실패")


@bp.route("/login", methods=["GET", "POST"])
def login():
    nxt = request.values.get("next", "")
    if request.method == "GET" and current_user():
        return redirect(_safe_next(nxt))
    error = None
    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        r = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if r is None or not r["is_active"] or not check_password_hash(r["password_hash"], password):
            error = "아이디 또는 비밀번호가 올바르지 않습니다."
        else:
            session.clear()
            session["user_id"] = r["id"]
            if DEFAULT_PASSWORDS.get(username) == password:
                session["pw_notice"] = True
            user = {"id": r["id"], "display_name": r["display_name"]}
            _audit(f"로그인: {r['display_name']}({username}) · 권한 {ROLE_LABEL[r['role']]}", user)
            return redirect(_safe_next(nxt))
    return render_template("login.html", error=error, username=username, next=nxt), (401 if error else 200)


@bp.route("/password", methods=["GET", "POST"])
@login_required
def password():
    user = current_user()
    error, done = None, False
    if request.method == "POST":
        cur = request.form.get("current") or ""
        new = request.form.get("new") or ""
        conf = request.form.get("confirm") or ""
        conn = get_db()
        r = conn.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not check_password_hash(r["password_hash"], cur):
            error = "현재 비밀번호가 올바르지 않습니다."
        elif len(new) < 8:
            error = "새 비밀번호는 8자 이상이어야 합니다."
        elif new != conf:
            error = "새 비밀번호 확인이 일치하지 않습니다."
        elif new == cur:
            error = "현재 비밀번호와 다른 비밀번호를 입력하세요."
        else:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), user["id"]))
            done = True
            _audit(f"비밀번호 변경: {user['display_name']}({user['username']})", user)
    return render_template("password.html", user=user, error=error, done=done), (400 if error else 200)


@bp.post("/logout")
def logout():
    user = current_user()
    if user:
        _audit(f"로그아웃: {user['display_name']}({user['username']})", user)
    session.clear()
    return redirect(url_for("auth.login"))
