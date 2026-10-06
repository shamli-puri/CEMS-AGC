"""Organizer module: dashboard, event CRUD, registrations, attendance,
feedback, statistics, notices and certificates."""

import io
import os
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
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import (
    ATT_PRESENT,
    AUDIENCES,
    EVENT_CANCELLED,
    EVENT_CATEGORIES,
    EVENT_COMPLETED,
    EVENT_ONGOING,
    EVENT_STATUSES,
    EVENT_UPCOMING,
    REG_CANCELLED,
    REG_CONFIRMED,
    Attendance,
    Certificate,
    Event,
    Feedback,
    Notice,
    Registration,
    User,
    utcnow,
)
from ..services import certificate_service, domain, email_service
from ..services.domain import issue_certificate, mark_attendance_bulk
from ..utils.decorators import organizer_required
from ..utils.helpers import (
    allowed_file,
    build_query_string,
    current_filters,
    parse_date,
    parse_datetime,
    parse_time,
)

organizer_bp = Blueprint("organizer", __name__)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@organizer_bp.route("/")
@organizer_bp.route("/dashboard")
@organizer_required
def dashboard():
    stats = domain.organizer_statistics(current_user.id)

    events = stats["events"]
    upcoming = [e for e in events if e.status == EVENT_UPCOMING][:5]
    recent = sorted(events, key=lambda e: e.event_date, reverse=True)[:5]

    needs_attention = []
    for event in events:
        if event.status == EVENT_CANCELLED:
            continue
        confirmed = [r for r in event.registrations if r.is_confirmed]
        unmarked = [r for r in confirmed if not r.attendance]
        if confirmed and unmarked:
            needs_attention.append((event, len(unmarked), len(confirmed)))

    top_events = sorted(
        [e for e in events if e.status != EVENT_CANCELLED],
        key=lambda e: e.active_registration_count(),
        reverse=True,
    )[:5]

    recent_feedback = []
    event_ids = [e.id for e in events]
    if event_ids:
        recent_feedback = (
            Feedback.query.filter(Feedback.event_id.in_(event_ids))
            .options(joinedload(Feedback.student), joinedload(Feedback.event))
            .order_by(Feedback.created_at.desc())
            .limit(5)
            .all()
        )

    notices = Notice.query.filter(
        (Notice.audience == "ALL") | (Notice.audience == current_user.role)
    ).order_by(Notice.is_important.desc(), Notice.published_at.desc()).limit(4).all()

    return render_template(
        "organizer/dashboard.html",
        stats=stats,
        upcoming=upcoming,
        recent=recent,
        needs_attention=needs_attention,
        top_events=top_events,
        recent_feedback=recent_feedback,
        notices=notices,
        my_notices=Notice.query.filter_by(author_id=current_user.id).count(),
        profile_score=domain.profile_completeness(current_user),
    )


# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------
@organizer_bp.route("/events")
@organizer_required
def events():
    filters = current_filters()
    search = (filters.get("q") or "").strip()
    category = filters.get("category")
    status = filters.get("status")

    statement = Event.query.filter_by(organizer_id=current_user.id)
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

    totals = {
        "all": Event.query.filter_by(organizer_id=current_user.id).count(),
        "upcoming": len([e for e in domain.organizer_events(current_user.id) if e.status == EVENT_UPCOMING]),
        "completed": len([e for e in domain.organizer_events(current_user.id) if e.status == EVENT_COMPLETED]),
        "cancelled": len([e for e in domain.organizer_events(current_user.id) if e.status == EVENT_CANCELLED]),
    }
    db.session.commit()

    return render_template(
        "organizer/events.html",
        events=rows,
        filters=filters,
        categories=EVENT_CATEGORIES,
        statuses=EVENT_STATUSES,
        totals=totals,
        query_string=build_query_string,
    )


def _owned_event_or_404(event_id):
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != current_user.id:
        flash("You can only manage events that you organize.", "danger")
        return None
    return event


def _validate_event_form(event=None):
    """Validate / normalize the event form. Returns (form, errors)."""
    form = {
        "title": (request.form.get("title") or "").strip(),
        "description": (request.form.get("description") or "").strip(),
        "category": (request.form.get("category") or "").strip(),
        "event_date": (request.form.get("event_date") or "").strip(),
        "start_time": (request.form.get("start_time") or "").strip(),
        "end_time": (request.form.get("end_time") or "").strip(),
        "venue": (request.form.get("venue") or "").strip(),
        "max_capacity": (request.form.get("max_capacity") or "").strip(),
        "registration_deadline": (request.form.get("registration_deadline") or "").strip(),
        "certificate_eligible": bool(request.form.get("certificate_eligible")),
    }
    errors = []

    if len(form["title"]) < 5:
        errors.append("Event title must be at least 5 characters long.")
    if len(form["title"]) > 160:
        errors.append("Event title must be 160 characters or fewer.")
    if len(form["description"]) < 20:
        errors.append("Event description must be at least 20 characters long.")
    if form["category"] not in EVENT_CATEGORIES:
        errors.append("Please choose a valid event category.")
    if len(form["venue"]) < 3:
        errors.append("Venue is required.")

    event_date, err = parse_date(form["event_date"], "Event date")
    if err:
        errors.append(err)
    start_time, err = parse_time(form["start_time"], "Start time")
    if err:
        errors.append(err)
    end_time, err = parse_time(form["end_time"], "End time")
    if err:
        errors.append(err)

    if event_date and start_time and end_time and end_time <= start_time:
        errors.append("End time must be later than the start time.")

    try:
        capacity = int(form["max_capacity"])
        if capacity < 1:
            errors.append("Maximum capacity must be at least 1.")
        if capacity > 10000:
            errors.append("Maximum capacity must be 10000 or fewer.")
    except (TypeError, ValueError):
        capacity = 0
        errors.append("Maximum capacity must be a whole number.")

    deadline, err = parse_datetime(form["registration_deadline"], "Registration deadline")
    if err:
        errors.append(err)

    if event_date and deadline:
        if deadline.date() > event_date:
            errors.append("Registration deadline cannot be after the event date.")
        elif deadline.date() == event_date and start_time and deadline.time() > start_time:
            errors.append("Registration deadline must be before the event starts.")

    if event and capacity:
        confirmed = event.active_registration_count()
        if capacity < confirmed:
            errors.append(
                f"Capacity cannot be below the {confirmed} participant(s) already registered."
            )

    form["_date"] = event_date
    form["_start"] = start_time
    form["_end"] = end_time
    form["_deadline"] = deadline
    form["_capacity"] = capacity
    return form, errors


def _handle_image_upload():
    upload = request.files.get("event_image")
    if not upload or not upload.filename:
        return None, None
    if not allowed_file(upload.filename, current_app.config["ALLOWED_IMAGE_EXTENSIONS"]):
        return None, "Event image must be a PNG, JPG, GIF or WEBP file."
    filename = secure_filename(upload.filename)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stem, _, ext = filename.partition(".")
    saved = f"{stem or 'event'}_{stamp}.{ext}"
    upload.save(os.path.join(current_app.config["UPLOAD_FOLDER"], saved))
    return saved, None


@organizer_bp.route("/events/create", methods=["GET", "POST"])
@organizer_required
def create_event():
    form = {"certificate_eligible": True}
    if request.method == "GET":
        return render_template(
            "organizer/event_form.html",
            event=None,
            form=form,
            categories=EVENT_CATEGORIES,
            min_date=datetime.utcnow().strftime("%Y-%m-%d"),
        )

    form, errors = _validate_event_form()
    image_name, image_error = _handle_image_upload()
    if image_error:
        errors.append(image_error)

    if errors:
        for message in errors:
            flash(message, "danger")
        return (
            render_template(
                "organizer/event_form.html",
                event=None,
                form=form,
                categories=EVENT_CATEGORIES,
                min_date=datetime.utcnow().strftime("%Y-%m-%d"),
            ),
            400,
        )

    event = Event(
        title=form["title"],
        description=form["description"],
        category=form["category"],
        event_date=form["_date"],
        start_time=form["_start"],
        end_time=form["_end"],
        venue=form["venue"],
        organizer_id=current_user.id,
        max_capacity=form["_capacity"],
        registration_deadline=form["_deadline"],
        image_filename=image_name,
        status=EVENT_UPCOMING,
        certificate_eligible=form["certificate_eligible"],
    )
    db.session.add(event)
    db.session.commit()

    db.session.add(
        Notice(
            title=f"New event: {event.title}",
            description=(
                f"{event.title} has been scheduled for {event.event_date:%d %B %Y} at {event.venue}. "
                f"Registrations are open until {event.registration_deadline:%d %B %Y, %I:%M %p}."
            ),
            author_id=current_user.id,
            audience="ALL",
            is_important=False,
        )
    )
    db.session.commit()

    flash(f'Event "{event.title}" created successfully and is now open for registration.', "success")
    return redirect(url_for("organizer.event_detail", event_id=event.id))


@organizer_bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@organizer_required
def edit_event(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))

    if request.method == "GET":
        form = {
            "title": event.title,
            "description": event.description,
            "category": event.category,
            "event_date": event.event_date.strftime("%Y-%m-%d"),
            "start_time": event.start_time.strftime("%H:%M"),
            "end_time": event.end_time.strftime("%H:%M"),
            "venue": event.venue,
            "max_capacity": str(event.max_capacity),
            "registration_deadline": event.registration_deadline.strftime("%Y-%m-%dT%H:%M"),
            "certificate_eligible": event.certificate_eligible,
        }
        return render_template(
            "organizer/event_form.html",
            event=event,
            form=form,
            categories=EVENT_CATEGORIES,
            min_date="",
        )

    form, errors = _validate_event_form(event=event)
    remove_image = bool(request.form.get("remove_image"))
    image_name, image_error = _handle_image_upload()
    if image_error:
        errors.append(image_error)

    if errors:
        for message in errors:
            flash(message, "danger")
        return (
            render_template(
                "organizer/event_form.html",
                event=event,
                form=form,
                categories=EVENT_CATEGORIES,
                min_date="",
            ),
            400,
        )

    if image_name:
        _delete_image(event.image_filename)
        event.image_filename = image_name
    elif remove_image:
        _delete_image(event.image_filename)
        event.image_filename = None

    event.title = form["title"]
    event.description = form["description"]
    event.category = form["category"]
    event.event_date = form["_date"]
    event.start_time = form["_start"]
    event.end_time = form["_end"]
    event.venue = form["venue"]
    event.max_capacity = form["_capacity"]
    event.registration_deadline = form["_deadline"]
    event.certificate_eligible = form["certificate_eligible"]
    db.session.commit()

    flash(f'Event "{event.title}" has been updated.', "success")
    return redirect(url_for("organizer.event_detail", event_id=event.id))


def _delete_image(filename):
    if not filename:
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:  # pragma: no cover - filesystem edge case
        current_app.logger.warning("Could not remove image %s", path)


@organizer_bp.route("/events/<int:event_id>/cancel", methods=["POST"])
@organizer_required
def cancel_event(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))
    if event.status == EVENT_CANCELLED:
        flash("This event is already cancelled.", "info")
        return redirect(url_for("organizer.event_detail", event_id=event.id))

    event.status = EVENT_CANCELLED
    for registration in event.registrations:
        if registration.is_confirmed:
            registration.status = REG_CANCELLED
            registration.cancelled_at = utcnow()
    db.session.commit()

    email_service.send_event_cancelled_email(event)
    flash(
        f'"{event.title}" has been cancelled. All confirmed registrations were released and '
        "participants were notified.",
        "success",
    )
    return redirect(url_for("organizer.event_detail", event_id=event.id))


@organizer_bp.route("/events/<int:event_id>/restore", methods=["POST"])
@organizer_required
def restore_event(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))
    if event.status != EVENT_CANCELLED:
        flash("Only cancelled events can be restored.", "info")
        return redirect(url_for("organizer.event_detail", event_id=event.id))

    event.refresh_status()
    if event.registration_deadline < utcnow():
        event.status = EVENT_CANCELLED
        db.session.commit()
        flash(
            "This event cannot be restored because the registration deadline has already passed.",
            "warning",
        )
        return redirect(url_for("organizer.event_detail", event_id=event.id))

    db.session.commit()
    flash(f'"{event.title}" has been restored to {event.status.lower()} status.', "success")
    return redirect(url_for("organizer.event_detail", event_id=event.id))


@organizer_bp.route("/events/<int:event_id>/delete", methods=["POST"])
@organizer_required
def delete_event(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))

    title = event.title
    confirmed = event.active_registration_count()
    for registration in list(event.registrations):
        if registration.attendance:
            db.session.delete(registration.attendance)
    db.session.delete(event)
    db.session.commit()

    flash(
        f'Event "{title}" was permanently deleted'
        + (f" along with {confirmed} registration(s)." if confirmed else "."),
        "success",
    )
    return redirect(url_for("organizer.events"))


@organizer_bp.route("/events/<int:event_id>")
@organizer_required
def event_detail(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))
    event.refresh_status()

    registrations = sorted(
        event.registrations, key=lambda r: (r.student.name.lower() if r.student else "")
    )
    certificates = (
        Certificate.query.filter_by(event_id=event.id).order_by(Certificate.issued_at.desc()).all()
    )
    return render_template(
        "organizer/event_detail.html",
        event=event,
        registrations=registrations,
        confirmed=[r for r in registrations if r.is_confirmed],
        stats=domain.event_statistics(event),
        certificates=certificates,
    )


# ---------------------------------------------------------------------------
# Registrations management
# ---------------------------------------------------------------------------
@organizer_bp.route("/events/<int:event_id>/registrations")
@organizer_required
def event_registrations(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))
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
        "organizer/registrations.html",
        event=event,
        registrations=rows,
        scope=scope,
        stats=domain.event_statistics(event),
    )


@organizer_bp.route("/registrations/<int:registration_id>/cancel", methods=["POST"])
@organizer_required
def cancel_registration(registration_id):
    registration = db.get_or_404(Registration, registration_id)
    if registration.event.organizer_id != current_user.id:
        flash("You can only manage registrations for your own events.", "danger")
        return redirect(url_for("organizer.events"))

    ok, message = domain.cancel_registration(registration)
    if ok:
        db.session.commit()
        email_service.send_registration_cancelled_email(registration)
        flash(f"{message} {registration.student.name} has been notified.", "success")
    else:
        flash(message, "warning")
    return redirect(
        request.referrer or url_for("organizer.event_registrations", event_id=registration.event_id)
    )


@organizer_bp.route("/registrations/<int:registration_id>/restore", methods=["POST"])
@organizer_required
def restore_registration(registration_id):
    registration = db.get_or_404(Registration, registration_id)
    event = registration.event
    if event.organizer_id != current_user.id:
        flash("You can only manage registrations for your own events.", "danger")
        return redirect(url_for("organizer.events"))

    if not registration.is_cancelled:
        flash("This registration is already active.", "info")
    elif event.registration_closed:
        flash("Registrations for this event are closed.", "warning")
    elif event.active_registration_count() >= event.max_capacity:
        flash("The event has reached its maximum capacity.", "warning")
    else:
        registration.status = REG_CONFIRMED
        registration.cancelled_at = None
        db.session.commit()
        flash(
            f"Registration {registration.registration_id} restored for {registration.student.name}.",
            "success",
        )
    return redirect(url_for("organizer.event_registrations", event_id=event.id))


@organizer_bp.route("/events/<int:event_id>/attendees")
@organizer_required
def attendees(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))
    rows = [r for r in event.registrations if r.is_confirmed]
    rows.sort(key=lambda r: (r.student.name.lower() if r.student else ""))
    return render_template(
        "organizer/attendees.html",
        event=event,
        registrations=rows,
        stats=domain.event_statistics(event),
    )


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
@organizer_bp.route("/events/<int:event_id>/attendance", methods=["GET", "POST"])
@organizer_required
def attendance(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))
    event.refresh_status()

    rows = [r for r in event.registrations if r.is_confirmed]
    rows.sort(key=lambda r: (r.student.name.lower() if r.student else ""))

    if request.method == "POST":
        present_ids = set()
        for value in request.form.getlist("present"):
            if value.isdigit():
                present_ids.add(int(value))
        scope = request.form.get("scope", "marked")
        if scope == "all":
            targets = {r.id for r in rows}
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
                flash(f"{issued} certificate(s) issued for attended participants.", "success")

        flash(f"Attendance verified for {applied} participant(s).", "success" if applied else "warning")
        return redirect(url_for("organizer.attendance", event_id=event.id))

    marked = [r for r in rows if r.attendance]
    unmarked = [r for r in rows if not r.attendance]
    return render_template(
        "organizer/attendance.html",
        event=event,
        registrations=rows,
        marked=marked,
        unmarked=unmarked,
        stats=domain.event_statistics(event),
    )


@organizer_bp.route("/registrations/<int:registration_id>/toggle-attendance", methods=["POST"])
@organizer_required
def toggle_attendance(registration_id):
    registration = db.get_or_404(Registration, registration_id)
    event = registration.event
    if event.organizer_id != current_user.id:
        flash("You can only manage attendance for your own events.", "danger")
        return redirect(url_for("organizer.events"))
    if not registration.is_confirmed:
        flash("Only confirmed registrations can be marked.", "warning")
        return redirect(url_for("organizer.event_registrations", event_id=event.id))

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
    return redirect(
        request.referrer or url_for("organizer.event_registrations", event_id=event.id)
    )


@organizer_bp.route("/events/<int:event_id>/attendance/report.pdf")
@organizer_required
def attendance_report(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))
    rows = [r for r in event.registrations if r.is_confirmed]
    rows.sort(key=lambda r: (r.student.name.lower() if r.student else ""))
    try:
        pdf = certificate_service.build_attendance_report_pdf(event, rows, marked_by=current_user)
    except Exception as exc:
        current_app.logger.exception("Attendance report failed")
        flash(f"Could not generate the attendance report: {exc}", "danger")
        return redirect(url_for("organizer.attendance", event_id=event.id))

    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"attendance-{event.id}.pdf",
    )


@organizer_bp.route("/attendance")
@organizer_bp.route("/attendance_records")
@organizer_required
def attendance_records():
    event_ids = [e.id for e in domain.organizer_events(current_user.id)]
    rows = []
    if event_ids:
        rows = (
            Attendance.query.filter(Attendance.event_id.in_(event_ids))
            .options(joinedload(Attendance.student), joinedload(Attendance.event))
            .order_by(Attendance.marked_at.desc())
            .limit(300)
            .all()
        )
    return render_template(
        "organizer/attendance_records.html",
        records=rows,
        stats=domain.organizer_statistics(current_user.id),
    )


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------
@organizer_bp.route("/events/<int:event_id>/certificates", methods=["GET", "POST"])
@organizer_required
def event_certificates(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))

    if request.method == "POST":
        issued = 0
        for registration in event.registrations:
            if domain.is_certificate_eligible(event, registration):
                _, created = issue_certificate(registration, current_user)
                issued += 1 if created else 0
        db.session.commit()
        flash(f"{issued} new certificate(s) issued for \"{event.title}\".", "success")
        return redirect(url_for("organizer.event_certificates", event_id=event.id))

    rows = (
        Certificate.query.filter_by(event_id=event.id).order_by(Certificate.issued_at.desc()).all()
    )
    eligible = [
        r
        for r in event.registrations
        if domain.is_certificate_eligible(event, r)
        and not Certificate.query.filter_by(registration_id=r.id).first()
    ]
    return render_template(
        "organizer/certificates.html",
        event=event,
        certificates=rows,
        eligible=eligible,
        stats=domain.event_statistics(event),
    )


@organizer_bp.route("/certificates/<int:certificate_id>/pdf")
@organizer_required
def certificate_pdf(certificate_id):
    certificate = db.get_or_404(Certificate, certificate_id)
    if certificate.event.organizer_id != current_user.id:
        flash("You can only download certificates for your own events.", "danger")
        return redirect(url_for("organizer.events"))
    try:
        pdf = certificate_service.build_certificate_pdf(certificate)
    except Exception as exc:
        current_app.logger.exception("Certificate PDF failed")
        flash(f"Could not generate the certificate PDF: {exc}", "danger")
        return redirect(url_for("organizer.events"))
    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"certificate-{certificate.certificate_id}.pdf",
    )


@organizer_bp.route("/certificates/<int:certificate_id>/send", methods=["GET", "POST"])
@organizer_required
def certificate_send(certificate_id):
    certificate = db.get_or_404(Certificate, certificate_id)
    if certificate.event.organizer_id != current_user.id:
        flash("You can only email certificates for your own events.", "danger")
        return redirect(url_for("organizer.events"))
    result = email_service.send_certificate_email(certificate)
    if result.get("delivered"):
        flash(f"Certificate emailed to {certificate.student.email}.", "success")
    else:
        flash(f"Certificate email recorded as a development message. {result.get('reason', '')}", "info")
    return redirect(url_for("organizer.event_certificates", event_id=certificate.event_id))


# ---------------------------------------------------------------------------
# Statistics & feedback
# ---------------------------------------------------------------------------
@organizer_bp.route("/events/<int:event_id>/statistics")
@organizer_required
def event_statistics(event_id):
    event = _owned_event_or_404(event_id)
    if event is None:
        return redirect(url_for("organizer.events"))
    event.refresh_status()

    stats = domain.event_statistics(event)
    rows = [r for r in event.registrations if r.is_confirmed]
    rows.sort(key=lambda r: (r.student.name.lower() if r.student else ""))

    by_department = {}
    by_year = {}
    for registration in rows:
        student = registration.student
        if not student:
            continue
        by_department[student.department or "Unspecified"] = by_department.get(
            student.department or "Unspecified", 0
        ) + 1
        by_year[student.year_of_study or "Unspecified"] = by_year.get(
            student.year_of_study or "Unspecified", 0
        ) + 1

    return render_template(
        "organizer/event_statistics.html",
        event=event,
        stats=stats,
        registrations=rows,
        by_department=sorted(by_department.items(), key=lambda kv: kv[1], reverse=True),
        by_year=sorted(by_year.items(), key=lambda kv: kv[1], reverse=True),
    )


@organizer_bp.route("/statistics")
@organizer_required
def statistics():
    stats = domain.organizer_statistics(current_user.id)
    events = stats["events"]

    monthly = {}
    for event in events:
        key = event.event_date.strftime("%b %Y")
        entry = monthly.setdefault(key, {"events": 0, "registrations": 0, "attendees": 0})
        entry["events"] += 1
        entry["registrations"] += event.active_registration_count()
        entry["attendees"] += event.attendee_count()

    by_category = {}
    for event in events:
        by_category[event.category] = by_category.get(event.category, 0) + event.active_registration_count()

    return render_template(
        "organizer/statistics.html",
        stats=stats,
        events=events,
        monthly=sorted(monthly.items()),
        by_category=sorted(by_category.items(), key=lambda kv: kv[1], reverse=True),
    )


@organizer_bp.route("/feedback")
@organizer_required
def feedback():
    events = domain.organizer_events(current_user.id)
    event_ids = [e.id for e in events]
    event_filter = request.args.get("event_id", type=int)
    filters = current_filters()
    search = (filters.get("q") or "").strip()

    rows = []
    if event_ids:
        statement = Feedback.query.filter(Feedback.event_id.in_(event_ids)).options(
            joinedload(Feedback.student), joinedload(Feedback.event)
        )
        if event_filter:
            statement = statement.filter(Feedback.event_id == event_filter)
        if search:
            statement = statement.filter(Feedback.comments.ilike(f"%{search}%"))
        rating = filters.get("rating")
        if rating and rating.isdigit() and 1 <= int(rating) <= 5:
            statement = statement.filter(Feedback.rating == int(rating))
        rows = statement.order_by(Feedback.created_at.desc()).all()

    ratings = [f.rating for f in Feedback.query.filter(Feedback.event_id.in_(event_ids)).all()] if event_ids else []
    average = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    distribution = {str(i): 0 for i in range(1, 6)}
    for value in ratings:
        distribution[str(value)] += 1

    return render_template(
        "organizer/feedback.html",
        feedback_rows=rows,
        events=events,
        average=average,
        total=len(ratings),
        distribution=distribution,
        filters=filters,
        event_filter=event_filter,
        query_string=build_query_string,
    )


@organizer_bp.route("/feedback/<int:feedback_id>")
@organizer_required
def feedback_detail(feedback_id):
    row = db.get_or_404(Feedback, feedback_id)
    if row.event.organizer_id != current_user.id:
        flash("That feedback belongs to another organizer's event.", "danger")
        return redirect(url_for("organizer.feedback"))
    return render_template("organizer/feedback_detail.html", entry=row)


# ---------------------------------------------------------------------------
# Participants across all my events
# ---------------------------------------------------------------------------
@organizer_bp.route("/participants")
@organizer_required
def participants():
    event_ids = [e.id for e in domain.organizer_events(current_user.id)]
    rows = []
    if event_ids:
        rows = (
            Registration.query.filter(
                Registration.event_id.in_(event_ids), Registration.status == REG_CONFIRMED
            )
            .options(joinedload(Registration.student), joinedload(Registration.event))
            .order_by(Registration.registered_at.desc())
            .all()
        )
    return render_template("organizer/participants.html", registrations=rows)


@organizer_bp.route("/participants.csv")
@organizer_required
def participants_csv():
    from flask import Response

    event_ids = [e.id for e in domain.organizer_events(current_user.id)]
    rows = []
    if event_ids:
        rows = (
            Registration.query.filter(
                Registration.event_id.in_(event_ids), Registration.status == REG_CONFIRMED
            )
            .options(joinedload(Registration.student), joinedload(Registration.event))
            .order_by(Registration.registered_at.desc())
            .all()
        )

    lines = ["Registration ID,Student,Email,Department,Roll Number,Event,Event Date,Attendance"]
    for registration in rows:
        student = registration.student
        lines.append(
            ",".join(
                [
                    registration.registration_id,
                    _csv_cell(student.name if student else ""),
                    _csv_cell(student.email if student else ""),
                    _csv_cell(student.department if student else ""),
                    _csv_cell(student.roll_number if student else ""),
                    _csv_cell(registration.event.title),
                    registration.event.event_date.strftime("%Y-%m-%d"),
                    registration.attendance_status,
                ]
            )
        )
    return Response(
        "\n".join(lines),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=cems-participants.csv"},
    )


def _csv_cell(value):
    return f'"{str(value or "").replace(chr(34), chr(34) * 2)}"'


# ---------------------------------------------------------------------------
# Notices (Organizer is the publishing role)
# ---------------------------------------------------------------------------
@organizer_bp.route("/notices")
@organizer_required
def notices():
    filters = current_filters()
    statement = Notice.query
    if filters.get("scope") == "mine":
        statement = statement.filter_by(author_id=current_user.id)
    rows = statement.order_by(Notice.is_important.desc(), Notice.published_at.desc()).all()
    return render_template(
        "organizer/notices.html",
        notices=rows,
        audiences=AUDIENCES,
        filters=filters,
        my_id=current_user.id,
        query_string=build_query_string,
    )


@organizer_bp.route("/notices/create", methods=["GET", "POST"])
@organizer_required
def create_notice():
    form = {"audience": "ALL", "is_important": False}
    if request.method == "GET":
        return render_template("organizer/notice_form.html", notice=None, form=form, audiences=AUDIENCES)

    form = {
        "title": (request.form.get("title") or "").strip(),
        "description": (request.form.get("description") or "").strip(),
        "audience": (request.form.get("audience") or "ALL").strip().upper(),
        "is_important": bool(request.form.get("is_important")),
    }
    errors = []
    if len(form["title"]) < 5:
        errors.append("Notice title must be at least 5 characters long.")
    if len(form["description"]) < 10:
        errors.append("Notice description must be at least 10 characters long.")
    if form["audience"] not in AUDIENCES:
        errors.append("Please choose a valid audience.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return render_template("organizer/notice_form.html", notice=None, form=form, audiences=AUDIENCES), 400

    notice = Notice(
        title=form["title"],
        description=form["description"],
        author_id=current_user.id,
        audience=form["audience"],
        is_important=form["is_important"],
    )
    db.session.add(notice)
    db.session.commit()
    flash("Notice published successfully.", "success")
    return redirect(url_for("organizer.notices"))


@organizer_bp.route("/notices/<int:notice_id>/edit", methods=["GET", "POST"])
@organizer_required
def edit_notice(notice_id):
    notice = db.get_or_404(Notice, notice_id)
    if notice.author_id != current_user.id:
        flash("You can only edit notices that you published.", "danger")
        return redirect(url_for("organizer.notices"))

    if request.method == "GET":
        form = {
            "title": notice.title,
            "description": notice.description,
            "audience": notice.audience,
            "is_important": notice.is_important,
        }
        return render_template("organizer/notice_form.html", notice=notice, form=form, audiences=AUDIENCES)

    form = {
        "title": (request.form.get("title") or "").strip(),
        "description": (request.form.get("description") or "").strip(),
        "audience": (request.form.get("audience") or "ALL").strip().upper(),
        "is_important": bool(request.form.get("is_important")),
    }
    errors = []
    if len(form["title"]) < 5:
        errors.append("Notice title must be at least 5 characters long.")
    if len(form["description"]) < 10:
        errors.append("Notice description must be at least 10 characters long.")
    if form["audience"] not in AUDIENCES:
        errors.append("Please choose a valid audience.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return render_template("organizer/notice_form.html", notice=notice, form=form, audiences=AUDIENCES), 400

    notice.title = form["title"]
    notice.description = form["description"]
    notice.audience = form["audience"]
    notice.is_important = form["is_important"]
    db.session.commit()
    flash("Notice updated successfully.", "success")
    return redirect(url_for("organizer.notices"))


@organizer_bp.route("/notices/<int:notice_id>/delete", methods=["POST"])
@organizer_required
def delete_notice(notice_id):
    notice = db.get_or_404(Notice, notice_id)
    if notice.author_id != current_user.id:
        flash("You can only delete notices that you published.", "danger")
        return redirect(url_for("organizer.notices"))
    title = notice.title
    db.session.delete(notice)
    db.session.commit()
    flash(f'Notice "{title}" deleted.', "success")
    return redirect(url_for("organizer.notices"))


@organizer_bp.route("/notices/<int:notice_id>")
@organizer_required
def notice_detail(notice_id):
    notice = db.get_or_404(Notice, notice_id)
    return render_template("organizer/notice_detail.html", notice=notice)