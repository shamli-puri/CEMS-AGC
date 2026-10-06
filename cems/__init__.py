"""Application factory for CEMS - AGC Campus Event Management System."""

import logging
import os

from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, request, url_for
from flask_login import current_user

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from config import BASE_DIR, get_config  # noqa: E402

from .extensions import db  # noqa: E402
from .models import (  # noqa: E402
    EVENT_CATEGORIES,
    EVENT_STATUSES,
    ROLE_LABELS,
    ROLE_STUDENT,
)

ROLE_HOME_ENDPOINTS = {
    ROLE_STUDENT: "student.dashboard",
    "FACULTY": "faculty.dashboard",
    "ORGANIZER": "organizer.dashboard",
}


def create_app(config_name=None, **overrides):
    # Templates / static live at the project root, not inside the package.
    app = Flask(
        __name__,
        instance_relative_config=False,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )
    config_class = get_config(config_name)
    app.config.from_object(config_class)
    app.config.update(overrides)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    _configure_logging(app)

    db.init_app(app)

    _register_login(app)
    _register_blueprints(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_cli(app)
    _register_core_routes(app)

    from . import models  # noqa: F401  (ensure models are registered)

    with app.app_context():
        if app.config.get("DB_AUTO_CREATE", True):
            db.create_all()
        if app.config.get("SEED_ON_START", True):
            from .seed import seed_if_empty

            seed_if_empty()
        db.session.commit()

    return app


def _configure_logging(app):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s"))
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    app.logger.handlers = [handler]
    app.logger.setLevel(level)


def _register_login(app):
    from flask_login import LoginManager

    from .models import User

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    login_manager.session_protection = "basic"

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import flash

        flash("Please log in to continue.", "info")
        if request.blueprint == "student":
            return redirect(url_for("auth.login", role="student", next=request.full_path.rstrip("?")))
        if request.blueprint == "faculty":
            return redirect(url_for("auth.login", role="faculty", next=request.full_path.rstrip("?")))
        if request.blueprint == "organizer":
            return redirect(url_for("auth.login", role="organizer", next=request.full_path.rstrip("?")))
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


def _register_blueprints(app):
    from .routes.auth import auth_bp
    from .routes.events import events_bp
    from .routes.faculty import faculty_bp
    from .routes.main import main_bp
    from .routes.notices import notices_bp
    from .routes.organizer import organizer_bp
    from .routes.profile import profile_bp
    from .routes.student import student_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp, url_prefix="/student")
    app.register_blueprint(faculty_bp, url_prefix="/faculty")
    app.register_blueprint(organizer_bp, url_prefix="/organizer")
    app.register_blueprint(events_bp, url_prefix="/events")
    app.register_blueprint(notices_bp, url_prefix="/notices")
    app.register_blueprint(profile_bp, url_prefix="/profile")


def _register_template_helpers(app):
    from datetime import datetime

    from .models import EVENT_CANCELLED, ROLE_STUDENT
    from .utils.helpers import (
        format_date,
        format_date_time,
        format_time,
        initials_of,
        rating_stars,
        truncate,
    )

    @app.context_processor
    def inject_globals():
        dev_emails = []
        try:
            dev_emails = list(getattr(g, "dev_emails", []))
        except RuntimeError:
            dev_emails = []
        return {
            "APP_NAME": app.config["APP_NAME"],
            "APP_TITLE": app.config["APP_TITLE"],
            "ORG_NAME": app.config["ORG_NAME"],
            "ORG_SHORT": app.config["ORG_SHORT"],
            "ORG_PLACE": app.config["ORG_PLACE"],
            "APP_VERSION": app.config["APP_VERSION"],
            "EVENT_CATEGORIES": EVENT_CATEGORIES,
            "EVENT_STATUSES": EVENT_STATUSES,
            "ROLE_LABELS": ROLE_LABELS,
            "CANCELLED_STATUS": EVENT_CANCELLED,
            "STUDENT_ROLE": ROLE_STUDENT,
            "current_year": datetime.now().year,
            "dev_emails": dev_emails,
        }

    app.jinja_env.filters["date_fmt"] = format_date
    app.jinja_env.filters["datetime_fmt"] = format_date_time
    app.jinja_env.filters["time_fmt"] = format_time
    app.jinja_env.filters["initials"] = initials_of
    app.jinja_env.filters["stars"] = rating_stars
    app.jinja_env.filters["shorten"] = truncate


def _register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/error.html", code=403, title="Access denied",
                               message="Your role does not have permission to open this page."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/error.html", code=404, title="Page not found",
                               message="The page you are looking for does not exist or was moved."), 404

    @app.errorhandler(413)
    def too_large(error):
        return render_template("errors/error.html", code=413, title="File too large",
                               message="The uploaded file exceeds the 4 MB limit."), 413

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        app.logger.exception("Unhandled server error")
        return render_template("errors/error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. The issue has been logged."), 500


def _register_core_routes(app):
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("main.role_home"))
        return render_template("welcome.html")

    @app.route("/role-home")
    def role_home():
        if current_user.is_authenticated:
            endpoint = ROLE_HOME_ENDPOINTS.get(current_user.role, "auth.login")
            return redirect(url_for(endpoint))
        return redirect(url_for("auth.login"))

    @app.route("/healthz")
    def healthz():
        from .models import Event, Registration, User

        return {
            "status": "ok",
            "app": app.config["APP_NAME"],
            "title": app.config["APP_TITLE"],
            "users": User.query.count(),
            "events": Event.query.count(),
            "registrations": Registration.query.count(),
        }


def _register_cli(app):
    @app.cli.command("init-db")
    def init_db_command():
        """Create all tables."""
        db.create_all()
        print("Database tables created.")

    @app.cli.command("seed")
    def seed_command():
        """Populate demo accounts, events, notices and feedback."""
        from .seed import seed_demo_data

        result = seed_demo_data(force=True)
        print(f"Seeded: {result}")

    @app.cli.command("reset-db")
    def reset_db_command():
        """Drop and recreate every table (development helper)."""
        db.drop_all()
        db.create_all()
        print("Database reset complete.")