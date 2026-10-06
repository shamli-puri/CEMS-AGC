"""Domain services for CEMS.

Thin, testable helpers that keep route handlers small:
registration rules, certificate issuing, event statistics.
"""

from datetime import datetime

from sqlalchemy import func

from ..extensions import db
from ..models import (
    ATT_PRESENT,
    AUDIENCE_ALL,
    EVENT_CANCELLED,
    EVENT_ONGOING,
    EVENT_UPCOMING,
    REG_CANCELLED,
    REG_CONFIRMED,
    Registration,
    User,
    utcnow,
)


def registration_block_reason(event, student):
    """Return an error string when *student* may not register for *event*."""
    if event is None or student is None:
        return "Invalid registration request."
    if event.status == EVENT_CANCELLED:
        return "This event has been cancelled. Registration is closed."
    if event.registration_deadline and event.registration_deadline < utcnow():
        return "The registration deadline for this event has passed."
    if event.seats_taken >= event.max_capacity:
        return "This event has reached its maximum capacity of "
        f"{event.max_capacity} participants."
    existing = Registration.query.filter_by(
        student_id=student.id, event_id=event.id, status=REG_CONFIRMED
    ).first()
    if existing:
        return f"You are already registered for this event ({existing.registration_id})."
    if student.is_student and event.status in (EVENT_UPCOMING, EVENT_ONGOING) and event.end_datetime < utcnow():
        return "This event has already taken place."
    return None


def cancel_registration(registration):
    """Cancel a confirmed registration. Returns (ok, message)."""
    if registration is None:
        return False, "Registration not found."
    if registration.is_cancelled:
        return False, "This registration is already cancelled."
    if registration.attendance and registration.attendance.status == ATT_PRESENT:
        return False, "Attendance was already marked Present, so this registration can no longer be cancelled."
    registration.status = REG_CANCELLED
    registration.cancelled_at = utcnow()
    if registration.attendance:
        db.session.delete(registration.attendance)
        registration.attendance = None
    db.session.flush()
    return True, "Registration cancelled successfully."


def is_certificate_eligible(event, registration):
    """A certificate is issued for a confirmed + present registration."""
    if event is None or registration is None:
        return False
    if not event.certificate_eligible:
        return False
    if not registration.is_confirmed:
        return False
    attendance = registration.attendance
    return bool(attendance and attendance.status == ATT_PRESENT)


def next_code(column, prefix, table=Registration):
    """Generate a guaranteed-unique human readable code."""
    from ..models import generate_code

    for _ in range(40):
        candidate = generate_code(prefix)
        exists = db.session.query(
            func.count(table.id)
        ).filter(column == candidate).scalar()
        if not exists:
            return candidate
    raise RuntimeError("Unable to generate a unique code")


def student_statistics(student_id):
    """Aggregate numbers used by the student dashboard."""
    registrations = Registration.query.filter_by(student_id=student_id).all()
    confirmed = [r for r in registrations if r.is_confirmed]
    present = [r for r in confirmed if r.attendance and r.attendance.status == ATT_PRESENT]
    upcoming = [
        r
        for r in confirmed
        if r.event.status != EVENT_CANCELLED and r.event.end_datetime >= utcnow()
    ]
    past = [r for r in confirmed if r.event.status == EVENT_CANCELLED or r.event.end_datetime < utcnow()]

    from ..models import Certificate, Feedback

    certificates = Certificate.query.filter_by(student_id=student_id).count()
    feedback_count = Feedback.query.filter_by(student_id=student_id).count()

    return {
        "total": len(registrations),
        "confirmed": len(confirmed),
        "cancelled": len(registrations) - len(confirmed),
        "upcoming": len(upcoming),
        "attended": len(present),
        "past": len(past),
        "certificates": certificates,
        "feedback": feedback_count,
        "registrations": registrations,
        "confirmed_registrations": confirmed,
        "upcoming_registrations": upcoming,
        "attended_registrations": present,
        "certificate_registrations": [r for r in present if is_certificate_eligible(r.event, r)],
    }


def organizer_events(organizer_id):
    from ..models import Event

    events = (
        Event.query.filter_by(organizer_id=organizer_id)
        .order_by(Event.event_date.asc(), Event.start_time.asc())
        .all()
    )
    for event in events:
        event.refresh_status()
    return events


def organizer_statistics(organizer_id):
    events = organizer_events(organizer_id)
    event_ids = [e.id for e in events]
    stats = {
        "total_events": len(events),
        "upcoming_events": len([e for e in events if e.status == EVENT_UPCOMING]),
        "ongoing_events": len([e for e in events if e.status == EVENT_ONGOING]),
        "completed_events": len([e for e in events if e.status == "COMPLETED"]),
        "cancelled_events": len([e for e in events if e.status == EVENT_CANCELLED]),
        "total_registrations": 0,
        "total_attendees": 0,
        "average_rating": 0.0,
        "capacity": sum(e.max_capacity for e in events),
        "events": events,
    }
    if not event_ids:
        return stats

    registrations = Registration.query.filter(
        Registration.event_id.in_(event_ids), Registration.status == REG_CONFIRMED
    ).all()
    stats["total_registrations"] = len(registrations)
    stats["total_attendees"] = len([r for r in registrations if r.attendance and r.attendance.status == ATT_PRESENT])

    from ..models import Feedback

    ratings = [
        f.rating
        for f in Feedback.query.filter(Feedback.event_id.in_(event_ids)).all()
        if f.rating
    ]
    if ratings:
        stats["average_rating"] = round(sum(ratings) / len(ratings), 2)
    return stats


def event_statistics(event):
    registrations = event.registrations
    confirmed = [r for r in registrations if r.is_confirmed]
    present = [r for r in confirmed if r.attendance and r.attendance.status == ATT_PRESENT]
    absent = [r for r in confirmed if r.attendance and r.attendance.status == "ABSENT"]
    unmarked = [r for r in confirmed if not r.attendance]
    cancelled = [r for r in registrations if r.is_cancelled]
    ratings = [f.rating for f in event.feedback_entries if f.rating]
    return {
        "confirmed": len(confirmed),
        "cancelled": len(cancelled),
        "present": len(present),
        "absent": len(absent),
        "unmarked": len(unmarked),
        "capacity": event.max_capacity,
        "fill_rate": round((len(confirmed) / event.max_capacity) * 100, 1) if event.max_capacity else 0.0,
        "attendance_rate": round((len(present) / len(confirmed)) * 100, 1) if confirmed else 0.0,
        "feedback_count": len(event.feedback_entries),
        "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
    }


def faculty_statistics(faculty_id=None):
    from ..models import Event

    events = Event.query.order_by(Event.event_date.desc()).all()
    for event in events:
        event.refresh_status()
    upcoming = [e for e in events if e.status in (EVENT_UPCOMING, EVENT_ONGOING)]
    relevant_ids = [e.id for e in events]

    registrations = []
    if relevant_ids:
        registrations = (
            Registration.query.filter(
                Registration.event_id.in_(relevant_ids), Registration.status == REG_CONFIRMED
            ).all()
        )
    present = [r for r in registrations if r.attendance and r.attendance.status == ATT_PRESENT]
    unmarked = [r for r in registrations if not r.attendance]
    return {
        "total_events": len(events),
        "upcoming_events": len(upcoming),
        "completed_events": len([e for e in events if e.status == "COMPLETED"]),
        "total_registrations": len(registrations),
        "total_attendees": len(present),
        "pending_attendance": len(unmarked),
        "events": events,
        "upcoming": upcoming,
    }


def visible_notices(role, limit=None):
    from ..models import Notice

    query = Notice.query.filter(
        (Notice.audience == AUDIENCE_ALL) | (Notice.audience == role)
    ).order_by(Notice.is_important.desc(), Notice.published_at.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def _actor_id(actor):
    """Accept either a User instance or a raw user id."""
    if actor is None:
        return None
    return getattr(actor, "id", actor)


def mark_attendance_bulk(event, registration_ids, present_ids, marked_by, remarks=None):
    """Create/update Attendance rows for the given registrations."""
    from ..models import Attendance

    actor_id = _actor_id(marked_by)
    applied = 0
    for reg_id in registration_ids:
        registration = (
            Registration.query.filter_by(id=reg_id, event_id=event.id).first()
        )
        if registration is None or not registration.is_confirmed:
            continue
        status = ATT_PRESENT if reg_id in present_ids else "ABSENT"
        record = Attendance.query.filter_by(registration_id=registration.id).first()
        if record is None:
            record = Attendance(
                registration_id=registration.id,
                student_id=registration.student_id,
                event_id=event.id,
                status=status,
                marked_by_id=actor_id,
                remarks=remarks,
            )
            db.session.add(record)
        else:
            record.status = status
            record.marked_at = utcnow()
            record.marked_by_id = actor_id
            if remarks:
                record.remarks = remarks
        registration.attendance = record
        applied += 1
    db.session.flush()
    return applied


def issue_certificate(registration, issued_by):
    """Idempotently issue a certificate for an eligible registration."""
    from ..models import Certificate

    existing = Certificate.query.filter_by(registration_id=registration.id).first()
    if existing:
        return existing, False
    code = next_code(Certificate.certificate_id, "AGC-CERT", table=Certificate)
    certificate = Certificate(
        certificate_id=code,
        student_id=registration.student_id,
        event_id=registration.event_id,
        registration_id=registration.id,
        issued_by_id=_actor_id(issued_by),
    )
    db.session.add(certificate)
    db.session.flush()
    return certificate, True


def profile_completeness(user):
    fields = [user.name, user.phone, user.department]
    if user.is_student:
        fields += [user.roll_number, user.year_of_study]
    elif user.is_faculty:
        fields += [user.employee_id, user.designation]
    else:
        fields += [user.organization, user.designation]
    filled = len([f for f in fields if f])
    return int((filled / len(fields)) * 100)


def ensure_organizer_for(event, user):
    return event.organizer_id == user.id


def search_events(query, scope="all", student_id=None):
    """Shared event search used by all three dashboards."""
    from ..models import Event

    q = (query or "").strip()
    scope = (scope or "all").lower()
    statement = Event.query
    if scope == "upcoming":
        statement = statement.filter(Event.status == EVENT_UPCOMING)
    elif scope == "completed":
        statement = statement.filter(Event.status == "COMPLETED")
    elif scope == "cancelled":
        statement = statement.filter(Event.status == EVENT_CANCELLED)
    elif scope == "registered" and student_id:
        statement = statement.join(Registration).filter(
            Registration.student_id == student_id, Registration.status == REG_CONFIRMED
        )
    elif scope == "mine" and student_id:
        statement = statement.filter(Event.organizer_id == student_id)
    if q:
        like = f"%{q}%"
        statement = statement.filter(
            db.or_(Event.title.ilike(like), Event.description.ilike(like), Event.venue.ilike(like))
        )
    events = statement.order_by(Event.event_date.asc(), Event.start_time.asc()).all()
    for event in events:
        event.refresh_status()
    return events


def ensure_certificate_rows(user_id):
    """Create any missing certificates for attended events of a student."""
    from ..models import Certificate, Event

    registrations = (
        Registration.query.filter_by(student_id=user_id, status=REG_CONFIRMED)
        .join(Event)
        .filter(Event.status == "COMPLETED")
        .all()
    )
    created = []
    for registration in registrations:
        if is_certificate_eligible(registration.event, registration):
            has_existing = Certificate.query.filter_by(registration_id=registration.id).first()
            if has_existing:
                continue
            issued_by = registration.event.organizer
            code = next_code(Certificate.certificate_id, "AGC-CERT", table=Certificate)
            certificate = Certificate(
                certificate_id=code,
                student_id=user_id,
                event_id=registration.event_id,
                registration_id=registration.id,
                issued_by_id=_actor_id(issued_by) or user_id,
            )
            db.session.add(certificate)
            created.append(certificate)
    if created:
        db.session.flush()
    return created


def user_directory(role=None):
    query = User.query.filter_by(is_active_account=True)
    if role:
        query = query.filter_by(role=role)
    return query.order_by(User.name.asc()).all()


def parse_iso(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None