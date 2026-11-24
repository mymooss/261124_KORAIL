"""로그인·권한 데코레이터."""
from functools import wraps

from flask import abort, g, jsonify, redirect, request, session, url_for

from ..db import get_db

ROLE_LEVEL = {"viewer": 1, "operator": 2, "admin": 3}
ROLE_LABEL = {"viewer": "조회자", "operator": "관제사", "admin": "관리자"}
ROLE_MESSAGE = {"operator": "관제사 권한이 필요합니다.", "admin": "관리자 권한이 필요합니다."}


def current_user():
    if "user" in g:
        return g.user
    user = None
    uid = session.get("user_id")
    if uid:
        r = get_db().execute(
            "SELECT id, username, display_name, role, is_active FROM users WHERE id=?", (uid,)).fetchone()
        if r and r["is_active"]:
            user = {"id": r["id"], "username": r["username"], "display_name": r["display_name"],
                    "role": r["role"], "role_label": ROLE_LABEL[r["role"]]}
    g.user = user
    return user


def has_role(user, role):
    return bool(user) and ROLE_LEVEL[user["role"]] >= ROLE_LEVEL[role]


def _is_api():
    return request.path.startswith("/api/")


def _unauthorized():
    if _is_api():
        return jsonify(error={"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."}), 401
    nxt = request.full_path if request.query_string else request.path
    return redirect(url_for("auth.login", next=nxt))


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return _unauthorized()
        return view(*args, **kwargs)
    return wrapper


def role_required(role):
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return _unauthorized()
            if not has_role(user, role):
                if _is_api():
                    return jsonify(error={"code": "FORBIDDEN", "message": ROLE_MESSAGE[role]}), 403
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return deco
