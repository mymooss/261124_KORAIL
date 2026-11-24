"""화면 라우트: /, /history."""
from flask import Blueprint, render_template, session

from ..auth.decorators import current_user, login_required

bp = Blueprint("views", __name__)


@bp.get("/")
@login_required
def console():
    return render_template("console.html", user=current_user(), pw_notice=session.pop("pw_notice", False))


@bp.get("/history")
@login_required
def history():
    return render_template("history.html", user=current_user())
