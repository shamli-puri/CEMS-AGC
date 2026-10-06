"""Faculty module: dashboard, events, registrations, attendance, feedback."""

import io

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import (
    ATT_PRESENT,
    EVENT_CANCELLED,
    EVENT_CATEGORIES,
    EVENT_COMPLETED,
    EVENT_UPCOMING,
    REG_CANCELLED,
    REG_CONFIRMED,
    Attendance,
    Event,
    Feedback,
    Notice,
    Registration,
    utcnow,
)
from ..services import certificate_service, domain, email_service
from ..services.domain import issue_certificate, mark_attendance_bulk
from ..utils.decorators import faculty_required
from ..utils.helpers import build_query_string, current_filters, parse_datetime

faculty_bp = Blueprint("faculty", __name__)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@faculty_bp.route("/")
@faculty_bp.route("/dashboard")
@faculty_required
def dashboard():
    stats = domain.faculty_statistics()

    upcoming_events = sorted(
        [e for e in stats["events"] if e.status in (EVENT_UPCOMING, "ONGOING")],
        key=lambda e: (e.event_date, e.start_time),
    )[:5]
    recent_events = sorted(stats["events"], key=lambda e: e.event_date, reverse=True)[:5]

    notices = Notice.query.filter(
        (Notice.audience == "ALL") | (Notice.audience == current_user.role)
    ).order_by(Notice.is_important.desc(), Notice.published_at.desc()).limit(4).all()

    pending_events = [
        e
        for e in stats["events"]
        if e.status in (EVENT_UPCOMING, "COMPLETED", "ONGOING") and not e.is_cancelled
    ]
    pending_rows = []
    for event in pending_events[:8]:
        confirmed = [r for r in event.registrations if r.is_confirmed]
        unmarked = [r for r in confirmed if not r.attendance]
        if confirmed and unmarked:
            pending_rows.append((event, len(unmarked), len(confirmed)))

    recent_feedback = (
        Feedback.query.order_by(Feedback.created_at.desc()).limit(5).all()
    )

    return render_template(
        "faculty/dashboard.html",
        stats=stats,
        upcoming_events=upcoming_events,
        recent_events=recent_events,
        notices=notices,
        pending_rows=pending_rows,
        recent_feedback=recent_feedback,
        profile_score=domain.profile_completeness(current_user),
    )


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@faculty_bp.route("/events")
@faculty_required
def events():
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

    rows = statement.order_by(Event.event_date.desc()).all()
    for event in rows:
        event.refresh_status()

    if date_from and not error_from:
        rows = [e for e in rows if e.event_date >= date_from.date()]
    if date_to and not error_to:
        rows = [e for e in rows if e.event_date <= date_to.date()]

    return render_template(
        "faculty/events.html",
        events=rows,
        filters=filters,
        categories=EVENT_CATEGORIES,
        query_string=build_query_string,
        filter_error=error_from or error_to,
    )


@faculty_bp.route("/events/<int:event_id>")
@faculty_required
def event_detail(event_id):
    event = db.get_or_404(Event, event_id)
    event.refresh_status()
    registrations = sorted(
        event.registrations, key=lambda r: (r.student.name.lower() if r.student else "")
    )
    return render_template(
        "faculty/event_detail.html",
        event=event,
        registrations=registrations,
        confirmed=[r for r in registrations if r.is_confirmed],
        stats=domain.event_statistics(event),
    )


# ---------------------------------------------------------------------------
# Registrations / attendees
# ---------------------------------------------------------------------------
@faculty_bp.route("/events/<int:event_id>/registrations")
@faculty_required
def event_registrations(event_id):
    event = db.get_or_404(Event, event_id)
    event.refresh_status()

    scope = (request.args.get("scope") or "confirmed").lower()
    rows = sorted(
        event.registrations, key=lambda r: (r.student.name.lower() if r.student else "")
    )
    if scope == "confirmed":
        rows = [r for r in rows if r.is_confirmed]
    elif scope == "cancelled":
        rows = [r for r in rows if r.is_cancelled]
    elif scope == "present":
        rows = [r for r in rows if r.is_confirmed and r.attendance and r.attendance.status == ATT_PRESENT]
    elif scope == "absent":
        rows = [r for r in rows if r.is_confirmed and r.attendance and r.attendance.status != ATT_PRESENT]
    elif scope == "unmarked":
        rows = [r for r in rows if r.is_confirmed and not r.attendance]

    return render_template(
        "faculty/registrations.html",
        event=event,
        registrations=rows,
        scope=scope,
        stats=domain.event_statistics(event),
    )


@faculty_bp.route("/events/<int:event_id>/attendees")
@faculty_required
def attendees(event_id):
    event = db.get_or_404(Event, event_id)
    event.refresh_status()
    rows = [r for r in event.registrations if r.is_confirmed]
    rows.sort(key=lambda r: (r.student.name.lower() if r.student else ""))
    return render_template(
        "faculty/attendees.html",
        event=event,
        registrations=rows,
        stats=domain.event_statistics(event),
    )


# ---------------------------------------------------------------------------
# Attendance marking
# ---------------------------------------------------------------------------
@faculty_bp.route("/events/<int:event_id>/attendance", methods=["GET", "POST"])
@faculty_required
def attendance(event_id):
    event = db.get_or_404(Event, event_id)
    event.refresh_status()

    rows = [r for r in event.registrations if r.is_confirmed]
    rows.sort(key=lambda r: (r.student.name.lower() if r.student else ""))

    if request.method == "POST":
        present_ids = set()
        for value in request.form.getlist("present"):
            try:
                present_ids.add(int(value))
            except (TypeError, ValueError):
                continue
        scope = request.form.get("scope", "marked")
        all_ids = {r.id for r in rows}
        if scope == "all":
            targets = all_ids
        elif scope == "unmarked":
            targets = {r.id for r in rows if not r.attendance}
        else:
            targets = present_ids | {int(v) for v in request.form.getlist("absent") if v.isdigit()}

        remarks = (request.form.get("remarks") or "").strip()[:160]
        applied = mark_attendance_bulk(event, sorted(targets), present_ids, current_user, remarks or None)
        db.session.commit()

        if event.certificate_eligible and event.status == EVENT_COMPLETED:
            issued = 0
            for registration in event.registrations:
                if domain.is_certificate_eligible(event, registration):
                    _, created = issue_certificate(registration, current_user)
                    issued += 1 if created else 0
            if issued:
                db.session.commit()
                flash(
                    f"{issued} certificate(s) issued for attended participants.",
                    "success",
                )

        if applied:
            flash(f"Attendance saved for {applied} participant(s) of \"{event.title}\".", "success")
        else:
            flash("No valid participants were selected for attendance marking.", "warning")
        return redirect(url_for("faculty.attendance", event_id=event.id))

    rows = [r for r in rows if r.is_confirmed]
    marked = [r for r in rows if r.attendance]
    unmarked = [r for r in rows if not r.attendance]
    return render_template(
        "faculty/attendance.html",
        event=event,
        registrations=rows,
        marked=marked,
        unmarked=unmarked,
        stats=domain.event_statistics(event),
    )


@faculty_bp.route("/registrations/<int:registration_id>/toggle-attendance", methods=["POST"])
@faculty_required
def toggle_attendance(registration_id):
    registration = db.get_or_404(Registration, registration_id)
    event = registration.event
    if not registration.is_confirmed:
        flash("Only confirmed registrations can have attendance marked.", "warning")
        return redirect(url_for("faculty.event_registrations", event_id=event.id))

    record = Attendance.query.filter_by(registration_id=registration.id).first()
    if record is None:
        mark_attendance_bulk(event, [registration.id], {registration.id}, current_user)
        message = f"{registration.student.name} marked PRESENT."
    elif record.status == ATT_PRESENT:
        mark_attendance_bulk(event, [registration.id], set(), current_user, record.remarks)
        message = f"{registration.student.name} marked ABSENT."
    else:
        mark_attendance_bulk(event, [registration.id], {registration.id}, current_user, record.remarks)
        message = f"{registration.student.name} marked PRESENT."
    db.session.commit()
    flash(message, "success")
    return redirect(request.referrer or url_for("faculty.event_registrations", event_id=event.id))


@faculty_bp.route("/events/<int:event_id>/attendance/report.pdf")
@faculty_required
def attendance_report(event_id):
    event = db.get_or_404(Event, event_id)
    rows = [r for r in event.registrations if r.is_confirmed]
    rows.sort(key=lambda r: (r.student.name.lower() if r.student else ""))
    try:
        pdf = certificate_service.build_attendance_report_pdf(event, rows, marked_by=current_user)
    except Exception as exc:
        current_app.logger.exception("Attendance report failed")
        flash(f"Could not generate the attendance report: {exc}", "danger")
        return redirect(url_for("faculty.attendance", event_id=event.id))

    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"attendance-{event.id}.pdf",
    )


@faculty_bp.route("/attendance")
@faculty_bp.route("/attendance_records")
@faculty_required
def attendance_records():
    stats = domain.faculty_statistics()
    rows = (
        Attendance.query.options(joinedload(Attendance.student), joinedload(Attendance.event))
        .order_by(Attendance.marked_at.desc())
        .limit(200)
        .all()
    )
    return render_template(
        "faculty/attendance_records.html",
        stats=stats,
        records=rows,
    )


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
@faculty_bp.route("/feedback")
@faculty_required
def feedback():
    filters = current_filters()
    statement = Feedback.query.options(
        joinedload(Feedback.student), joinedload(Feedback.event)
    )
    search = (filters.get("q") or "").strip()
    if search:
        statement = statement.join(Event).filter(
            or_(Event.title.ilike(f"%{search}%"), Feedback.comments.ilike(f"%{search}%"))
        )
    rating = filters.get("rating")
    if rating and rating.isdigit() and 1 <= int(rating) <= 5:
        statement = statement.filter(Feedback.rating == int(rating))

    rows = statement.order_by(Feedback.created_at.desc()).all()
    ratings = [f.rating for f in Feedback.query.all() if f.rating]
    average = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    distribution = {str(i): 0 for i in range(1, 6)}
    for value in ratings:
        distribution[str(value)] += 1

    return render_template(
        "faculty/feedback.html",
        feedback_rows=rows,
        average=average,
        total=len(ratings),
        distribution=distribution,
        filters=filters,
        query_string=build_query_string,
    )


@faculty_bp.route("/feedback/<int:feedback_id>")
@faculty_required
def feedback_detail(feedback_id):
    row = db.get_or_404(Feedback, feedback_id)
    return render_template("faculty/feedback_detail.html", entry=row)


# ---------------------------------------------------------------------------
# Notices
# ---------------------------------------------------------------------------
@faculty_bp.route("/notices")
@faculty_required
def notices():
    rows = Notice.query.filter(
        (Notice.audience == "ALL") | (Notice.audience == current_user.role)
    ).order_by(Notice.is_important.desc(), Notice.published_at.desc()).all()
    return render_template("faculty/notices.html", notices=rows)


@faculty_bp.route("/notices/<int:notice_id>")
@faculty_required
def notice_detail(notice_id):
    row = db.get_or_404(Notice, notice_id)
    if not row.visible_to(current_user.role):
        flash("This notice is not published for faculty.", "danger")
        return redirect(url_for("faculty.notices"))
    return render_template("faculty/notice_detail.html", notice=row)


# ---------------------------------------------------------------------------
# Send event reminder to participants (uses the safe email fallback)
# ---------------------------------------------------------------------------
@faculty_bp.route("/events/<int:event_id>/remind", methods=["POST"])
@faculty_required
def remind_participants(event_id):
    event = db.get_or_404(Event, event_id)
    recipients = [r.student.email for r in event.registrations if r.is_confirmed and r.student]
    if not recipients:
        flash("No confirmed participants to remind for this event.", "warning")
        return redirect(url_for("faculty.event_detail", event_id=event.id))

    result = email_service.send_email(
        subject=f"[CEMS-AGC] Reminder: {event.title}",
        recipients=recipients,
        body=(
            f"Dear participant,\n\n"
            f"This is a reminder for \"{event.title}\" on {event.event_date:%d %B %Y} "
            f"at {event.venue}.\n\nKindly carry your CEMS digital ticket.\n\n"
            f"-- CEMS | AGC Campus Event Management System"
        ),
    )
    if result.get("delivered"):
        flash(f"Reminder emailed to {len(recipients)} participant(s).", "success")
    else:
        flash(
            f"Reminder prepared for {len(recipients)} participant(s) and recorded as a "
            f"development message. {result.get('reason', '')}",
            "info",
        )
    return redirect(url_for("faculty.event_detail", event_id=event.id))