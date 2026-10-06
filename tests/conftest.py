"""Pytest configuration and shared fixtures for CEMS.

Important: no application context is kept open across test-client requests.
Flask reuses an already-pushed application context for a request, which would
leak ``flask.g`` (and therefore ``current_user``) from one request to the next.
Every fixture therefore opens and closes its own short-lived context.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from cems import create_app  # noqa: E402
from cems.extensions import db as _db  # noqa: E402
from cems.models import ATT_ABSENT, ATT_PRESENT  # noqa: E402

import helpers  # noqa: E402

PASSWORD = "agc@2026"


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        _db.create_all()
    yield application
    with application.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def student(app):
    return helpers.create_user(
        app,
        "STUDENT",
        "student@test.agc.edu.in",
        "Test Student",
        roll_number="CSE-2023-0001",
        department="Computer Science & Engineering",
        year_of_study="3rd Year",
    )


@pytest.fixture()
def student2(app):
    return helpers.create_user(
        app,
        "STUDENT",
        "student2@test.agc.edu.in",
        "Second Student",
        roll_number="CSE-2023-0002",
        department="Information Technology",
        year_of_study="2nd Year",
    )


@pytest.fixture()
def faculty(app):
    return helpers.create_user(
        app,
        "FACULTY",
        "faculty@test.agc.edu.in",
        "Test Faculty",
        designation="Associate Professor",
        department="Computer Science & Engineering",
        employee_id="AGC-FAC-001",
    )


@pytest.fixture()
def organizer(app):
    return helpers.create_user(
        app,
        "ORGANIZER",
        "organizer@test.agc.edu.in",
        "Test Organizer",
        designation="Event Coordinator",
        organization="AGC Technical Committee",
    )


@pytest.fixture()
def organizer2(app):
    return helpers.create_user(
        app,
        "ORGANIZER",
        "organizer2@test.agc.edu.in",
        "Other Organizer",
        organization="AGC Sports Committee",
    )


@pytest.fixture()
def future_event(app, organizer):
    return helpers.create_event(
        app,
        title="AGC Future Tech Fest",
        description="A future campus event used for automated testing of the CEMS workflows.",
        category="Technical",
        days=10,
        start="10:00",
        end="16:00",
        venue="Main Auditorium, AGC Campus",
        organizer_id=organizer.id,
        max_capacity=50,
        deadline_days=-2,
        status="UPCOMING",
    )


@pytest.fixture()
def past_event(app, organizer):
    return helpers.create_event(
        app,
        title="AGC Completed Workshop",
        description="A completed campus event used for attendance and certificate testing.",
        category="Workshop",
        days=-5,
        start="10:00",
        end="17:00",
        venue="Seminar Hall A, AGC Campus",
        organizer_id=organizer.id,
        max_capacity=40,
        deadline_days=-10,
        status="COMPLETED",
    )


@pytest.fixture()
def full_event(app, organizer):
    return helpers.create_event(
        app,
        title="AGC Tiny Capacity Event",
        description="An event with a very small capacity used to test the full-capacity rule.",
        category="Cultural",
        days=12,
        start="11:00",
        end="13:00",
        venue="Open Air Auditorium, AGC Campus",
        organizer_id=organizer.id,
        max_capacity=1,
        deadline_days=-1,
        status="UPCOMING",
    )


@pytest.fixture()
def closed_event(app, organizer):
    from datetime import timedelta

    from cems.models import utcnow

    return helpers.create_event(
        app,
        title="AGC Deadline Closed Event",
        description="An event whose registration deadline has already passed.",
        category="Seminar",
        days=3,
        start="12:00",
        end="15:00",
        venue="Seminar Hall B, AGC Campus",
        organizer_id=organizer.id,
        max_capacity=60,
        deadline=utcnow() - timedelta(days=1),
        status="UPCOMING",
    )


@pytest.fixture()
def cancelled_event(app, organizer):
    return helpers.create_event(
        app,
        title="AGC Cancelled Event",
        description="An event that has been cancelled by the organizer.",
        category="Community",
        days=6,
        start="09:00",
        end="12:00",
        venue="AGC Health Centre",
        organizer_id=organizer.id,
        max_capacity=30,
        deadline_days=-1,
        status="CANCELLED",
    )


def login(client, email, password=PASSWORD, role=None):
    """Log a user in through the correct role login endpoint."""
    url = "/auth/login/" + role if role else "/auth/login"
    return client.post(url, data={"email": email, "password": password}, follow_redirects=True)


def logout(client):
    return client.post("/auth/logout", follow_redirects=True)


__all__ = ["login", "logout", "PASSWORD", "ATT_PRESENT", "ATT_ABSENT"]