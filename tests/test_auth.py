"""Points 4-6: registration, three role logins, sessions and role isolation."""

import pytest
from conftest import PASSWORD, login, logout

from cems.extensions import db
from cems.models import ROLE_FACULTY, ROLE_ORGANIZER, ROLE_STUDENT, User


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def test_register_page_is_public(client):
    response = client.get("/auth/register")
    assert response.status_code == 200
    assert b"student" in response.data.lower()
    assert b"self register" in response.data.lower()


def test_valid_registration_creates_a_student_and_logs_in(client, app):
    response = client.post(
        "/auth/register",
        data={
            "name": "Riya Kapoor",
            "email": "Riya.Kapoor@agc.edu.in",
            "roll_number": "CSE-2024-1234",
            "department": "Computer Science & Engineering",
            "year_of_study": "2nd Year",
            "phone": "9876543210",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "agree": "1",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Student account created" in response.data

    with app.app_context():
        created = User.query.filter_by(email="riya.kapoor@agc.edu.in").first()
        assert created is not None
        assert created.role == ROLE_STUDENT
        assert created.check_password(PASSWORD)


def test_registration_normalises_email_to_lower_case(client, app):
    client.post(
        "/auth/register",
        data={
            "name": "Lower Case",
            "email": "MiXeD.CaSe@agc.edu.in",
            "roll_number": "CSE-2024-4321",
            "department": "Information Technology",
            "year_of_study": "1st Year",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "agree": "1",
        },
        follow_redirects=True,
    )
    with app.app_context():
        assert User.query.filter_by(email="mixed.case@agc.edu.in").first() is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Al"},
        {"email": "not-an-email"},
        {"roll_number": ""},
        {"department": ""},
        {"year_of_study": ""},
        {"password": "123"},
        {"confirm_password": "different"},
        {"agree": ""},
        {"phone": "12"},
    ],
)
def test_invalid_registration_is_rejected_with_400(client, overrides):
    payload = {
        "name": "Valid Name",
        "email": f"valid{abs(hash(str(overrides))) % 99999}@agc.edu.in",
        "roll_number": "CSE-2024-0001",
        "department": "Computer Science & Engineering",
        "year_of_study": "2nd Year",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "agree": "1",
    }
    payload.update(overrides)
    response = client.post("/auth/register", data=payload)
    assert response.status_code == 400


def test_duplicate_email_is_rejected(client, student):
    response = client.post(
        "/auth/register",
        data={
            "name": "Duplicate Student",
            "email": student.email,
            "roll_number": "CSE-2024-7777",
            "department": "Computer Science & Engineering",
            "year_of_study": "2nd Year",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "agree": "1",
        },
    )
    assert response.status_code == 400
    assert b"already exists" in response.data


def test_register_redirects_authenticated_users(client, student):
    login(client, student.email, role="student")
    response = client.get("/auth/register", follow_redirects=True)
    assert response.status_code == 200
    assert b"Student Dashboard" in response.data
    logout(client)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def test_login_landing_offers_exactly_three_roles(client):
    response = client.get("/auth/login")
    assert response.status_code == 200
    for label in (b"Student", b"Faculty", b"Organizer"):
        assert label in response.data


@pytest.mark.parametrize(
    "role_key", ["student", "faculty", "organizer"]
)
def test_each_role_login_page_renders(client, role_key):
    response = client.get(f"/auth/login/{role_key}")
    assert response.status_code == 200
    assert b"password" in response.data.lower()


def test_login_query_parameter_redirects_to_the_role_page(client):
    response = client.get("/auth/login?role=faculty")
    assert response.status_code == 302
    assert "/auth/login/faculty" in response.headers["Location"]


def test_unknown_login_type_falls_back_to_chooser(client):
    response = client.get("/auth/login/principal", follow_redirects=True)
    assert response.status_code == 200
    assert b"Organizer" in response.data


def test_account_type_helper(client):
    response = client.get("/auth/account-type?role=organizer")
    assert response.status_code == 302
    assert "/auth/login/organizer" in response.headers["Location"]


@pytest.mark.parametrize(
    "role_key,home",
    [
        ("student", "/student/dashboard"),
        ("faculty", "/faculty/dashboard"),
        ("organizer", "/organizer/dashboard"),
    ],
)
def test_each_role_logs_into_its_own_dashboard(
    client, app, role_key, home, student, faculty, organizer
):
    user = {"student": student, "faculty": faculty, "organizer": organizer}[role_key]
    response = client.post(
        f"/auth/login/{role_key}", data={"email": user.email, "password": PASSWORD}
    )
    assert response.status_code == 302
    assert home in response.headers["Location"]

    followed = client.get(home)
    assert followed.status_code == 200


def test_wrong_password_returns_401(client, student):
    response = client.post(
        "/auth/login/student", data={"email": student.email, "password": "wrong-pass"}
    )
    assert response.status_code == 401
    assert b"Incorrect password" in response.data


def test_unknown_email_returns_401(client, app):
    response = client.post(
        "/auth/login/student",
        data={"email": "nobody@agc.edu.in", "password": PASSWORD},
    )
    assert response.status_code == 401
    assert b"No account found" in response.data


def test_missing_fields_return_400(client):
    response = client.post("/auth/login/student", data={"email": "", "password": ""})
    assert response.status_code == 400


@pytest.mark.parametrize(
    "role_key,fixture_name",
    [("student", "faculty"), ("faculty", "student"), ("organizer", "student")],
)
def test_login_page_rejects_the_wrong_role_with_403(
    request, client, role_key, fixture_name, student, faculty
):
    other = request.getfixturevalue(fixture_name)
    response = client.post(
        f"/auth/login/{role_key}", data={"email": other.email, "password": PASSWORD}
    )
    assert response.status_code == 403
    assert b"registered as" in response.data


def test_deactivated_account_cannot_log_in(client, app, student):
    with app.app_context():
        # Bulk update: the session identity map is shared with the test client,
        # so a plain attribute assignment would be masked by the cached object.
        db.session.query(User).filter(User.id == student.id).update(
            {"is_active_account": False}
        )
        db.session.commit()
        db.session.expire_all()
    response = client.post(
        "/auth/login/student", data={"email": student.email, "password": PASSWORD},
        follow_redirects=True,
    )
    assert b"deactivated" in response.data
    assert client.get("/student/dashboard").status_code == 302


def test_email_match_is_case_insensitive(client, app, student):
    response = client.post(
        "/auth/login/student",
        data={"email": student.email.upper(), "password": PASSWORD},
    )
    assert response.status_code == 302
    assert "/student/dashboard" in response.headers["Location"]


def test_last_login_is_recorded(client, app, student):
    login(client, student.email, role="student")
    with app.app_context():
        assert db.session.get(User, student.id).last_login_at is not None


# ---------------------------------------------------------------------------
# Logout / session
# ---------------------------------------------------------------------------
def test_logout_ends_the_session(client, student):
    login(client, student.email, role="student")
    response = client.post("/auth/logout", follow_redirects=True)
    assert b"signed out" in response.data
    assert client.get("/student/dashboard").status_code == 302


def test_logout_accepts_the_trailing_slash_alias(client, student):
    login(client, student.email, role="student")
    response = client.get("/auth/logout/", follow_redirects=True)
    assert b"signed out" in response.data


def test_logout_when_not_logged_in(client):
    response = client.post("/auth/logout", follow_redirects=True)
    assert response.status_code == 200
    assert b"already signed out" in response.data


def test_role_home_sends_each_role_to_its_dashboard(app, student, faculty, organizer):
    for user, home in (
        (student, "/student/dashboard"),
        (faculty, "/faculty/dashboard"),
        (organizer, "/organizer/dashboard"),
    ):
        fresh = app.test_client()
        posted = fresh.post(
            f"/auth/login/{user.role.lower()}",
            data={"email": user.email, "password": PASSWORD},
        )
        assert posted.status_code == 302, user.role
        assert home in posted.headers["Location"], (
            user.role,
            posted.headers["Location"],
        )
        response = fresh.get("/role-home")
        assert response.status_code == 302
        assert home in response.headers["Location"], user.role


# ---------------------------------------------------------------------------
# Role isolation
# ---------------------------------------------------------------------------
STUDENT_ONLY = [
    "/student/dashboard",
    "/student/events",
    "/student/registrations",
    "/student/attendance",
    "/student/certificates",
    "/student/feedback",
    "/student/notices",
]
FACULTY_ONLY = [
    "/faculty/dashboard",
    "/faculty/events",
    "/faculty/attendance",
    "/faculty/feedback",
    "/faculty/notices",
]
ORGANIZER_ONLY = [
    "/organizer/dashboard",
    "/organizer/events",
    "/organizer/events/create",
    "/organizer/statistics",
    "/organizer/participants",
    "/organizer/notices/create",
]


def _login_as(client, user):
    client.post(
        f"/auth/login/{user.role.lower()}", data={"email": user.email, "password": PASSWORD}
    )


def test_anonymous_users_are_sent_to_the_matching_login_page(client):
    for url in STUDENT_ONLY:
        response = client.get(url)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]
    for url in FACULTY_ONLY + ORGANIZER_ONLY:
        assert client.get(url).status_code == 302


def test_student_cannot_open_faculty_or_organizer_pages(client, student):
    _login_as(client, student)
    for url in FACULTY_ONLY + ORGANIZER_ONLY:
        response = client.get(url)
        assert response.status_code == 302, url
        assert "/student/dashboard" in response.headers["Location"], url


def test_faculty_cannot_open_student_or_organizer_pages(client, faculty):
    _login_as(client, faculty)
    for url in STUDENT_ONLY + ORGANIZER_ONLY:
        response = client.get(url)
        assert response.status_code == 302, url
        assert "/faculty/dashboard" in response.headers["Location"], url


def test_organizer_cannot_open_student_or_faculty_pages(client, organizer):
    _login_as(client, organizer)
    for url in STUDENT_ONLY + FACULTY_ONLY:
        response = client.get(url)
        assert response.status_code == 302, url
        assert "/organizer/dashboard" in response.headers["Location"], url


def test_student_cannot_post_to_organizer_actions(client, student, future_event):
    _login_as(client, student)
    for url in (
        f"/organizer/events/{future_event.id}/cancel",
        f"/organizer/events/{future_event.id}/delete",
        "/organizer/notices/create",
    ):
        response = client.post(url)
        assert response.status_code in (302, 405), url
        assert "/student/dashboard" in response.headers.get("Location", "/student/dashboard")


def test_role_constants_cover_every_account(student, faculty, organizer):
    assert student.role == ROLE_STUDENT
    assert faculty.role == ROLE_FACULTY
    assert organizer.role == ROLE_ORGANIZER