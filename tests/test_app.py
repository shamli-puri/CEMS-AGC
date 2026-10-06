"""Point 1-3: application factory, configuration, health endpoint, public pages, CLI."""

import os

from cems import create_app
from cems.extensions import db
from cems.models import ROLE_STUDENT


def test_create_app_registers_blueprints(app):
    names = set(app.blueprints)
    assert {
        "main",
        "auth",
        "student",
        "faculty",
        "organizer",
        "events",
        "notices",
        "profile",
    } <= names


def test_three_roles_only_and_no_admin(app):
    from cems.models import ALL_ROLES, ROLE_FACULTY, ROLE_ORGANIZER

    assert ALL_ROLES == (ROLE_STUDENT, ROLE_FACULTY, ROLE_ORGANIZER)
    assert "ADMIN" not in ALL_ROLES
    assert "ADMIN" not in app.jinja_env.globals


def test_app_exposes_full_route_surface(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    for expected in (
        "/",
        "/healthz",
        "/about",
        "/auth/login",
        "/auth/login/student",
        "/auth/login/faculty",
        "/auth/login/organizer",
        "/auth/register",
        "/auth/logout",
        "/student/dashboard",
        "/faculty/dashboard",
        "/organizer/dashboard",
        "/organizer/events/create",
        "/events/catalogue",
        "/events/search",
        "/notices/",
        "/profile/edit",
    ):
        assert expected in rules, expected


def test_no_duplicate_rule_endpoints(app):
    pairs = [(rule.rule, rule.endpoint) for rule in app.url_map.iter_rules()]
    assert len(pairs) == len(set(pairs))


def test_healthz_reports_counts(client, student):
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["app"] == "CEMS"
    assert payload["users"] >= 1


def test_index_and_role_home_redirect_anonymous_users(client):
    # "/" renders the public welcome screen; "/role-home" still funnels to login.
    welcome = client.get("/")
    assert welcome.status_code == 200
    assert b"CEMS" in welcome.data
    response = client.get("/role-home")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_welcome_landing_page_is_public(client):
    response = client.get("/home")
    assert response.status_code == 200
    assert b"CEMS" in response.data


def test_about_page_is_public(client):
    response = client.get("/about")
    assert response.status_code == 200
    assert b"CEMS" in response.data


def test_branding_assets_are_local_and_there_is_no_bootstrap_cdn(client):
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/main.js").status_code == 200
    assert client.get("/static/images/agc-logo.svg").status_code == 200
    assert client.get("/static/images/favicon.svg").status_code == 200
    page = client.get("/home").data.lower()
    assert b"cdn.jsdelivr.net" not in page
    assert b"cdnjs.cloudflare.com" not in page
    assert b"stackpath.bootstrapcdn.com" not in page
    assert b"/static/css/style.css" in page


def test_navy_and_gold_branding_present_in_stylesheet(client):
    css = client.get("/static/css/style.css").data.decode("utf-8").lower()
    assert "#1e40af" in css
    assert "#c9a227" in css


def test_custom_jinja_filters_are_registered(app):
    for name in ("date_fmt", "datetime_fmt", "time_fmt", "initials", "stars", "shorten"):
        assert name in app.jinja_env.filters


def test_custom_404_and_403_pages(client):
    missing = client.get("/definitely-not-a-real-page")
    assert missing.status_code == 404
    assert b"404" in missing.data

    forbidden = client.get("/events/999999")
    assert forbidden.status_code == 404
    assert b"404" in forbidden.data


def test_error_page_template_used_for_forbidden(client, student):
    client.post("/auth/login/student", data={"email": student.email, "password": "agc@2026"})
    forbidden = client.get("/organizer/statistics", follow_redirects=True)
    assert forbidden.status_code == 200
    assert b"CEMS" in forbidden.data


def test_cli_commands_are_registered(app):
    assert {"init-db", "seed", "reset-db"} <= set(app.cli.commands)


def test_cli_init_db_and_reset_db_run(runner):
    result = runner.invoke(args=["init-db"])
    assert result.exit_code == 0
    assert "created" in result.output.lower()
    result = runner.invoke(args=["reset-db"])
    assert result.exit_code == 0


def test_cli_seed_creates_demo_accounts(runner, app):
    result = runner.invoke(args=["seed"])
    assert result.exit_code == 0
    from cems.models import ROLE_FACULTY, ROLE_ORGANIZER, User

    with app.app_context():
        emails = {u.email for u in User.query.all()}
        assert "student@agc.edu.in" in emails
        assert "faculty@agc.edu.in" in emails
        assert "organizer@agc.edu.in" in emails
        assert User.query.filter_by(role=ROLE_FACULTY).count() >= 1
        assert User.query.filter_by(role=ROLE_ORGANIZER).count() >= 1


def test_development_email_fallback_writes_log_file(app, tmp_path):
    from cems.services import email_service

    log_file = tmp_path / "emails.log"
    app.config["MAIL_LOG_FILE"] = str(log_file)
    app.config["MAIL_ENABLED"] = False

    with app.test_request_context():
        result = email_service.send_email(
            subject="[CEMS-AGC] Test subject", recipients="student@agc.edu.in", body="Body line."
        )

    assert result["ok"] is True
    assert result["delivered"] is False
    assert "development message" in result["reason"]
    assert log_file.exists()
    assert "Test subject" in log_file.read_text(encoding="utf-8")


def test_upload_folder_and_instance_folder_exist(app):
    assert os.path.isdir(app.instance_path)
    assert os.path.isdir(app.config["UPLOAD_FOLDER"])


def test_shell_context_exposes_models(app):
    with app.app_context():
        context = app.make_shell_context()
    for key in ("db", "User", "Event", "Registration"):
        assert key in context, key
    assert context["db"] is db