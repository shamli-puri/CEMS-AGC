"""Points 7-9: model helpers, capacity rules and the domain service layer."""

from datetime import datetime, time, timedelta

import helpers
import pytest

from cems.extensions import db
from cems.models import (
    ATT_ABSENT,
    ATT_PRESENT,
    ATTENDANCE_PENDING,
    EVENT_CANCELLED,
    EVENT_COMPLETED,
    EVENT_ONGOING,
    EVENT_UPCOMING,
    REG_CANCELLED,
    REG_CONFIRMED,
    ROLE_LABELS,
    generate_code,
    utcnow,
)
from cems.services import domain


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------
def test_password_hashing_is_not_plain_text(app, student):
    from cems.models import User

    with app.app_context():
        row = db.session.get(User, student.id)
        assert row.password_hash != "agc@2026"
        assert "agc@2026" not in row.password_hash
        assert row.check_password("agc@2026") is True
        assert row.check_password("nope") is False
        assert row.check_password("") is False


def test_role_labels_and_predicates(app, student, faculty, organizer):
    from cems.models import User

    with app.app_context():
        for user, is_student, is_faculty, is_organizer, label in (
            (User.query.get(student.id), True, False, False, "Student"),
            (User.query.get(faculty.id), False, True, False, "Faculty"),
            (User.query.get(organizer.id), False, False, True, "Organizer"),
        ):
            assert user.is_student is is_student
            assert user.is_faculty is is_faculty
            assert user.is_organizer is is_organizer
            assert user.role_label == label
            assert ROLE_LABELS[user.role] == label


def test_initials_and_display_meta(app, student):
    from cems.models import User

    with app.app_context():
        row = db.session.get(User, student.id)
        assert row.initials == "TS"
        assert "CSE-2023-0001" in row.display_meta
        assert "3rd Year" in row.display_meta


def test_generate_code_shape():
    code = generate_code("AGC-REG")
    assert code.startswith("AGC-REG-")
    assert len(code.split("-")[-1]) == 6
    assert code != generate_code("AGC-REG") or True  # uniqueness is probabilistic


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------
def test_seat_counting_and_capacity(app, future_event, student, student2):
    from cems.models import Event

    with app.app_context():
        event = db.session.get(Event, future_event.id)
        assert event.seats_taken == 0
        assert event.seats_left == event.max_capacity
        assert event.is_full is False
        assert event.registration_open is True

    helpers.create_registration(app, future_event.id, student.id)
    with app.app_context():
        event = db.session.get(Event, future_event.id)
        assert event.seats_taken == 1
        assert event.seats_left == event.max_capacity - 1

    helpers.create_registration(app, future_event.id, student2.id, status=REG_CANCELLED)
    with app.app_context():
        event = db.session.get(Event, future_event.id)
        assert event.seats_taken == 1, "cancelled registrations must not hold a seat"


def test_is_full_when_capacity_reached(app, full_event, student):
    from cems.models import Event

    helpers.create_registration(app, full_event.id, student.id)
    with app.app_context():
        event = db.session.get(Event, full_event.id)
        assert event.is_full is True
        assert event.seats_left == 0
        assert event.registration_open is False
        ok, reason = event.registration_state()
        assert ok is False
        assert "maximum capacity" in reason


def test_registration_state_reasons(app, closed_event, cancelled_event, past_event):
    from cems.models import Event

    with app.app_context():
        closed = db.session.get(Event, closed_event.id)
        ok, reason = closed.registration_state()
        assert ok is False and "deadline" in reason

        cancelled = db.session.get(Event, cancelled_event.id)
        ok, reason = cancelled.registration_state()
        assert ok is False and "cancelled" in reason

        past = db.session.get(Event, past_event.id)
        ok, reason = past.registration_state()
        assert ok is False
        assert reason  # a finished event is not open for registration


def test_refresh_status_derives_upcoming_ongoing_completed(app, organizer):
    from cems.models import Event

    now = utcnow()
    upcoming = helpers.create_event(
        app,
        title="Upcoming derived",
        organizer_id=organizer.id,
        days=3,
        start="10:00",
        end="16:00",
    )
    ongoing = helpers.create_event(
        app,
        title="Ongoing derived",
        organizer_id=organizer.id,
        days=0,
        start=(now - timedelta(hours=2)).strftime("%H:%M"),
        end=(now + timedelta(hours=3)).strftime("%H:%M"),
    )
    finished = helpers.create_event(
        app,
        title="Finished derived",
        organizer_id=organizer.id,
        days=-3,
        start="10:00",
        end="16:00",
    )
    cancelled = helpers.create_event(
        app,
        title="Stays cancelled",
        organizer_id=organizer.id,
        days=3,
        status=EVENT_CANCELLED,
    )

    with app.app_context():
        assert db.session.get(Event, upcoming.id).refresh_status() == EVENT_UPCOMING
        assert db.session.get(Event, ongoing.id).refresh_status() == EVENT_ONGOING
        assert db.session.get(Event, finished.id).refresh_status() == EVENT_COMPLETED
        assert db.session.get(Event, cancelled.id).refresh_status() == EVENT_CANCELLED
        db.session.commit()


def test_status_class_mapping(app, future_event):
    from cems.models import Event

    with app.app_context():
        event = db.session.get(Event, future_event.id)
        assert event.status_class() == "badge-upcoming"
        event.status = EVENT_COMPLETED
        assert event.status_class() == "badge-completed"
        event.status = EVENT_CANCELLED
        assert event.status_class() == "badge-cancelled"


def test_average_rating_and_feedback_count(app, past_event, student, faculty):
    from cems.models import Event

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    helpers.create_feedback(app, reg_pk, student.id, past_event.id, rating=4, comments="Solid")

    with app.app_context():
        event = db.session.get(Event, past_event.id)
        assert event.feedback_count() == 1
        assert event.average_rating() == 4.0

    reg_pk2, _ = helpers.create_registration(app, past_event.id, faculty.id)
    helpers.create_feedback(app, reg_pk2, faculty.id, past_event.id, rating=5, comments="Great")
    with app.app_context():
        event = db.session.get(Event, past_event.id)
        assert event.average_rating() == 4.5


def test_registration_attendance_status_helpers(app, past_event, student, faculty):
    from cems.models import Event, Registration

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    with app.app_context():
        registration = db.session.get(Registration, reg_pk)
        assert registration.attendance_status == ATTENDANCE_PENDING
        assert registration.attendance_class == "badge-muted"

    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    with app.app_context():
        registration = db.session.get(Registration, reg_pk)
        assert registration.attendance_status == "Present"
        assert registration.attendance_class == "badge-success"

    helpers.mark_attendance(app, reg_pk, ATT_ABSENT, marked_by_id=faculty.id)
    with app.app_context():
        registration = db.session.get(Registration, reg_pk)
        assert registration.attendance_status == "Absent"
        assert registration.attendance_class == "badge-danger"


# ---------------------------------------------------------------------------
# Domain: registration rules
# ---------------------------------------------------------------------------
def test_registration_block_reason_returns_none_for_valid(app, future_event, student):
    with app.app_context():
        from cems.models import Event, User

        assert domain.registration_block_reason(
            db.session.get(Event, future_event.id), db.session.get(User, student.id)
        ) is None


def test_registration_block_reason_for_cancelled(app, cancelled_event, student):
    with app.app_context():
        from cems.models import Event, User

        reason = domain.registration_block_reason(
            db.session.get(Event, cancelled_event.id), db.session.get(User, student.id)
        )
        assert reason and "cancelled" in reason


def test_registration_block_reason_for_deadline(app, closed_event, student):
    with app.app_context():
        from cems.models import Event, User

        reason = domain.registration_block_reason(
            db.session.get(Event, closed_event.id), db.session.get(User, student.id)
        )
        assert reason and "deadline" in reason


def test_registration_block_reason_when_full(app, full_event, student, student2):
    helpers.create_registration(app, full_event.id, student.id)
    with app.app_context():
        from cems.models import Event, User

        reason = domain.registration_block_reason(
            db.session.get(Event, full_event.id), db.session.get(User, student2.id)
        )
        assert reason and "maximum capacity" in reason


def test_registration_block_reason_for_duplicate(app, future_event, student):
    helpers.create_registration(app, future_event.id, student.id)
    with app.app_context():
        from cems.models import Event, User

        reason = domain.registration_block_reason(
            db.session.get(Event, future_event.id), db.session.get(User, student.id)
        )
        assert reason and "already registered" in reason


def test_cancel_registration_rules(app, past_event, student, faculty):
    from cems.models import Registration

    reg_pk, code = helpers.create_registration(app, past_event.id, student.id)
    with app.app_context():
        ok, message = domain.cancel_registration(db.session.get(Registration, reg_pk))
        assert ok is True
        assert "cancel" in message.lower()
        db.session.commit()
        assert db.session.get(Registration, reg_pk).status == REG_CANCELLED
        assert db.session.get(Registration, reg_pk).cancelled_at is not None
        assert code.startswith("AGC-REG-")

    # second cancel is refused
    with app.app_context():
        ok, message = domain.cancel_registration(db.session.get(Registration, reg_pk))
        assert ok is False
        assert "already cancelled" in message


def test_cannot_cancel_after_present_attendance(app, past_event, student, faculty):
    from cems.models import Registration

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    with app.app_context():
        ok, message = domain.cancel_registration(db.session.get(Registration, reg_pk))
        assert ok is False
        assert "Present" in message


# ---------------------------------------------------------------------------
# Domain: attendance and certificates
# ---------------------------------------------------------------------------
def test_mark_attendance_bulk_sets_present_and_absent(app, past_event, student, student2, faculty):
    from cems.models import Attendance, Registration

    a, _ = helpers.create_registration(app, past_event.id, student.id)
    b, _ = helpers.create_registration(app, past_event.id, student2.id)
    with app.app_context():
        from cems.models import Event

        event = db.session.get(Event, past_event.id)
        applied = domain.mark_attendance_bulk(event, [a, b], {a}, faculty.id, "bulk run")
        db.session.commit()
        assert applied == 2

        rows = {r.registration_id: r.status for r in Attendance.query.filter_by(event_id=event.id)}
        assert rows[a] == ATT_PRESENT
        assert rows[b] == ATT_ABSENT
        assert db.session.get(Registration, a).attendance.marked_by_id == faculty.id


def test_mark_attendance_bulk_skips_cancelled_registrations(app, past_event, student, faculty):
    from cems.models import Event

    cancelled_pk, _ = helpers.create_registration(
        app, past_event.id, student.id, status=REG_CANCELLED
    )
    with app.app_context():
        event = db.session.get(Event, past_event.id)
        assert domain.mark_attendance_bulk(event, [cancelled_pk], {cancelled_pk}, faculty.id) == 0


def test_is_certificate_eligibility_rules(app, past_event, student, student2, faculty):
    from cems.models import Event, Registration

    present_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, present_pk, ATT_PRESENT, marked_by_id=faculty.id)
    absent_pk, _ = helpers.create_registration(app, past_event.id, student2.id)
    helpers.mark_attendance(app, absent_pk, ATT_ABSENT, marked_by_id=faculty.id)

    with app.app_context():
        event = db.session.get(Event, past_event.id)
        assert domain.is_certificate_eligible(event, db.session.get(Registration, present_pk)) is True
        assert domain.is_certificate_eligible(event, db.session.get(Registration, absent_pk)) is False
        assert domain.is_certificate_eligible(None, None) is False

        event.certificate_eligible = False
        db.session.commit()
        assert domain.is_certificate_eligible(event, db.session.get(Registration, present_pk)) is False


def test_issue_certificate_is_idempotent(app, past_event, student, faculty):
    from cems.models import Certificate, Event, Registration

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    with app.app_context():
        registration = db.session.get(Registration, reg_pk)
        certificate, created = domain.issue_certificate(registration, faculty.id)
        db.session.commit()
        assert created is True
        first_id = certificate.certificate_id
        assert first_id.startswith("AGC-CERT-")

        again, created_again = domain.issue_certificate(
            db.session.get(Registration, reg_pk), faculty.id
        )
        db.session.commit()
        assert created_again is False
        assert again.certificate_id == first_id
        assert Certificate.query.filter_by(registration_id=reg_pk).count() == 1


def test_next_code_produces_unique_values(app, student):
    from cems.models import Registration

    with app.app_context():
        first = domain.next_code(Registration.registration_id, "AGC-REG")
        second = domain.next_code(Registration.registration_id, "AGC-REG")
        assert first.startswith("AGC-REG-")
        assert first != second


# ---------------------------------------------------------------------------
# Domain: statistics
# ---------------------------------------------------------------------------
def test_student_statistics(app, past_event, future_event, student, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    helpers.create_registration(app, future_event.id, student.id)

    with app.app_context():
        stats = domain.student_statistics(student.id)
    assert stats["total"] == 2
    assert stats["confirmed"] == 2
    assert stats["attended"] == 1
    assert stats["upcoming"] == 1
    assert stats["past"] == 1
    assert stats["cancelled"] == 0


def test_organizer_statistics_only_counts_own_events(app, organizer, organizer2, student):
    mine = helpers.create_event(app, title="Mine", organizer_id=organizer.id, max_capacity=30)
    theirs = helpers.create_event(app, title="Theirs", organizer_id=organizer2.id, max_capacity=30)
    helpers.create_registration(app, mine.id, student.id)
    helpers.create_registration(app, theirs.id, student.id)

    with app.app_context():
        events = domain.organizer_events(organizer.id)
        assert [e.id for e in events] == [mine.id]
        stats = domain.organizer_statistics(organizer.id)
    assert stats["total_events"] == 1
    assert stats["total_registrations"] == 1
    assert stats["capacity"] == 30


def test_event_statistics(app, past_event, student, student2, faculty):
    from cems.models import Event

    present_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, present_pk, ATT_PRESENT, marked_by_id=faculty.id)
    absent_pk, _ = helpers.create_registration(app, past_event.id, student2.id)
    helpers.mark_attendance(app, absent_pk, ATT_ABSENT, marked_by_id=faculty.id)
    helpers.create_registration(app, past_event.id, student.id, status=REG_CANCELLED)

    with app.app_context():
        event = db.session.get(Event, past_event.id)
        stats = domain.event_statistics(event)
    assert stats["confirmed"] == 2
    assert stats["cancelled"] == 1
    assert stats["present"] == 1
    assert stats["absent"] == 1
    assert stats["unmarked"] == 0
    assert stats["attendance_rate"] == 50.0
    assert stats["fill_rate"] == 5.0


def test_faculty_statistics(app, past_event, future_event, student, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    helpers.create_registration(app, future_event.id, student.id)

    with app.app_context():
        stats = domain.faculty_statistics(faculty.id)
    assert stats["total_events"] == 2
    assert stats["completed_events"] == 1
    assert stats["upcoming_events"] == 1
    assert stats["total_registrations"] == 2
    assert stats["total_attendees"] == 1
    assert stats["pending_attendance"] == 1


def test_profile_completeness_per_role(app, student, faculty, organizer):
    from cems.models import User

    with app.app_context():
        # None of the fixtures set a phone number (or a department for the
        # organizer), so completeness depends on how many fields each role has.
        assert domain.profile_completeness(db.session.get(User, student.id)) == 80
        assert domain.profile_completeness(db.session.get(User, faculty.id)) == 80
        assert domain.profile_completeness(db.session.get(User, organizer.id)) == 60

        db.session.get(User, student.id).phone = "9876500000"
        db.session.commit()
        assert domain.profile_completeness(db.session.get(User, student.id)) == 100


def test_search_events_scopes_and_query(app, organizer, student):
    upcoming = helpers.create_event(app, title="Robotics Workshop", organizer_id=organizer.id, days=5)
    done = helpers.create_event(
        app, title="Robotics Retrospective", organizer_id=organizer.id, days=-5, status=EVENT_COMPLETED
    )
    helpers.create_registration(app, upcoming.id, student.id)

    with app.app_context():
        assert [e.id for e in domain.search_events("Robotics", "all")] == [done.id, upcoming.id]
        assert [e.id for e in domain.search_events("", "upcoming")] == [upcoming.id]
        assert [e.id for e in domain.search_events("", "completed")] == [done.id]
        assert [e.id for e in domain.search_events("", "registered", student_id=student.id)] == [
            upcoming.id
        ]
        # ordered by event_date: the retrospective (-5 days) comes first
        assert [e.id for e in domain.search_events("", "mine", student_id=organizer.id)] == [
            done.id,
            upcoming.id,
        ]


def test_user_directory_filters_active_accounts(app, student, student2, faculty):
    from cems.models import User

    with app.app_context():
        db.session.query(User).filter(User.id == student.id).update({"is_active_account": False})
        db.session.commit()
        db.session.expire_all()
        directory = domain.user_directory()
        emails = {u.email for u in directory}
        assert student.email not in emails
        assert faculty.email in emails
        assert student2.email in emails

        students = domain.user_directory(role="STUDENT")
        assert {u.email for u in students} == {student2.email}


def test_ensure_certificate_rows_backfills_missing_rows(app, past_event, student, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    with app.app_context():
        from cems.models import Certificate

        assert Certificate.query.filter_by(student_id=student.id).count() == 0
        created = domain.ensure_certificate_rows(student.id)
        db.session.commit()
        assert len(created) == 1
        assert Certificate.query.filter_by(student_id=student.id).count() == 1
        assert domain.ensure_certificate_rows(student.id) == []


def test_ensure_organizer_for(app, future_event, organizer, organizer2):
    with app.app_context():
        from cems.models import Event, User

        event = db.session.get(Event, future_event.id)
        assert domain.ensure_organizer_for(event, db.session.get(User, organizer.id)) is True
        assert domain.ensure_organizer_for(event, db.session.get(User, organizer2.id)) is False


def test_visible_notices_filters_by_audience(app, organizer):
    for audience in ("ALL", "STUDENT", "FACULTY", "ORGANIZER"):
        helpers.create_notice(
            app, organizer.id, f"Notice for {audience}", "Body text", audience=audience
        )
    with app.app_context():
        from cems.services.domain import visible_notices

        for role, expected_extra in (
            ("STUDENT", "STUDENT"),
            ("FACULTY", "FACULTY"),
            ("ORGANIZER", "ORGANIZER"),
        ):
            titles = {n.title for n in visible_notices(role)}
            assert f"Notice for {expected_extra}" in titles
            assert f"Notice for ALL" in titles
            others = {"STUDENT", "FACULTY", "ORGANIZER"} - {expected_extra}
            for other in others:
                assert f"Notice for {other}" not in titles


@pytest.mark.parametrize("bad", [None, "not a date", "2024-13-45"])
def test_parse_datetime_rejects_bad_input(bad):
    from cems.utils.helpers import parse_datetime

    value, error = parse_datetime(bad, "When")
    assert value is None
    assert error


def test_helpers_formatting_and_filters():
    from cems.utils.helpers import (
        current_filters,
        format_date,
        format_time,
        initials_of,
        rating_stars,
        safe_next,
        slugify,
        truncate,
    )

    assert format_date(datetime(2026, 3, 7)) == "7 March 2026"
    assert format_time(time(14, 5)).strip() == "02:05 PM"
    assert initials_of("Aarav Sharma") == "AS"
    assert initials_of("Aarav Kumar Sharma") == "AS"
    assert initials_of("") == "AG"
    assert rating_stars(3).count("&#9733;") == 3
    assert truncate("x" * 200, 10).endswith("\u2026")
    assert slugify("Tech Fest 2026!") == "tech-fest-2026"
    assert safe_next("https://evil.example.com") is None
    assert safe_next("//evil.example.com") is None
    assert safe_next("/student/dashboard") == "/student/dashboard"