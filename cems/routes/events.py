"""Shared event routes: public catalogue, details and QR ticket verification."""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..models import (
    EVENT_CATEGORIES,
    ATT_PRESENT,
    REG_CONFIRMED,
    Event,
    Registration,
    utcnow,
)
from ..services import domain
from ..utils.helpers import build_query_string, current_filters, parse_datetime

events_bp = Blueprint("events", __name__)


def _registered_event_ids():
    """Map event_id -> registration primary key for the logged-in student."""
    if not current_user.is_authenticated or not current_user.is_student:
        return {}
    return {
        event_id: pk
        for (event_id, pk) in db.session.query(Registration.event_id, Registration.id).filter(
            Registration.student_id == current_user.id, Registration.status == REG_CONFIRMED
        )
    }


def _catalogue_response():
    filters = current_filters()
    search = (filters.get("q") or "").strip()
    category = filters.get("category")
    status = filters.get("status")

    date_from, error_from = parse_datetime(filters.get("date_from"), "From date")
    date_to, error_to = parse_datetime(filters.get("date_to"), "To date")

    statement = Event.query
    if search:
        like = f"%{search}%"
        statement = statement.filter(
            or_(Event.title.ilike(like), Event.description.ilike(like), Event.venue.ilike(like))
        )
    if category and category != "all" and category in EVENT_CATEGORIES:
        statement = statement.filter(Event.category == category)
    if status and status != "all":
        statement = statement.filter(Event.status == status)

    rows = statement.order_by(Event.event_date.asc(), Event.start_time.asc()).all()
    for event in rows:
        event.refresh_status()

    if date_from and not error_from:
        rows = [e for e in rows if e.event_date >= date_from.date()]
    if date_to and not error_to:
        rows = [e for e in rows if e.event_date <= date_to.date()]

    return render_template(
        "events/catalogue.html",
        events=rows,
        filters=filters,
        categories=EVENT_CATEGORIES,
        registered_ids=_registered_event_ids(),
        query_string=build_query_string,
        filter_error=error_from or error_to,
    )


@events_bp.route("/")
@events_bp.route("/catalogue")
def catalogue():
    """Event catalogue for signed-in users (each role sees its own home link)."""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return _catalogue_response()


@events_bp.route("/<int:event_id>")
def detail(event_id):
    event = db.get_or_404(Event, event_id)
    event.refresh_status()

    registration = None
    my_attendance = None
    my_certificate = None
    if current_user.is_authenticated and current_user.is_student:
        registration = (
            Registration.query.filter_by(student_id=current_user.id, event_id=event.id)
            .order_by(Registration.id.desc())
            .first()
        )
        if registration and registration.is_cancelled:
            registration = None
        my_attendance = registration.attendance if registration else None
        from ..models import Certificate

        my_certificate = Certificate.query.filter_by(
            student_id=current_user.id, event_id=event.id
        ).first()

    open_now, reason = event.registration_state()

    if current_user.is_student:
        base = "student.event_detail"
    elif current_user.is_faculty:
        base = "faculty.event_detail"
    elif current_user.is_organizer and event.organizer_id == current_user.id:
        base = "organizer.event_detail"
    else:
        base = "events.detail"

    return render_template(
        "events/detail.html",
        event=event,
        registration=registration,
        my_attendance=my_attendance,
        my_certificate=my_certificate,
        open_now=open_now,
        reason=reason,
        stats=domain.event_statistics(event),
        dashboard_endpoint=base,
        show_register=current_user.is_student,
    )


@events_bp.route("/verify/<token>")
def verify_ticket(token):
    """Public QR verification page - no login required."""
    registration = Registration.query.filter_by(registration_id=(token or "").strip().upper()).first()
    if registration is None:
        return render_template("events/verify.html", registration=None, event=None, token=token), 404

    event = registration.event
    return render_template(
        "events/verify.html",
        registration=registration,
        event=event,
        token=token,
        attended=bool(registration.attendance and registration.attendance.status == ATT_PRESENT),
        now=utcnow(),
    )


@events_bp.route("/search")
def search():
    """Deep-linkable search that renders the catalogue results in place."""
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return _catalogue_response()