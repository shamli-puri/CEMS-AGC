"""Points 18-22: the organizer module - event CRUD, ownership, attendance,
certificates, notices, statistics and CSV export."""

from datetime import timedelta

import helpers
import pytest

from cems.extensions import db
from cems.models import ATT_ABSENT, ATT_PRESENT, EVENT_CANCELLED, REG_CANCELLED, utcnow


@pytest.fixture()
def as_organizer(app, organizer):
    client = app.test_client()
    helpers.login_as(client, organizer)
    return client


def event_payload(**overrides):
    from datetime import datetime

    base = datetime.utcnow() + timedelta(days=20)
    payload = {
        "title": "AGC Innovation Expo",
        "description": "A two day showcase of student projects across every department.",
        "category": "Technical",
        "event_date": base.strftime("%Y-%m-%d"),
        "start_time": "10:00",
        "end_time": "16:00",
        "venue": "Innovation Lab, AGC Campus",
        "max_capacity": "120",
        "registration_deadline": (base - timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
        "certificate_eligible": "1",
    }
    payload.update(overrides)
    return payload


def created_event_id(app):
    from cems.models import Event

    with app.app_context():
        row = Event.query.filter_by(title="AGC Innovation Expo").first()
        return row.id if row else None


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
def test_organizer_dashboard_and_alias(app, as_organizer, organizer, future_event):
    response = as_organizer.get("/organizer/dashboard")
    assert response.status_code == 200
    assert organizer.name.encode() in response.data
    assert as_organizer.get("/organizer/").status_code == 200


def test_organizer_event_listing(app, as_organizer, future_event, past_event):
    assert as_organizer.get("/organizer/events").status_code == 200
    assert as_organizer.get("/organizer/events?status=UPCOMING").status_code == 200
    assert as_organizer.get("/organizer/events?category=Technical").status_code == 200
    assert as_organizer.get("/organizer/events?q=Tech+Fest").status_code == 200


def test_organizer_only_sees_their_own_events(app, as_organizer, organizer2, organizer):
    helpers.create_event(app, title="Foreign Event", organizer_id=organizer2.id)
    helpers.create_event(app, title="Own Event", organizer_id=organizer.id)
    response = as_organizer.get("/organizer/events")
    assert b"Own Event" in response.data
    assert b"Foreign Event" not in response.data


# ---------------------------------------------------------------------------
# Event CRUD
# ---------------------------------------------------------------------------
def test_organizer_creates_an_event(app, as_organizer):
    response = as_organizer.post("/organizer/events/create", data=event_payload(), follow_redirects=True)
    assert b"created successfully" in response.data
    event_id = created_event_id(app)
    assert event_id

    from cems.models import Event, Notice

    with app.app_context():
        event = db.session.get(Event, event_id)
        assert event.status == "UPCOMING"
        assert event.max_capacity == 120
        assert event.certificate_eligible is True
        # creating an event publishes a notice for everyone
        assert Notice.query.filter_by(title="New event: AGC Innovation Expo").first() is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "abc"},
        {"description": "too short"},
        {"category": "NotACategory"},
        {"venue": ""},
        {"event_date": "not-a-date"},
        {"start_time": "99:99"},
        {"start_time": "16:00", "end_time": "10:00"},
        {"max_capacity": "0"},
        {"max_capacity": "abc"},
        {"registration_deadline": "nope"},
    ],
)
def test_invalid_event_form_returns_400(app, as_organizer, overrides):
    response = as_organizer.post(
        "/organizer/events/create", data=event_payload(**overrides)
    )
    assert response.status_code == 400


def test_organizer_edits_an_event(app, as_organizer):
    as_organizer.post(
        "/organizer/events/create", data=event_payload(), follow_redirects=True
    )
    event_id = created_event_id(app)
    assert event_id

    get_page = as_organizer.get(f"/organizer/events/{event_id}/edit")
    assert get_page.status_code == 200

    response = as_organizer.post(
        f"/organizer/events/{event_id}/edit",
        data=event_payload(title="AGC Innovation Expo 2026"),
        follow_redirects=True,
    )
    assert b"has been updated" in response.data

    from cems.models import Event

    with app.app_context():
        assert db.session.get(Event, event_id).title == "AGC Innovation Expo 2026"


def test_capacity_cannot_be_lowered_below_confirmed_registrations(
    app, as_organizer, organizer, future_event, student, student2
):
    helpers.create_registration(app, future_event.id, student.id)
    helpers.create_registration(app, future_event.id, student2.id)
    response = as_organizer.post(
        f"/organizer/events/{future_event.id}/edit",
        data=event_payload(
            title=future_event.title,
            event_date=future_event.event_date.strftime("%Y-%m-%d"),
            registration_deadline=future_event.registration_deadline.strftime("%Y-%m-%d %H:%M"),
            max_capacity="1",
        ),
    )
    assert response.status_code == 400
    assert b"Capacity cannot be below" in response.data


def test_organizer_cancels_an_event_and_releases_registrations(
    app, as_organizer, organizer, future_event, student
):
    reg_pk, _ = helpers.create_registration(app, future_event.id, student.id)
    response = as_organizer.post(
        f"/organizer/events/{future_event.id}/cancel", follow_redirects=True
    )
    assert b"has been cancelled" in response.data

    from cems.models import Event, Registration

    with app.app_context():
        assert db.session.get(Event, future_event.id).status == EVENT_CANCELLED
        assert db.session.get(Registration, reg_pk).status == REG_CANCELLED


def test_cancelling_twice_is_reported(app, as_organizer, cancelled_event):
    response = as_organizer.post(
        f"/organizer/events/{cancelled_event.id}/cancel", follow_redirects=True
    )
    assert b"already cancelled" in response.data


def test_restore_requires_a_cancelled_event(app, as_organizer, future_event):
    response = as_organizer.post(
        f"/organizer/events/{future_event.id}/restore", follow_redirects=True
    )
    assert b"Only cancelled events" in response.data


def test_organizer_restores_a_cancelled_event(app, as_organizer, cancelled_event):
    response = as_organizer.post(
        f"/organizer/events/{cancelled_event.id}/restore", follow_redirects=True
    )
    assert b"has been restored" in response.data


def test_restore_is_refused_after_the_deadline(app, as_organizer, organizer):
    from datetime import datetime, time

    stale = helpers.create_event(
        app,
        title="Stale cancelled event",
        organizer_id=organizer.id,
        days=10,
        start="10:00",
        end="16:00",
        deadline=utcnow() - timedelta(days=2),
        status=EVENT_CANCELLED,
    )
    response = as_organizer.post(f"/organizer/events/{stale.id}/restore", follow_redirects=True)
    assert b"cannot be restored" in response.data


def test_organizer_deletes_an_event(app, as_organizer, future_event):
    from cems.models import Event

    event_id = future_event.id
    response = as_organizer.post(f"/organizer/events/{event_id}/delete", follow_redirects=True)
    assert b"permanently deleted" in response.data
    with app.app_context():
        assert db.session.get(Event, event_id) is None


# ---------------------------------------------------------------------------
# Ownership guard
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "action", ["edit", "cancel", "restore", "delete", "registrations", "attendees", "attendance"]
)
def test_organizer_cannot_touch_another_organizers_event(app, as_organizer, organizer2, action):
    foreign = helpers.create_event(app, title="Foreign", organizer_id=organizer2.id)
    if action == "edit":
        response = as_organizer.get(f"/organizer/events/{foreign.id}/edit", follow_redirects=True)
    elif action == "restore":
        response = as_organizer.post(
            f"/organizer/events/{foreign.id}/restore", follow_redirects=True
        )
    elif action == "registrations":
        response = as_organizer.get(
            f"/organizer/events/{foreign.id}/registrations", follow_redirects=True
        )
    elif action == "attendees":
        response = as_organizer.get(f"/organizer/events/{foreign.id}/attendees", follow_redirects=True)
    elif action == "attendance":
        response = as_organizer.get(
            f"/organizer/events/{foreign.id}/attendance", follow_redirects=True
        )
    else:
        response = as_organizer.post(f"/organizer/events/{foreign.id}/{action}", follow_redirects=True)
    assert b"only manage events that you organize" in response.data


def test_foreign_event_survives_the_ownership_guard(app, as_organizer, organizer2):
    from cems.models import Event

    foreign = helpers.create_event(app, title="Foreign", organizer_id=organizer2.id)
    as_organizer.post(f"/organizer/events/{foreign.id}/delete", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Event, foreign.id) is not None


# ---------------------------------------------------------------------------
# Registration management
# ---------------------------------------------------------------------------
def test_organizer_cancels_and_restores_a_registration(app, as_organizer, future_event, student):
    reg_pk, _ = helpers.create_registration(app, future_event.id, student.id)

    cancelled = as_organizer.post(
        f"/organizer/registrations/{reg_pk}/cancel", follow_redirects=True
    )
    assert b"has been notified" in cancelled.data

    from cems.models import Registration

    with app.app_context():
        assert db.session.get(Registration, reg_pk).status == REG_CANCELLED

    restored = as_organizer.post(
        f"/organizer/registrations/{reg_pk}/restore", follow_redirects=True
    )
    assert b"restored for" in restored.data
    with app.app_context():
        assert db.session.get(Registration, reg_pk).status == "CONFIRMED"


def test_restoring_an_active_registration_is_reported(app, as_organizer, future_event, student):
    reg_pk, _ = helpers.create_registration(app, future_event.id, student.id)
    response = as_organizer.post(
        f"/organizer/registrations/{reg_pk}/restore", follow_redirects=True
    )
    assert b"already active" in response.data


def test_restore_is_refused_when_the_event_is_full(app, as_organizer, organizer, full_event, student):
    helpers.create_registration(app, full_event.id, student.id + 500)
    cancelled_pk, _ = helpers.create_registration(
        app, full_event.id, student.id, status=REG_CANCELLED
    )
    response = as_organizer.post(
        f"/organizer/registrations/{cancelled_pk}/restore", follow_redirects=True
    )
    assert b"maximum capacity" in response.data


def test_organizer_cannot_manage_foreign_registrations(app, as_organizer, organizer2, student):
    foreign_event = helpers.create_event(app, title="Foreign", organizer_id=organizer2.id)
    reg_pk, _ = helpers.create_registration(app, foreign_event.id, student.id)
    response = as_organizer.post(
        f"/organizer/registrations/{reg_pk}/cancel", follow_redirects=True
    )
    assert b"only manage registrations for your own events" in response.data


def test_registration_listing_scopes(app, as_organizer, future_event, student, student2):
    present_pk, _ = helpers.create_registration(app, future_event.id, student.id)
    helpers.mark_attendance(app, present_pk, ATT_PRESENT, marked_by_id=1)
    helpers.create_registration(app, future_event.id, student2.id, status=REG_CANCELLED)

    for scope in ("confirmed", "cancelled", "present", "absent", "unmarked", "all"):
        response = as_organizer.get(f"/organizer/events/{future_event.id}/registrations?scope={scope}")
        assert response.status_code == 200, scope


# ---------------------------------------------------------------------------
# Attendance and certificates
# ---------------------------------------------------------------------------
def test_organizer_marks_attendance_in_bulk(app, as_organizer, organizer, future_event, student, student2):
    a, _ = helpers.create_registration(app, future_event.id, student.id)
    b, _ = helpers.create_registration(app, future_event.id, student2.id)
    response = as_organizer.post(
        f"/organizer/events/{future_event.id}/attendance",
        data={"scope": "all", "present": [str(a)]},
        follow_redirects=True,
    )
    assert b"Attendance verified for 2 participant(s)" in response.data

    from cems.models import Attendance

    with app.app_context():
        rows = {r.registration_id: r.status for r in Attendance.query.all()}
    assert rows[a] == ATT_PRESENT
    assert rows[b] == ATT_ABSENT


def test_organizer_toggles_attendance(app, as_organizer, future_event, student):
    reg_pk, _ = helpers.create_registration(app, future_event.id, student.id)
    first = as_organizer.post(
        f"/organizer/registrations/{reg_pk}/toggle-attendance", follow_redirects=True
    )
    assert b"marked PRESENT" in first.data
    second = as_organizer.post(
        f"/organizer/registrations/{reg_pk}/toggle-attendance", follow_redirects=True
    )
    assert b"marked ABSENT" in second.data


def test_attendance_toggle_refuses_foreign_events(app, as_organizer, organizer2, student):
    foreign = helpers.create_event(app, title="Foreign", organizer_id=organizer2.id)
    reg_pk, _ = helpers.create_registration(app, foreign.id, student.id)
    response = as_organizer.post(
        f"/organizer/registrations/{reg_pk}/toggle-attendance", follow_redirects=True
    )
    assert b"only manage attendance for your own events" in response.data


def test_attendance_page_and_report_pdf(app, as_organizer, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)

    assert as_organizer.get(f"/organizer/events/{past_event.id}/attendance").status_code == 200
    pdf = as_organizer.get(f"/organizer/events/{past_event.id}/attendance/report.pdf")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")


def test_organizer_issues_and_emails_certificates(app, as_organizer, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)

    response = as_organizer.post(
        f"/organizer/events/{past_event.id}/certificates", follow_redirects=True
    )
    assert b"certificate(s) issued" in response.data

    from cems.models import Certificate

    with app.app_context():
        certificate = Certificate.query.filter_by(event_id=past_event.id).first()
        assert certificate is not None
        certificate_pk = certificate.id

    listing = as_organizer.get(f"/organizer/events/{past_event.id}/certificates")
    assert listing.status_code == 200

    pdf = as_organizer.get(f"/organizer/certificates/{certificate_pk}/pdf")
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")

    emailed = as_organizer.post(
        f"/organizer/certificates/{certificate_pk}/send", follow_redirects=True
    )
    assert b"development message" in emailed.data


def test_organizer_cannot_download_a_foreign_certificate(app, as_organizer, organizer2, past_event, student):
    foreign = helpers.create_event(
        app, title="Foreign", organizer_id=organizer2.id, days=-5, status="COMPLETED"
    )
    reg_pk, _ = helpers.create_registration(app, foreign.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)

    from cems.models import Certificate

    with app.app_context():
        from cems.services import domain
        from cems.models import Registration

        certificate, _ = domain.issue_certificate(
            db.session.get(Registration, reg_pk), organizer2.id
        )
        db.session.commit()
        certificate_pk = certificate.id

    response = as_organizer.get(
        f"/organizer/certificates/{certificate_pk}/pdf", follow_redirects=True
    )
    assert b"only download certificates for your own events" in response.data


# ---------------------------------------------------------------------------
# Statistics, participants, feedback
# ---------------------------------------------------------------------------
def test_organizer_statistics_pages(app, as_organizer, future_event, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)
    helpers.create_registration(app, future_event.id, student.id)

    overall = as_organizer.get("/organizer/statistics")
    assert overall.status_code == 200
    assert b"Statistics" in overall.data

    per_event = as_organizer.get(f"/organizer/events/{past_event.id}/statistics")
    assert per_event.status_code == 200
    assert b"Computer Science &amp; Engineering" in per_event.data
    assert b"3rd Year" in per_event.data
    assert b"Participant register" in per_event.data


def test_participants_page_and_csv_export(app, as_organizer, future_event, student):
    helpers.create_registration(app, future_event.id, student.id)

    page = as_organizer.get("/organizer/participants")
    assert page.status_code == 200
    assert student.email.encode() in page.data

    csv = as_organizer.get("/organizer/participants.csv")
    assert csv.status_code == 200
    assert csv.mimetype == "text/csv"
    assert "Registration ID,Student,Email" in csv.get_data(as_text=True)
    assert student.email in csv.get_data(as_text=True)
    assert "attachment" in csv.headers["Content-Disposition"]


def test_csv_export_escapes_quotes(app, as_organizer, future_event, student):
    with app.app_context():
        from cems.models import User

        db.session.query(User).filter(User.id == student.id).update({"name": 'Ada "Countess" Lovelace'})
        db.session.commit()
    helpers.create_registration(app, future_event.id, student.id)
    csv = as_organizer.get("/organizer/participants.csv").get_data(as_text=True)
    assert '"Ada ""Countess"" Lovelace"' in csv


def test_organizer_feedback_review(app, as_organizer, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)
    entry = helpers.create_feedback(
        app, reg_pk, student.id, past_event.id, rating=5, comments="Excellent expo."
    )

    listing = as_organizer.get("/organizer/feedback")
    assert listing.status_code == 200
    assert b"Excellent expo." in listing.data

    detail = as_organizer.get(f"/organizer/feedback/{entry.id}")
    assert detail.status_code == 200
    assert b"Excellent expo." in detail.data


def test_organizer_cannot_read_foreign_feedback(app, as_organizer, organizer2, student):
    foreign = helpers.create_event(
        app, title="Foreign", organizer_id=organizer2.id, days=-5, status="COMPLETED"
    )
    reg_pk, _ = helpers.create_registration(app, foreign.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)
    entry = helpers.create_feedback(app, reg_pk, student.id, foreign.id, rating=3)

    response = as_organizer.get(f"/organizer/feedback/{entry.id}", follow_redirects=True)
    assert b"belongs to another organizer" in response.data


def test_organizer_attendance_records_page(app, as_organizer, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)
    for url in ("/organizer/attendance", "/organizer/attendance_records"):
        assert as_organizer.get(url).status_code == 200, url


# ---------------------------------------------------------------------------
# Notices
# ---------------------------------------------------------------------------
def test_organizer_creates_edits_and_deletes_a_notice(app, as_organizer, organizer):
    created = as_organizer.post(
        "/organizer/notices/create",
        data={
            "title": "Registrations close soon",
            "description": "Registrations for the innovation expo close on Friday.",
            "audience": "STUDENT",
            "is_important": "1",
        },
        follow_redirects=True,
    )
    assert b"published successfully" in created.data

    from cems.models import Notice

    with app.app_context():
        notice = Notice.query.filter_by(title="Registrations close soon").first()
        assert notice is not None
        assert notice.audience == "STUDENT"
        assert notice.is_important is True
        notice_id = notice.id

    assert as_organizer.get(f"/organizer/notices/{notice_id}").status_code == 200

    edited = as_organizer.post(
        f"/organizer/notices/{notice_id}/edit",
        data={
            "title": "Registrations closed",
            "description": "Registrations for the innovation expo are now closed.",
            "audience": "ALL",
        },
        follow_redirects=True,
    )
    assert b"updated successfully" in edited.data

    deleted = as_organizer.post(
        f"/organizer/notices/{notice_id}/delete", follow_redirects=True
    )
    assert b"deleted" in deleted.data
    with app.app_context():
        assert db.session.get(Notice, notice_id) is None


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "abc", "description": "long enough body", "audience": "ALL"},
        {"title": "Long enough title", "description": "short", "audience": "ALL"},
        {"title": "Long enough title", "description": "long enough body", "audience": "NOPE"},
    ],
)
def test_invalid_notice_returns_400(app, as_organizer, payload):
    assert as_organizer.post("/organizer/notices/create", data=payload).status_code == 400


def test_organizer_cannot_edit_or_delete_a_foreign_notice(app, as_organizer, organizer2):
    notice = helpers.create_notice(
        app, organizer2.id, "Foreign notice", "Written by another organizer.", audience="ALL"
    )
    edit = as_organizer.post(
        f"/organizer/notices/{notice.id}/edit",
        data={"title": "Hijacked notice", "description": "Should never be saved here.", "audience": "ALL"},
        follow_redirects=True,
    )
    assert b"only edit notices that you published" in edit.data

    delete = as_organizer.post(f"/organizer/notices/{notice.id}/delete", follow_redirects=True)
    assert b"only delete notices that you published" in delete.data

    from cems.models import Notice

    with app.app_context():
        assert db.session.get(Notice, notice.id).title == "Foreign notice"