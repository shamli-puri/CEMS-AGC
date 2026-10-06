"""Points 23-25: public event catalogue, filters, details and notices."""

import helpers
import pytest

from cems.extensions import db
from cems.models import EVENT_CANCELLED


@pytest.fixture()
def signed_in(app, student):
    client = app.test_client()
    helpers.login_as(client, student)
    return client


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
def test_catalogue_requires_authentication(client):
    for url in ("/events/catalogue", "/events/", "/events/search?q=tech"):
        response = client.get(url)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]


def test_catalogue_lists_every_event(app, signed_in, organizer):
    helpers.create_event(app, title="Technical Summit", category="Technical", organizer_id=organizer.id)
    helpers.create_event(app, title="Cultural Night", category="Cultural", organizer_id=organizer.id)
    response = signed_in.get("/events/catalogue")
    assert response.status_code == 200
    assert b"Technical Summit" in response.data
    assert b"Cultural Night" in response.data


def test_catalogue_root_alias(app, signed_in, organizer):
    helpers.create_event(app, title="Alias Event", organizer_id=organizer.id)
    assert signed_in.get("/events/").status_code == 200


def test_catalogue_search_by_free_text(app, signed_in, organizer):
    helpers.create_event(app, title="Robotics Challenge", organizer_id=organizer.id)
    helpers.create_event(app, title="Photography Walk", organizer_id=organizer.id)

    hit = signed_in.get("/events/catalogue?q=Robotics")
    assert b"Robotics Challenge" in hit.data
    assert b"Photography Walk" not in hit.data


def test_catalogue_search_matches_description_and_venue(app, signed_in, organizer):
    helpers.create_event(
        app,
        title="Generic Title",
        description="A workshop about drones and aerial robotics.",
        venue="Hangar 3, AGC Campus",
        organizer_id=organizer.id,
    )
    assert b"Generic Title" in signed_in.get("/events/catalogue?q=drones").data
    assert b"Generic Title" in signed_in.get("/events/catalogue?q=Hangar").data


def test_catalogue_category_and_status_filters(app, signed_in, organizer):
    helpers.create_event(app, title="Tech Only", category="Technical", organizer_id=organizer.id)
    helpers.create_event(app, title="Sport Only", category="Sports", organizer_id=organizer.id)
    helpers.create_event(
        app, title="Dead Event", category="Technical", organizer_id=organizer.id, status=EVENT_CANCELLED
    )

    tech = signed_in.get("/events/catalogue?category=Technical")
    assert b"Tech Only" in tech.data
    assert b"Sport Only" not in tech.data

    sports = signed_in.get("/events/catalogue?category=Sports")
    assert b"Sport Only" in sports.data
    assert b"Tech Only" not in sports.data


def test_catalogue_ignores_an_unknown_category(app, signed_in, organizer):
    helpers.create_event(app, title="Tech Only", category="Technical", organizer_id=organizer.id)
    response = signed_in.get("/events/catalogue?category=NotACategory")
    assert response.status_code == 200
    assert b"Tech Only" in response.data


def test_catalogue_date_filters(app, signed_in, organizer):
    soon = helpers.create_event(app, title="Soon", organizer_id=organizer.id, days=3)
    later = helpers.create_event(app, title="Later", organizer_id=organizer.id, days=40)

    early = signed_in.get("/events/catalogue?date_to=" + soon.event_date.isoformat())
    assert b"Later" not in early.data

    late = signed_in.get("/events/catalogue?date_from=" + soon.event_date.isoformat())
    assert b"Later" in late.data


def test_catalogue_reports_a_bad_date(app, signed_in):
    response = signed_in.get("/events/catalogue?date_from=not-a-date")
    assert response.status_code == 200
    assert b"valid date" in response.data.lower()


def test_search_route_renders_results_in_place(app, signed_in, organizer):
    helpers.create_event(app, title="Deep Link Searchable", organizer_id=organizer.id)
    helpers.create_event(app, title="Unrelated Event", organizer_id=organizer.id)

    response = signed_in.get("/events/search?q=Deep+Link")
    assert response.status_code == 200
    assert b"Deep Link Searchable" in response.data
    assert b"Unrelated Event" not in response.data


def test_search_marks_the_students_registrations(app, signed_in, student, organizer):
    event = helpers.create_event(app, title="Registered Event", organizer_id=organizer.id)
    helpers.create_registration(app, event.id, student.id)
    response = signed_in.get(f"/events/catalogue?q=Registered+Event")
    assert response.status_code == 200
    assert b"Registered" in response.data


# ---------------------------------------------------------------------------
# Event detail
# ---------------------------------------------------------------------------
def test_event_detail_page(app, signed_in, organizer, future_event):
    response = signed_in.get(f"/events/{future_event.id}")
    assert response.status_code == 200
    assert b"Future Tech Fest" in response.data
    assert b"Main Auditorium" in response.data


def test_event_detail_of_a_missing_event_is_404(app, signed_in):
    assert signed_in.get("/events/999999").status_code == 404


def test_event_detail_is_visible_to_faculty_and_organizer(app, student, faculty, organizer):
    event = helpers.create_event(app, title="Shared Event", organizer_id=organizer.id)
    for user in (faculty, organizer):
        client = app.test_client()
        helpers.login_as(client, user)
        assert client.get(f"/events/{event.id}").status_code == 200


# ---------------------------------------------------------------------------
# Notices
# ---------------------------------------------------------------------------
def test_public_notices_index_and_detail(app, signed_in, organizer):
    notice = helpers.create_notice(
        app, organizer.id, "Exam Schedule Released", "The exam schedule is now published.", audience="ALL"
    )
    index = signed_in.get("/notices/")
    assert index.status_code == 200
    assert b"Exam Schedule Released" in index.data

    detail = signed_in.get(f"/notices/{notice.id}")
    assert detail.status_code == 200
    assert b"The exam schedule is now published." in detail.data


def test_notices_index_without_trailing_slash(app, signed_in):
    assert signed_in.get("/notices").status_code == 200


def test_notices_hide_other_audiences(app, signed_in, organizer):
    helpers.create_notice(app, organizer.id, "Faculty Secret", "Hidden.", audience="FACULTY")
    response = signed_in.get("/notices/")
    assert b"Faculty Secret" not in response.data


def test_notice_detail_for_another_audience_is_refused(app, signed_in, organizer):
    notice = helpers.create_notice(
        app, organizer.id, "Faculty Secret", "Hidden body.", audience="FACULTY"
    )
    response = signed_in.get(f"/notices/{notice.id}", follow_redirects=True)
    assert b"not published for your role" in response.data


def test_notices_require_authentication(app, organizer):
    notice = helpers.create_notice(app, organizer.id, "Public Notice", "Open to all.", audience="ALL")
    client = app.test_client()
    response = client.get(f"/notices/{notice.id}")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]
    assert client.get("/notices/").status_code == 302


def test_missing_notice_is_404(app, signed_in):
    assert signed_in.get("/notices/123456").status_code == 404