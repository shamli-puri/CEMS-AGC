"""Role based access control decorators for CEMS."""

from functools import wraps

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user

from ..models import ROLE_LABELS


def role_required(*roles):
    """Allow access only to the listed roles. Everything else is rejected."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in to continue.", "info")
                return redirect(
                    url_for("auth.login", role=_safe_role_hint(request.path), next=_current_target())
                )
            if roles and current_user.role not in roles:
                return _denied(roles)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def _current_target():
    return request.full_path.rstrip("?")


student_required = role_required("STUDENT")
faculty_required = role_required("FACULTY")
organizer_required = role_required("ORGANIZER")


def _denied(allowed_roles):
    """Send the user back to their own dashboard with a clear message."""
    names = ", ".join(ROLE_LABELS.get(r, r) for r in allowed_roles)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        abort(403)
    flash(f"Access denied. This page is restricted to: {names}.", "danger")
    home = {
        "STUDENT": "student.dashboard",
        "FACULTY": "faculty.dashboard",
        "ORGANIZER": "organizer.dashboard",
    }.get(current_user.role, "main.role_home")
    return redirect(url_for(home))


def _safe_role_hint(path):
    if path.startswith("/faculty"):
        return "faculty"
    if path.startswith("/organizer"):
        return "organizer"
    if path.startswith("/student"):
        return "student"
    return None