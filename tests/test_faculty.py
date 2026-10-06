"""Points 15-17: the faculty module - overview, attendance marking, feedback, notices."""

import helpers
import pytest

from cems.extensions import db
from cems.models import ATT_ABSENT, ATT_PRESENT, REG_CANCELLED


@pytest.fixture()
def as_faculty(app, faculty):
    client = app.test_client()
    helpers.login_as(client, faculty)
    return client


# ---------------------------------------------------------------------------
# Overview pages
# ---------------------------------------------------------------------------
def test_faculty_dashboard(app, as_faculty, faculty, past_event, future_event):
    response = as_faculty.get("/faculty/dashboard")
    assert response.status_code == 200
    assert b"Faculty" in response.data
    assert faculty.name.encode() in response.data


def test_faculty_event_listing_and_detail(app, as_faculty, organizer, past_event, student):
    helpers.create_registration(app, past_event.id, student.id)
    assert as_faculty.get("/faculty/events").status_code == 200
    assert as_faculty.get("/faculty/events?scope=upcoming").status_code == 200
    detail = as_faculty.get(f"/faculty/events/{past_event.id}")
    assert detail.status_code == 200
    assert b"Completed Workshop" in detail.data


def test_faculty_registration_roster_scopes(app, as_faculty, past_event, student, student2):
    present_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, present_pk, ATT_PRESENT, marked_by_id=1)
    helpers.create_registration(app, past_event.id, student2.id)

    for url in (
        f"/faculty/events/{past_event.id}/registrations",
        f"/faculty/events/{past_event.id}/registrations?scope=present",
        f"/faculty/events/{past_event.id}/registrations?scope=absent",
        f"/faculty/events/{past_event.id}/attendees",
    ):
        assert as_faculty.get(url).status_code == 200, url

    present = as_faculty.get(f"/faculty/events/{past_event.id}/registrations?scope=present")
    assert b"Test Student" in present.data
    assert b"Second Student" not in present.data


# ---------------------------------------------------------------------------
# Attendance marking
# ---------------------------------------------------------------------------
def test_faculty_marks_attendance_in_bulk(app, as_faculty, faculty, past_event, student, student2):
    a, _ = helpers.create_registration(app, past_event.id, student.id)
    b, _ = helpers.create_registration(app, past_event.id, student2.id)

    response = as_faculty.post(
        f"/faculty/events/{past_event.id}/attendance",
        data={"present": [str(a)], "absent": [str(b)], "scope": "marked"},
        follow_redirects=True,
    )
    assert b"Attendance saved for 2 participant(s)" in response.data

    from cems.models import Attendance

    with app.app_context():
        rows = {r.registration_id: r.status for r in Attendance.query.all()}
        assert rows[a] == ATT_PRESENT
        assert rows[b] == ATT_ABSENT
        assert Attendance.query.filter_by(registration_id=a).first().marked_by_id == faculty.id


def test_faculty_bulk_attendance_scope_all(app, as_faculty, past_event, student):
    a, _ = helpers.create_registration(app, past_event.id, student.id)
    response = as_faculty.post(
        f"/faculty/events/{past_event.id}/attendance",
        data={"scope": "all", "present": [str(a)]},
        follow_redirects=True,
    )
    assert b"Attendance saved for 1 participant(s)" in response.data

    from cems.models import Attendance

    with app.app_context():
        assert Attendance.query.filter_by(registration_id=a).first().status == ATT_PRESENT


def test_faculty_attendance_without_selection_warns(app, as_faculty, past_event, student):
    helpers.create_registration(app, past_event.id, student.id)
    response = as_faculty.post(
        f"/faculty/events/{past_event.id}/attendance",
        data={"scope": "marked"},
        follow_redirects=True,
    )
    assert b"No valid participants" in response.data


def test_faculty_toggle_attendance(app, as_faculty, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)

    first = as_faculty.post(
        f"/faculty/registrations/{reg_pk}/toggle-attendance", follow_redirects=True
    )
    assert b"marked PRESENT" in first.data

    from cems.models import Attendance

    with app.app_context():
        assert Attendance.query.filter_by(registration_id=reg_pk).first().status == ATT_PRESENT

    second = as_faculty.post(
        f"/faculty/registrations/{reg_pk}/toggle-attendance", follow_redirects=True
    )
    assert b"marked ABSENT" in second.data
    with app.app_context():
        assert Attendance.query.filter_by(registration_id=reg_pk).first().status == ATT_ABSENT


def test_attendance_toggle_refuses_cancelled_registration(app, as_faculty, past_event, student):
    reg_pk, _ = helpers.create_registration(
        app, past_event.id, student.id, status=REG_CANCELLED
    )
    response = as_faculty.post(
        f"/faculty/registrations/{reg_pk}/toggle-attendance", follow_redirects=True
    )
    assert b"Only confirmed registrations" in response.data


def test_faculty_attendance_page_and_pdf(app, as_faculty, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)

    page = as_faculty.get(f"/faculty/events/{past_event.id}/attendance")
    assert page.status_code == 200
    assert b"Test Student" in page.data

    pdf = as_faculty.get(f"/faculty/events/{past_event.id}/attendance/report.pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF")


def test_faculty_attendance_records_page(app, as_faculty, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)
    for url in ("/faculty/attendance", "/faculty/attendance_records"):
        response = as_faculty.get(url)
        assert response.status_code == 200, url
        assert b"Completed Workshop" in response.data


def test_completed_event_attendance_also_issues_certificates(app, as_faculty, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    as_faculty.post(
        f"/faculty/events/{past_event.id}/attendance",
        data={"scope": "all", "present": [str(reg_pk)]},
        follow_redirects=True,
    )
    from cems.models import Certificate

    with app.app_context():
        certificate = Certificate.query.filter_by(registration_id=reg_pk).first()
        assert certificate is not None
        assert certificate.certificate_id.startswith("AGC-CERT-")


# ---------------------------------------------------------------------------
# Feedback review
# ---------------------------------------------------------------------------
def test_faculty_feedback_listing_and_detail(app, as_faculty, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)
    entry = helpers.create_feedback(
        app, reg_pk, student.id, past_event.id, rating=4, comments="Well organised."
    )

    listing = as_faculty.get("/faculty/feedback")
    assert listing.status_code == 200
    assert b"Well organised." in listing.data

    detail = as_faculty.get(f"/faculty/feedback/{entry.id}")
    assert detail.status_code == 200
    assert b"Well organised." in detail.data


def test_faculty_feedback_filters_by_rating_and_query(app, as_faculty, past_event, student):
    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=1)
    helpers.create_feedback(
        app, reg_pk, student.id, past_event.id, rating=5, comments="Outstanding speaker."
    )

    five = as_faculty.get("/faculty/feedback?rating=5")
    assert b"Outstanding speaker." in five.data

    one = as_faculty.get("/faculty/feedback?rating=1")
    assert b"Outstanding speaker." not in one.data

    search = as_faculty.get("/faculty/feedback?q=Outstanding")
    assert b"Outstanding speaker." in search.data


def test_faculty_feedback_detail_missing_is_404(app, as_faculty):
    assert as_faculty.get("/faculty/feedback/987654").status_code == 404


# ---------------------------------------------------------------------------
# Notices
# ---------------------------------------------------------------------------
def test_faculty_notice_listing_and_detail(app, as_faculty, organizer):
    notice = helpers.create_notice(
        app, organizer.id, "Faculty Notice", "Body for faculty.", audience="FACULTY"
    )
    listing = as_faculty.get("/faculty/notices")
    assert listing.status_code == 200
    assert b"Faculty Notice" in listing.data

    detail = as_faculty.get(f"/faculty/notices/{notice.id}")
    assert detail.status_code == 200
    assert b"Body for faculty." in detail.data


def test_faculty_cannot_open_a_student_only_notice(app, as_faculty, organizer):
    notice = helpers.create_notice(
        app, organizer.id, "Student Only Notice", "Body.", audience="STUDENT"
    )
    response = as_faculty.get(f"/faculty/notices/{notice.id}", follow_redirects=True)
    assert b"not published for faculty" in response.data


def test_faculty_reminder_uses_the_development_fallback(app, as_faculty, future_event, student):
    helpers.create_registration(app, future_event.id, student.id)
    response = as_faculty.post(
        f"/faculty/events/{future_event.id}/remind", follow_redirects=True
    )
    assert b"development message" in response.data


def test_faculty_reminder_without_participants(app, as_faculty, future_event):
    response = as_faculty.post(
        f"/faculty/events/{future_event.id}/remind", follow_redirects=True
    )
    assert b"No confirmed participants" in response.data