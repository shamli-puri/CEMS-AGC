"""Student module: dashboard, events, registration, tickets, attendance,
certificates, feedback, notices and profile shortcuts."""

import io
from datetime import datetime

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
    REG_CONFIRMED,
    Certificate,
    Event,
    Feedback,
    Notice,
    Registration,
    utcnow,
)
from ..services import certificate_service, domain, email_service, qr_service
from ..services.domain import next_code
from ..utils.decorators import student_required
from ..utils.helpers import build_query_string, current_filters, parse_datetime

student_bp = Blueprint("student", __name__)


def _registration_query():
    return Registration.query.options(
        joinedload(Registration.event).joinedload(Event.organizer),
        joinedload(Registration.attendance),
    ).filter_by(student_id=current_user.id)


def _my_registration(event_id, confirmed_only=True):
    query = Registration.query.filter_by(student_id=current_user.id, event_id=event_id)
    if confirmed_only:
        query = query.filter_by(status=REG_CONFIRMED)
    return query.order_by(Registration.id.desc()).first()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@student_bp.route("/")
@student_bp.route("/dashboard")
@student_required
def dashboard():
    stats = domain.student_statistics(current_user.id)

    registrations = sorted(
        stats["confirmed_registrations"],
        key=lambda r: (r.event.event_date, r.event.start_time),
    )
    upcoming_regs = [
        r
        for r in registrations
        if r.event.status != EVENT_CANCELLED and r.event.end_datetime >= utcnow()
    ][:4]
    past_regs = sorted(
        [r for r in registrations if r.event.status == EVENT_CANCELLED or r.event.end_datetime < utcnow()],
        key=lambda r: r.event.event_date,
        reverse=True,
    )[:4]

    upcoming_events = (
        Event.query.filter(
            Event.status.in_([EVENT_UPCOMING]), Event.event_date >= datetime.utcnow().date()
        )
        .order_by(Event.event_date.asc(), Event.start_time.asc())
        .limit(6)
        .all()
    )
    for event in upcoming_events:
        event.refresh_status()

    notices = Notice.query.filter(
        (Notice.audience == "ALL") | (Notice.audience == current_user.role)
    ).order_by(Notice.is_important.desc(), Notice.published_at.desc()).limit(4).all()

    recent_certificates = (
        Certificate.query.filter_by(student_id=current_user.id)
        .order_by(Certificate.issued_at.desc())
        .limit(3)
        .all()
    )

    return render_template(
        "student/dashboard.html",
        stats=stats,
        upcoming_regs=upcoming_regs,
        past_regs=past_regs,
        upcoming_events=upcoming_events,
        notices=notices,
        recent_certificates=recent_certificates,
        profile_score=domain.profile_completeness(current_user),
    )


# ---------------------------------------------------------------------------
# Events browsing
# ---------------------------------------------------------------------------
@student_bp.route("/events")
@student_required
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

    rows = statement.order_by(Event.event_date.asc(), Event.start_time.asc()).all()
    for event in rows:
        event.refresh_status()

    if date_from and not error_from:
        rows = [e for e in rows if e.event_date >= date_from.date()]
    if date_to and not error_to:
        rows = [e for e in rows if e.event_date <= date_to.date()]

    registered_ids = {
        event_id: pk
        for (event_id, pk) in db.session.query(
            Registration.event_id, Registration.id
        ).filter(
            Registration.student_id == current_user.id, Registration.status == REG_CONFIRMED
        )
    }
    return render_template(
        "student/events.html",
        events=rows,
        filters=filters,
        registered_ids=registered_ids,
        categories=EVENT_CATEGORIES,
        query_string=build_query_string,
        filter_error=error_from or error_to,
    )


@student_bp.route("/events/<int:event_id>")
@student_required
def event_detail(event_id):
    event = db.get_or_404(Event, event_id)
    event.refresh_status()

    registration = _my_registration(event.id, confirmed_only=False)
    if registration and registration.is_cancelled:
        registration = None

    open_now, reason = event.registration_state()

    feedback = None
    attendance = None
    certificate = None
    if _my_registration(event.id):
        feedback = Feedback.query.filter_by(student_id=current_user.id, event_id=event.id).first()
        attendance = registration.attendance if registration else None
        certificate = Certificate.query.filter_by(student_id=current_user.id, event_id=event.id).first()

    return render_template(
        "student/event_detail.html",
        event=event,
        registration=registration,
        open_now=open_now,
        reason=reason,
        feedback=feedback,
        attendance=attendance,
        certificate=certificate,
        stats=domain.event_statistics(event),
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
@student_bp.route("/events/<int:event_id>/register", methods=["POST"])
@student_required
def register(event_id):
    event = db.get_or_404(Event, event_id)
    event.refresh_status()

    reason = domain.registration_block_reason(event, current_user)
    if reason:
        flash(reason, "danger")
        return redirect(url_for("student.event_detail", event_id=event.id))

    code = next_code(Registration.registration_id, "AGC-REG")
    registration = Registration(
        registration_id=code,
        student_id=current_user.id,
        event_id=event.id,
        status=REG_CONFIRMED,
    )
    db.session.add(registration)
    db.session.commit()

    email_service.send_registration_email(registration)
    flash(
        f'Registration successful for "{event.title}". '
        f"Your registration ID is {registration.registration_id}.",
        "success",
    )
    return redirect(url_for("student.ticket", registration_id=registration.id))


@student_bp.route("/registrations/<int:registration_id>/cancel", methods=["POST"])
@student_required
def cancel_registration(registration_id):
    registration = db.get_or_404(Registration, registration_id)
    if registration.student_id != current_user.id:
        flash("You can only cancel your own registrations.", "danger")
        return redirect(url_for("student.registrations"))

    ok, message = domain.cancel_registration(registration)
    if ok:
        db.session.commit()
        email_service.send_registration_cancelled_email(registration)
        flash(f"{message} Registration ID {registration.registration_id} is now void.", "success")
    else:
        flash(message, "warning")
    return redirect(url_for("student.registrations"))


@student_bp.route("/registrations")
@student_bp.route("/my-registrations")
@student_required
def registrations():
    scope = (request.args.get("scope") or "all").lower()
    rows = _registration_query().order_by(Registration.registered_at.desc()).all()

    now = utcnow()
    if scope == "upcoming":
        rows = [
            r
            for r in rows
            if r.is_confirmed and r.event.status != EVENT_CANCELLED and r.event.end_datetime >= now
        ]
    elif scope == "attended":
        rows = [r for r in rows if r.is_confirmed and r.attendance and r.attendance.status == ATT_PRESENT]
    elif scope == "cancelled":
        rows = [r for r in rows if r.is_cancelled]
    elif scope == "past":
        rows = [r for r in rows if r.is_confirmed and r.event.end_datetime < now]

    return render_template(
        "student/registrations.html",
        registrations=rows,
        scope=scope,
        stats=domain.student_statistics(current_user.id),
    )


# ---------------------------------------------------------------------------
# Digital ticket + QR
# ---------------------------------------------------------------------------
@student_bp.route("/registrations/<int:registration_id>/ticket")
@student_required
def ticket(registration_id):
    registration = db.get_or_404(Registration, registration_id)
    if registration.student_id != current_user.id:
        flash("This ticket belongs to another student.", "danger")
        return redirect(url_for("student.registrations"))
    if registration.is_cancelled:
        flash("This registration was cancelled, so the ticket is no longer valid.", "warning")
        return redirect(url_for("student.registrations"))

    payload = qr_service.build_qr_payload(registration)
    verify_url = url_for("events.verify_ticket", token=registration.registration_id, _external=True)
    return render_template(
        "student/ticket.html",
        registration=registration,
        event=registration.event,
        payload=payload,
        verify_url=verify_url,
        qr_png_url=url_for("student.ticket_qr", registration_id=registration.id),
    )


@student_bp.route("/registrations/<int:registration_id>/qr.png")
@student_required
def ticket_qr(registration_id):
    registration = db.get_or_404(Registration, registration_id)
    if registration.student_id != current_user.id:
        return ("Forbidden", 403)
    try:
        png = qr_service.qr_png_bytes(qr_service.build_qr_payload(registration), box_size=10)
    except Exception as exc:  # pragma: no cover - defensive
        current_app.logger.warning("QR generation failed: %s", exc)
        return ("QR code generation unavailable", 500)
    return send_file(
        io.BytesIO(png),
        mimetype="image/png",
        download_name=f"{registration.registration_id}-qr.png",
    )


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
@student_bp.route("/attendance")
@student_required
def attendance():
    rows = [r for r in _registration_query().all() if r.is_confirmed]
    rows.sort(key=lambda r: r.event.event_date, reverse=True)

    present = [r for r in rows if r.attendance and r.attendance.status == ATT_PRESENT]
    absent = [r for r in rows if r.attendance and r.attendance.status != ATT_PRESENT]
    pending = [r for r in rows if not r.attendance]

    return render_template(
        "student/attendance.html",
        rows=rows,
        present=present,
        absent=absent,
        pending=pending,
        rate=round((len(present) / len(rows)) * 100, 1) if rows else 0.0,
    )


@student_bp.route("/attendance/record.pdf")
@student_required
def attendance_pdf():
    rows = [r for r in _registration_query().all() if r.is_confirmed]
    rows.sort(key=lambda r: r.event.event_date, reverse=True)
    try:
        pdf = certificate_service.build_attendance_record_pdf(rows, current_user)
    except Exception as exc:
        current_app.logger.exception("Attendance PDF failed")
        flash(f"Could not build the attendance record: {exc}", "danger")
        return redirect(url_for("student.attendance"))

    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="cems-attendance-record.pdf",
    )


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------
@student_bp.route("/certificates")
@student_bp.route("/certificates/")
@student_required
def certificates():
    domain.ensure_certificate_rows(current_user.id)
    db.session.commit()

    rows = (
        Certificate.query.filter_by(student_id=current_user.id)
        .order_by(Certificate.issued_at.desc())
        .all()
    )
    existing = {c.registration_id for c in rows}
    eligible = [
        r
        for r in _registration_query().all()
        if domain.is_certificate_eligible(r.event, r)
        and r.event.status == EVENT_COMPLETED
        and r.id not in existing
    ]
    return render_template(
        "student/certificates.html",
        certificates=rows,
        eligible=eligible,
        profile_score=domain.profile_completeness(current_user),
    )


@student_bp.route("/certificates/<int:certificate_id>/pdf")
@student_bp.route("/certificates/<int:certificate_id>/download")
@student_required
def certificate_pdf(certificate_id):
    certificate = db.get_or_404(Certificate, certificate_id)
    if certificate.student_id != current_user.id:
        flash("That certificate belongs to another student.", "danger")
        return redirect(url_for("student.certificates"))
    try:
        pdf_bytes = certificate_service.build_certificate_pdf(certificate)
    except Exception as exc:
        current_app.logger.exception("Certificate PDF failed")
        flash(f"Could not generate the certificate PDF: {exc}", "danger")
        return redirect(url_for("student.certificates"))

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"certificate-{certificate.certificate_id}.pdf",
    )


@student_bp.route("/certificates/<int:certificate_id>/send", methods=["GET", "POST"])
@student_required
def certificate_email(certificate_id):
    certificate = db.get_or_404(Certificate, certificate_id)
    if certificate.student_id != current_user.id:
        flash("That certificate belongs to another student.", "danger")
        return redirect(url_for("student.certificates"))

    result = email_service.send_certificate_email(certificate)
    if result.get("delivered"):
        flash(f"Certificate email sent to {certificate.student.email}.", "success")
    else:
        flash(f"Certificate email recorded as a development message. {result.get('reason', '')}", "info")
    return redirect(url_for("student.certificates"))


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
@student_bp.route("/feedback")
@student_required
def feedback_list():
    rows = _registration_query().order_by(Registration.registered_at.desc()).all()
    attended = [r for r in rows if r.is_confirmed and r.attendance and r.attendance.status == ATT_PRESENT]

    entries = (
        Feedback.query.filter_by(student_id=current_user.id)
        .order_by(Feedback.created_at.desc())
        .all()
    )
    given_ids = {f.registration_id for f in entries}
    pending = [r for r in attended if r.id not in given_ids]
    average = round(sum(f.rating for f in entries) / len(entries), 2) if entries else 0.0

    return render_template(
        "student/feedback.html",
        entries=entries,
        pending=pending,
        average=average,
        total=len(entries),
    )


@student_bp.route("/events/<int:event_id>/feedback", methods=["POST"])
@student_required
def submit_feedback(event_id):
    event = db.get_or_404(Event, event_id)
    registration = _my_registration(event.id)

    if registration is None:
        flash("You can only give feedback for events you registered for.", "danger")
        return redirect(url_for("student.feedback_list"))
    if not registration.attendance or registration.attendance.status != ATT_PRESENT:
        flash("Feedback can only be submitted for events you actually attended.", "warning")
        return redirect(url_for("student.feedback_list"))
    if Feedback.query.filter_by(registration_id=registration.id).first():
        flash("You have already submitted feedback for this event.", "info")
        return redirect(url_for("student.feedback_list"))

    comments = (request.form.get("comments") or "").strip()
    errors = []
    try:
        rating = int(request.form.get("rating"))
    except (TypeError, ValueError):
        rating = 0
        errors.append("Please select a rating between 1 and 5 stars.")
    if rating and not (1 <= rating <= 5):
        errors.append("Rating must be between 1 and 5.")
    if len(comments) < 5:
        errors.append("Please write a short comment (at least 5 characters).")
    if len(comments) > 1000:
        errors.append("Comments must be 1000 characters or fewer.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return redirect(url_for("student.feedback_list"))

    entry = Feedback(
        student_id=current_user.id,
        event_id=event.id,
        registration_id=registration.id,
        rating=rating,
        comments=comments,
    )
    db.session.add(entry)
    db.session.commit()
    flash(f'Thank you! Your feedback for "{event.title}" has been recorded.', "success")
    return redirect(url_for("student.feedback_list"))


# ---------------------------------------------------------------------------
# Notices (student view)
# ---------------------------------------------------------------------------
@student_bp.route("/notices")
@student_required
def notices():
    rows = Notice.query.filter(
        (Notice.audience == "ALL") | (Notice.audience == current_user.role)
    ).order_by(Notice.is_important.desc(), Notice.published_at.desc()).all()
    return render_template("student/notices.html", notices=rows)


@student_bp.route("/notices/<int:notice_id>")
@student_required
def notice_detail(notice_id):
    row = db.get_or_404(Notice, notice_id)
    if not row.visible_to(current_user.role):
        flash("This notice is not published for your role.", "danger")
        return redirect(url_for("student.notices"))
    return render_template("student/notice_detail.html", notice=row)


# ---------------------------------------------------------------------------
# Students may be able to see who else attends an event
# ---------------------------------------------------------------------------
@student_bp.route("/events/<int:event_id>/participants")
@student_required
def participants(event_id):
    event = db.get_or_404(Event, event_id)
    registration = _my_registration(event.id)
    if registration is None:
        flash("Register for this event to view the participant list.", "info")
        return redirect(url_for("student.event_detail", event_id=event.id))

    rows = [r for r in event.registrations if r.is_confirmed]
    rows.sort(key=lambda r: r.student.name.lower() if r.student else "")
    return render_template(
        "student/participants.html",
        event=event,
        rows=rows,
        stats=domain.event_statistics(event),
        my_registration_id=registration.id,
    )