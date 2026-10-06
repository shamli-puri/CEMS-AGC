"""Points 26-27: shared profile management, PDF services and the email fallback."""

import io

import helpers
import pytest

from cems.extensions import db
from cems.models import ATT_PRESENT


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def test_profile_requires_authentication(client):
    for url in ("/profile/", "/profile/edit", "/profile/password"):
        assert client.get(url).status_code == 302


@pytest.mark.parametrize("fixture_name", ["student", "faculty", "organizer"])
def test_every_role_can_view_and_edit_its_profile(request, app, fixture_name):
    user = request.getfixturevalue(fixture_name)
    client = app.test_client()
    helpers.login_as(client, user)

    view = client.get("/profile/")
    assert view.status_code == 200
    assert user.name.encode() in view.data

    edit = client.get("/profile/edit")
    assert edit.status_code == 200


def test_student_updates_their_profile(app, student):
    client = app.test_client()
    helpers.login_as(client, student)
    response = client.post(
        "/profile/edit",
        data={
            "name": "Test Student Updated",
            "phone": "9876543210",
            "department": "Information Technology",
            "roll_number": "CSE-2023-0001",
            "year_of_study": "4th Year",
            "bio": "Updated by the CEMS test suite.",
        },
        follow_redirects=True,
    )
    assert b"Profile updated" in response.data

    from cems.models import User

    with app.app_context():
        row = db.session.get(User, student.id)
        assert row.name == "Test Student Updated"
        assert row.phone == "9876543210"
        assert row.department == "Information Technology"
        assert row.year_of_study == "4th Year"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Ab"},
        {"name": "Valid Name", "phone": "123"},
        {"name": "Valid Name", "phone": "not-a-number"},
        {"name": "Valid Name", "department": "Astrology"},
    ],
)
def test_invalid_profile_update_returns_400(app, student, payload):
    client = app.test_client()
    helpers.login_as(client, student)
    response = client.post("/profile/edit", data=payload)
    assert response.status_code == 400


def test_faculty_profile_updates_faculty_fields(app, faculty):
    client = app.test_client()
    helpers.login_as(client, faculty)
    response = client.post(
        "/profile/edit",
        data={
            "name": "Test Faculty Updated",
            "designation": "Professor",
            "department": "Mechanical Engineering",
            "employee_id": "AGC-FAC-002",
        },
        follow_redirects=True,
    )
    assert b"Profile updated" in response.data

    from cems.models import User

    with app.app_context():
        row = db.session.get(User, faculty.id)
        assert row.designation == "Professor"
        assert row.employee_id == "AGC-FAC-002"


def test_organizer_profile_updates_organizer_fields(app, organizer):
    client = app.test_client()
    helpers.login_as(client, organizer)
    response = client.post(
        "/profile/edit",
        data={
            "name": "Test Organizer Updated",
            "organization": "AGC Innovation Cell",
            "designation": "Head Coordinator",
        },
        follow_redirects=True,
    )
    assert b"Profile updated" in response.data

    from cems.models import User

    with app.app_context():
        row = db.session.get(User, organizer.id)
        assert row.organization == "AGC Innovation Cell"


def test_password_change_flow(app, student):
    client = app.test_client()
    helpers.login_as(client, student)
    assert client.get("/profile/password").status_code == 200

    response = client.post(
        "/profile/password",
        data={
            "current_password": "agc@2026",
            "new_password": "brand-new-pass",
            "confirm_password": "brand-new-pass",
        },
        follow_redirects=True,
    )
    assert b"Password changed" in response.data

    from cems.models import User

    with app.app_context():
        assert db.session.get(User, student.id).check_password("brand-new-pass") is True

    helpers.logout(client)
    relogin = client.post(
        "/auth/login/student", data={"email": student.email, "password": "brand-new-pass"}
    )
    assert relogin.status_code == 302


@pytest.mark.parametrize(
    "payload",
    [
        {"current_password": "wrong", "new_password": "abcdef", "confirm_password": "abcdef"},
        {"current_password": "agc@2026", "new_password": "abc", "confirm_password": "abc"},
        {"current_password": "agc@2026", "new_password": "abcdef", "confirm_password": "different"},
        {"current_password": "agc@2026", "new_password": "agc@2026", "confirm_password": "agc@2026"},
    ],
)
def test_invalid_password_change_returns_400(app, student, payload):
    client = app.test_client()
    helpers.login_as(client, student)
    response = client.post("/profile/password", data=payload)
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# PDF services
# ---------------------------------------------------------------------------
def test_certificate_pdf_is_a_valid_document(app, past_event, student, faculty):
    from cems.models import Registration
    from cems.services import certificate_service, domain

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    with app.app_context():
        certificate, _ = domain.issue_certificate(db.session.get(Registration, reg_pk), faculty.id)
        db.session.commit()
        pdf = certificate_service.build_certificate_pdf(certificate)

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_attendance_record_pdf(app, past_event, student, faculty):
    from cems.models import Registration
    from cems.services import certificate_service

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    with app.app_context():
        from cems.models import User

        registrations = [db.session.get(Registration, reg_pk)]
        student_row = db.session.get(User, student.id)
        pdf = certificate_service.build_attendance_record_pdf(registrations, student_row)

    assert pdf.startswith(b"%PDF")


def test_attendance_report_pdf(app, past_event, student, faculty):
    from cems.models import Event, Registration
    from cems.services import certificate_service

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)

    with app.app_context():
        event = db.session.get(Event, past_event.id)
        pdf = certificate_service.build_attendance_report_pdf(
            event, [db.session.get(Registration, reg_pk)], marked_by=None
        )

    assert pdf.startswith(b"%PDF")


# ---------------------------------------------------------------------------
# QR service
# ---------------------------------------------------------------------------
def test_qr_helpers_produce_png_svg_and_data_uri(app, student, future_event):
    from cems.models import Registration
    from cems.services import qr_service

    reg_pk, code = helpers.create_registration(app, future_event.id, student.id)
    with app.app_context():
        payload = qr_service.build_qr_payload(db.session.get(Registration, reg_pk))

    png = qr_service.qr_png_bytes(payload)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    svg = qr_service.qr_svg(payload)
    assert svg.lstrip().startswith(b"<?xml") or b"<svg" in svg[:400]

    uri = qr_service.qr_data_uri(payload)
    assert uri.startswith("data:image/png;base64,")
    assert code in payload


# ---------------------------------------------------------------------------
# Email service
# ---------------------------------------------------------------------------
def test_send_email_without_recipients_is_refused(app):
    from cems.services import email_service

    with app.test_request_context():
        result = email_service.send_email("Subject", "", "Body")
    assert result["ok"] is False
    assert result["delivered"] is False


def test_email_fallback_writes_to_the_configured_log(app, tmp_path):
    from cems.services import email_service

    log_file = tmp_path / "emails.log"
    app.config["MAIL_LOG_FILE"] = str(log_file)
    with app.test_request_context():
        result = email_service.send_email(
            "[CEMS-AGC] Registration confirmed: Test",
            recipients=["student@agc.edu.in", "  "],
            body="Line one\nLine two",
        )
    assert result["delivered"] is False
    text = log_file.read_text(encoding="utf-8")
    assert "[CEMS-AGC] Registration confirmed: Test" in text
    assert "Line one" in text


def test_email_fallback_records_a_development_message_on_g(app):
    from flask import g

    from cems.services import email_service

    with app.test_request_context():
        assert email_service.smtp_configured(app) is False
        email_service.send_email("Dev subject", recipients="student@agc.edu.in", body="Body")
        assert len(g.dev_emails) == 1
        assert g.dev_emails[0]["subject"] == "Dev subject"


def test_domain_email_templates(app, organizer, past_event, student, future_event):
    from cems.models import Registration
    from cems.services import email_service

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    with app.app_context():
        registration = db.session.get(Registration, reg_pk)
        assert email_service.send_registration_email(registration)["ok"] is True
        assert email_service.send_registration_cancelled_email(registration)["ok"] is True

    upcoming = helpers.create_event(app, title="Cancel Me", days=3, organizer_id=organizer.id)
    reg2, _ = helpers.create_registration(app, upcoming.id, student.id)
    with app.app_context():
        from cems.models import Event

        event = db.session.get(Event, upcoming.id)
        result = email_service.send_event_cancelled_email(event)
    assert result["ok"] is True


def test_certificate_email_template(app, past_event, student, faculty):
    from cems.models import Certificate, Registration
    from cems.services import email_service, domain

    reg_pk, _ = helpers.create_registration(app, past_event.id, student.id)
    helpers.mark_attendance(app, reg_pk, ATT_PRESENT, marked_by_id=faculty.id)
    with app.app_context():
        certificate, _ = domain.issue_certificate(db.session.get(Registration, reg_pk), faculty.id)
        db.session.commit()
        assert email_service.send_certificate_email(certificate)["ok"] is True
        assert Certificate.query.count() == 1