"""Test helpers that always open their own short-lived application context.

Returned values are plain Python objects (or fully loaded detached rows) because
the testing session uses ``expire_on_commit=False``.
"""

from datetime import datetime, time, timedelta

from cems.extensions import db
from cems.models import (
    ATT_PRESENT,
    REG_CONFIRMED,
    Event,
    Registration,
    User,
    utcnow,
)

PASSWORD = "agc@2026"


class Record(dict):
    """Dict that also exposes its keys as attributes, for readable assertions."""

    __getattr__ = dict.__getitem__


def _parse_time(value, default):
    if not value:
        return default
    for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Unsupported time value: {value!r}")


def create_user(app, role, email, name, password=PASSWORD, **extra):
    """Create a user and return a plain record of its identity."""
    with app.app_context():
        user = User(name=name, email=email, role=role, **extra)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return Record(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            **{k: v for k, v in extra.items()},
        )


def create_event(
    app,
    title,
    description="An event created by the CEMS automated tests.",
    category="Technical",
    days=10,
    start="10:00",
    end="16:00",
    venue="AGC Campus",
    organizer_id=None,
    max_capacity=50,
    deadline_days=-1,
    deadline=None,
    status="UPCOMING",
    certificate_eligible=True,
):
    """Create an event relative to the current date and return a plain record.

    ``deadline_days`` is relative to the event date; pass ``deadline`` for an
    absolute registration deadline.
    """
    base = datetime.utcnow() + timedelta(days=days)
    with app.app_context():
        event = Event(
            title=title,
            description=description,
            category=category,
            event_date=base.date(),
            start_time=_parse_time(start, time(10, 0)),
            end_time=_parse_time(end, time(16, 0)),
            venue=venue,
            organizer_id=organizer_id,
            max_capacity=max_capacity,
            registration_deadline=deadline or (base + timedelta(days=deadline_days)),
            status=status,
            certificate_eligible=certificate_eligible,
        )
        db.session.add(event)
        db.session.commit()
        return Record(
            id=event.id,
            title=event.title,
            description=event.description,
            category=event.category,
            event_date=event.event_date,
            start_time=event.start_time,
            end_time=event.end_time,
            venue=event.venue,
            organizer_id=event.organizer_id,
            max_capacity=event.max_capacity,
            registration_deadline=event.registration_deadline,
            status=event.status,
            certificate_eligible=event.certificate_eligible,
        )


def create_registration(app, event_id, student_id, status=REG_CONFIRMED, code=None):
    """Create a registration and return ``(pk, registration_id)``."""
    with app.app_context():
        registration = Registration(
            registration_id=code
            or f"AGC-REG-E{event_id}S{student_id}-{_next_registration_sequence():03d}",
            student_id=student_id,
            event_id=event_id,
            status=status,
            registered_at=utcnow(),
        )
        db.session.add(registration)
        db.session.commit()
        return registration.id, registration.registration_id


def _next_registration_sequence():
    global _REG_SEQUENCE
    _REG_SEQUENCE += 1
    return _REG_SEQUENCE


_REG_SEQUENCE = 0


def mark_attendance(app, registration_pk, status=ATT_PRESENT, marked_by_id=1):
    """Create or update the attendance row for a registration."""
    from cems.models import Attendance

    with app.app_context():
        registration = db.session.get(Registration, registration_pk)
        assert registration is not None
        record = Attendance.query.filter_by(registration_id=registration_pk).first()
        if record is None:
            record = Attendance(
                registration_id=registration_pk,
                student_id=registration.student_id,
                event_id=registration.event_id,
                status=status,
                marked_by_id=marked_by_id,
                marked_at=utcnow(),
            )
            db.session.add(record)
        else:
            record.status = status
            record.marked_by_id = marked_by_id
            record.marked_at = utcnow()
        db.session.commit()
        return record.id


def create_notice(app, author_id, title, description, audience="ALL", important=False):
    with app.app_context():
        from cems.models import Notice

        notice = Notice(
            title=title,
            description=description,
            author_id=author_id,
            audience=audience,
            is_important=important,
            published_at=utcnow(),
        )
        db.session.add(notice)
        db.session.commit()
        return Record(id=notice.id, title=notice.title, audience=notice.audience)


def create_feedback(app, registration_pk, student_id, event_id, rating=5, comments="Great event."):
    with app.app_context():
        from cems.models import Feedback

        entry = Feedback(
            student_id=student_id,
            event_id=event_id,
            registration_id=registration_pk,
            rating=rating,
            comments=comments,
            created_at=utcnow(),
        )
        db.session.add(entry)
        db.session.commit()
        return Record(id=entry.id, rating=entry.rating, comments=entry.comments)


def login_as(client, user, password=PASSWORD):
    """Log a user in through their own role login page."""
    return client.post(
        f"/auth/login/{user.role.lower()}", data={"email": user.email, "password": password}
    )


def logout(client):
    return client.post("/auth/logout", follow_redirects=True)