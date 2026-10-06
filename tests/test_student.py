"""Points 10-14: the student module - dashboard, registration, tickets, attendance,
certificates and feedback."""

import helpers
import pytest

from cems.extensions import db
from cems.models import ATT_PRESENT, REG_CANCELLED, REG_CONFIRMED

PASSWORD = "agc@2026"


@pytest.fixture()
def as_student(app, student):
    """A logged-in student client plus the student record."""
    client = app.test_client()
    helpers.login_as(client, student)
    return client


# ---------------------------------------------------------------------------
# Dashboard and listings
# ---------------------------------------------------------------------------
def test_dashboard_renders_with_statistics(app, as_student, student, future_event, past_event):
    helpers.create_registration(app, future_event.id, student.id)
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)

    response = as_student.get("/student/dashboard")
    assert response.status_code == 200
    assert b"Student Dashboard" in response.data
    assert b"Test Student" in response.data


def test_dashboard_alias_as_slash(app, as_student):
    assert as_student.get("/student/").status_code == 200


def test_student_event_list_filters(app, as_student, organizer, future_event, past_event):
    assert as_student.get("/student/events").status_code == 200
    assert as_student.get("/student/events?category=Technical").status_code == 200
    assert as_student.get("/student/events?q=Future").status_code == 200
    assert as_student.get("/student/events?scope=upcoming").status_code == 200
    assert as_student.get(f"/student/events?q=Future+Tech+Fest").data.count(b"Future Tech Fest") >= 1
    assert b"Completed Workshop" not in as_student.get("/student/events?q=Future+Tech+Fest").data


def test_registration_scopes(app, as_student, student, future_event, past_event):
    future_pk, _ = helpers.create_registration(app, future_event.id, student.id)
    past_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, past_pk, ATT_PRESENT, marked_by_id=1)

    assert as_student.get("/student/registrations").status_code == 200
    assert as_student.get("/student/registrations?scope=upcoming").status_code == 200
    assert as_student.get("/student/registrations?scope=attended").status_code == 200
    assert as_student.get("/student/registrations?scope=past").status_code == 200
    assert as_student.get("/student/registrations?scope=cancelled").status_code == 200
    assert as_student.get("/student/my-registrations").status_code == 200


# ---------------------------------------------------------------------------
# Registration workflow
# ---------------------------------------------------------------------------
def test_student_registers_and_receives_a_registration_id(app, as_student, student, future_event):
    response = as_student.post(
        f"/student/events/{future_event.id}/register", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Registration successful" in response.data

    from cems.models import Registration

    with app.app_context():
        registration = Registration.query.filter_by(
            student_id=student.id, event_id=future_event.id
        ).first()
        assert registration is not None
        assert registration.status == REG_CONFIRMED
        assert registration.registration_id.startswith("AGC-REG-")
        assert registration.attendance is None


def test_duplicate_registration_is_blocked(app, as_student, student, future_event):
    helpers.create_registration(app, future_event.id, student.id)
    response = as_student.post(
        f"/student/events/{future_event.id}/register", follow_redirects=True
    )
    assert b"already registered" in response.data


def test_registration_blocked_when_event_is_full(app, as_student, student, full_event):
    helpers.create_registration(app, full_event.id, student.id + 1000)
    response = as_student.post(
        f"/student/events/{full_event.id}/register", follow_redirects=True
    )
    assert b"maximum capacity" in response.data


def test_registration_blocked_after_the_deadline(app, as_student, closed_event):
    response = as_student.post(
        f"/student/events/{closed_event.id}/register", follow_redirects=True
    )
    assert b"deadline" in response.data.lower()


def test_registration_blocked_for_a_cancelled_event(app, as_student, cancelled_event):
    response = as_student.post(
        f"/student/events/{cancelled_event.id}/register", follow_redirects=True
    )
    assert b"cancelled" in response.data.lower()


def test_registration_for_missing_event_returns_404(app, as_student):
    assert as_student.post("/student/events/424242/register").status_code == 404


def test_student_cancels_own_registration(app, as_student, student, future_event):
    reg_pk, code = helpers.create_registration(app, future_event.id, student.id)
    response = as_student.post(f"/student/registrations/{reg_pk}/cancel", follow_redirects=True)
    assert b"cancel" in response.data.lower()

    from cems.models import Registration

    with app.app_context():
        row = db.session.get(Registration, reg_pk)
        assert row.status == REG_CANCELLED
        assert row.cancelled_at is not None
        assert code.startswith("AGC-REG-")


def test_student_cannot_cancel_someone_elses_registration(app, as_student, student2, future_event):
    reg_pk, _ = helpers.create_registration(app, future_event.id, student2.id)
    response = as_student.post(f"/student/registrations/{reg_pk}/cancel", follow_redirects=True)
    assert b"only cancel your own" in response.data

    from cems.models import Registration

    with app.app_context():
        assert db.session.get(Registration, reg_pk).status == REG_CONFIRMED


def test_cancellation_frees_the_seat(app, as_student, student, full_event):
    reg_pk, _ = helpers.create_registration(app, full_event.id, student.id)
    as_student.post(f"/student/registrations/{reg_pk}/cancel", follow_redirects=True)

    from cems.models import Event

    with app.app_context():
        assert db.session.get(Event, full_event.id).seats_taken == 0


# ---------------------------------------------------------------------------
# Digital ticket and QR
# ---------------------------------------------------------------------------
def test_ticket_page_shows_the_qr_and_verify_link(app, as_student, student, future_event):
    reg_pk, code = helpers.create_registration(app, future_event.id, student.id)
    response = as_student.get(f"/student/registrations/{reg_pk}/ticket")
    assert response.status_code == 200
    assert code.encode() in response.data
    assert b"qr.png" in response.data


def test_ticket_qr_returns_a_png(app, as_student, student, future_event):
    reg_pk, _ = helpers.create_registration(app, future_event.id, student.id)
    response = as_student.get(f"/student/registrations/{reg_pk}/qr.png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_ticket_of_another_student_is_refused(app, as_student, student2, future_event):
    reg_pk, _ = helpers.create_registration(app, future_event.id, student2.id)
    response = as_student.get(f"/student/registrations/{reg_pk}/ticket", follow_redirects=True)
    assert b"belongs to another student" in response.data
    assert as_student.get(f"/student/registrations/{reg_pk}/qr.png").status_code == 403


def test_cancelled_registration_has_no_valid_ticket(app, as_student, student, future_event):
    reg_pk, _ = helpers.create_registration(
        app, future_event.id, student.id, status=REG_CANCELLED
    )
    response = as_student.get(f"/student/registrations/{reg_pk}/ticket", follow_redirects=True)
    assert b"no longer valid" in response.data


def test_qr_payload_encodes_the_registration(app, student, future_event):
    from cems.services import qr_service

    reg_pk, code = helpers.create_registration(app, future_event.id, student.id)
    from cems.models import Registration

    with app.app_context():
        payload = qr_service.build_qr_payload(db.session.get(Registration, reg_pk))
    assert payload == f"AGC-CEMS|{code}|{reg_pk}"


def test_public_ticket_verification(app, student, future_event):
    reg_pk, code = helpers.create_registration(app, future_event.id, student.id)
    response = app.test_client().get(f"/events/verify/{code}")
    assert response.status_code == 200
    assert code.encode() in response.data


def test_public_ticket_verification_of_unknown_code(app):
    assert app.test_client().get("/events/verify/AGC-REG-DOESNOTEXIST").status_code == 404


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
def test_attendance_page_and_pdf(app, as_student, student, past_event, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    page = as_student.get("/student/attendance")
    assert page.status_code == 200

    pdf = as_student.get("/student/attendance/record.pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")


def test_attendance_page_shows_pending_rows(app, as_student, student, past_event):
    helpers.create_registration(app, past_event.id, student.id)
    response = as_student.get("/student/attendance")
    assert b"Not Marked" in response.data


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------
def test_certificate_list_and_pdf(app, as_student, student, past_event, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    listing = as_student.get("/student/certificates")
    assert listing.status_code == 200

    from cems.models import Certificate

    with app.app_context():
        certificate = Certificate.query.filter_by(student_id=student.id).first()
        assert certificate is not None
        certificate_id = certificate.id

    for url in (
        f"/student/certificates/{certificate_id}/pdf",
        f"/student/certificates/{certificate_id}/download",
    ):
        response = as_student.get(url)
        assert response.status_code == 200, url
        assert response.mimetype == "application/pdf"
        assert response.data.startswith(b"%PDF")


def test_certificate_email_uses_the_development_fallback(app, as_student, student, past_event, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    # Visiting the list back-fills the certificate row for attended events.
    as_student.get("/student/certificates")

    from cems.models import Certificate

    with app.app_context():
        certificate_id = Certificate.query.filter_by(student_id=student.id).first().id

    response = as_student.post(
        f"/student/certificates/{certificate_id}/send", follow_redirects=True
    )
    assert b"development message" in response.data


def test_student_cannot_open_another_students_certificate(app, as_student, student2, past_event, faculty):
    from cems.models import Certificate, Registration

    reg_pk, _ = helpers.create_registration(app, past_event.id, student2.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    with app.app_context():
        from cems.services import domain

        registration = db.session.get(Registration, reg_pk)
        domain.issue_certificate(registration, faculty.id)
        db.session.commit()
        certificate_id = Certificate.query.filter_by(student_id=student2.id).first().id

    response = as_student.get(
        f"/student/certificates/{certificate_id}/pdf", follow_redirects=True
    )
    assert b"belongs to another student" in response.data


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
def test_feedback_submitted_for_an_attended_event(app, as_student, student, past_event, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    response = as_student.post(
        f"/student/events/{past_event.id}/feedback",
        data={"rating": 5, "comments": "Excellent organisation throughout."},
        follow_redirects=True,
    )
    assert b"recorded" in response.data

    from cems.models import Feedback

    with app.app_context():
        entry = Feedback.query.filter_by(student_id=student.id).first()
        assert entry is not None
        assert entry.rating == 5


def test_feedback_is_blocked_twice(app, as_student, student, past_event, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    as_student.post(
        f"/student/events/{past_event.id}/feedback",
        data={"rating": 4, "comments": "First submission."},
        follow_redirects=True,
    )
    response = as_student.post(
        f"/student/events/{past_event.id}/feedback",
        data={"rating": 4, "comments": "Second submission."},
        follow_redirects=True,
    )
    assert b"already submitted" in response.data


def test_feedback_blocked_for_an_unattended_event(app, as_student, student, past_event, faculty):
    helpers.create_registration(app, past_event.id, student.id)
    response = as_student.post(
        f"/student/events/{past_event.id}/feedback",
        data={"rating": 4, "comments": "I was not there at all."},
        follow_redirects=True,
    )
    assert b"attended" in response.data.lower()


def test_feedback_blocked_without_a_registration(app, as_student, past_event):
    response = as_student.post(
        f"/student/events/{past_event.id}/feedback",
        data={"rating": 4, "comments": "Never registered for this."},
        follow_redirects=True,
    )
    assert b"only give feedback for events you registered" in response.data


@pytest.mark.parametrize(
    "payload",
    [
        {"rating": "", "comments": "No rating supplied."},
        {"rating": 9, "comments": "Rating out of range."},
        {"rating": 3, "comments": "hi"},
        {"rating": 3, "comments": "x" * 1200},
    ],
)
def test_invalid_feedback_is_rejected(app, as_student, student, past_event, faculty, payload):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    response = as_student.post(
        f"/student/events/{past_event.id}/feedback", data=payload, follow_redirects=True
    )
    from cems.models import Feedback

    with app.app_context():
        assert Feedback.query.filter_by(registration_id=reg_pk).first() is None


def test_feedback_list_shows_entries_and_pending(app, as_student, student, past_event, future_event, faculty):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    pending_pk, _ = helpers.create_registration(app, future_event.id, student.id)
    helpers.create_feedback(app, reg_pk, student.id, past_event.id, rating=5)

    response = as_student.get("/student/feedback")
    assert response.status_code == 200
    assert b"Great event." in response.data


# ---------------------------------------------------------------------------
# Notices and participants
# ---------------------------------------------------------------------------
def test_student_notice_pages(app, as_student, organizer):
    notice = helpers.create_notice(
        app, organizer.id, "Student Notice Title", "Body for students.", audience="STUDENT"
    )
    listing = as_student.get("/student/notices")
    assert listing.status_code == 200
    assert b"Student Notice Title" in listing.data

    detail = as_student.get(f"/student/notices/{notice.id}")
    assert detail.status_code == 200

    hidden = as_student.get(
        f"/student/notices/{helpers.create_notice(app, organizer.id, 'Faculty Only', 'Body.', audience='FACULTY').id}",
        follow_redirects=True,
    )
    assert b"not published for your role" in hidden.data


def test_participant_list_requires_registration(app, as_student, student, student2, future_event):
    helpers.create_registration(app, future_event.id, student2.id)
    blocked = as_student.get(f"/student/events/{future_event.id}/participants", follow_redirects=True)
    assert b"Register for this event" in blocked.data

    helpers.create_registration(app, future_event.id, student.id)
    allowed = as_student.get(f"/student/events/{future_event.id}/participants")
    assert allowed.status_code == 200