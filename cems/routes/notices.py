"""Shared notice routes used by all three roles."""

from flask import Blueprint, render_template

from ..extensions import db
from ..models import Notice

notices_bp = Blueprint("notices", __name__)


@notices_bp.route("/", strict_slashes=False)
def index():
    from flask_login import current_user

    from ..utils.decorators import role_required  # noqa: F401  (documentation)

    if not current_user.is_authenticated:
        from flask import redirect, url_for

        return redirect(url_for("auth.login"))

    rows = Notice.query.filter(
        (Notice.audience == "ALL") | (Notice.audience == current_user.role)
    ).order_by(Notice.is_important.desc(), Notice.published_at.desc()).all()

    return render_template(
        "notices/index.html",
        notices=rows,
        important=[n for n in rows if n.is_important],
    )


@notices_bp.route("/<int:notice_id>")
def detail(notice_id):
    from flask import flash, redirect, url_for
    from flask_login import current_user

    notice = db.get_or_404(Notice, notice_id)
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=f"/notices/{notice.id}"))
    if not notice.visible_to(current_user.role):
        flash("This notice is not published for your role.", "danger")
        return redirect(url_for("notices.index"))
    return render_template("notices/detail.html", notice=notice)