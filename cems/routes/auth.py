"""Authentication routes: three role registration, three role logins, logout."""

import re

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func

from ..extensions import db
from ..models import (
    DEPARTMENTS,
    ROLE_FACULTY,
    ROLE_ORGANIZER,
    ROLE_STUDENT,
    YEARS_OF_STUDY,
    User,
    utcnow,
)
from ..utils.decorators import role_required
from ..utils.helpers import safe_next

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

ROLE_TABS = {
    "student": (ROLE_STUDENT, "Student", "student"),
    "faculty": (ROLE_FACULTY, "Faculty", "faculty"),
    "organizer": (ROLE_ORGANIZER, "Organizer", "organizer"),
}

LOGIN_WELCOME = {
    ROLE_STUDENT: "Student login",
    ROLE_FACULTY: "Faculty login",
    ROLE_ORGANIZER: "Organizer login",
}

REGISTER_WELCOME = {
    ROLE_STUDENT: "Create student account",
    ROLE_FACULTY: "Create faculty account",
    ROLE_ORGANIZER: "Create organizer account",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _valid_email(value):
    return bool(value and EMAIL_RE.match(value.strip()))


@auth_bp.route("/login")
def login():
    """Role chooser / login landing page."""
    if current_user.is_authenticated:
        return redirect(url_for("main.role_home"))
    requested = (request.args.get("role") or "").strip().lower()
    if requested in ROLE_TABS:
        return redirect(url_for(f"auth.login_{requested}"))
    return render_template(
        "auth/login_select.html", role_tabs=ROLE_TABS, app_name=current_app.config["APP_NAME"]
    )


@auth_bp.route("/login/<role>")
def login_role(role):
    if current_user.is_authenticated:
        return redirect(url_for("main.role_home"))
    if role not in ROLE_TABS:
        flash("Unknown login type. Choose Student, Faculty or Organizer.", "danger")
        return redirect(url_for("auth.login"))
    role_value, role_label, icon = ROLE_TABS[role]
    if request.method == "GET":
        return render_template(
            "auth/login.html",
            role_key=role,
            role_value=role_value,
            role_label=role_label,
            role_icon=icon,
            welcome=LOGIN_WELCOME[role_value],
            form={},
        )

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    remember = bool(request.form.get("remember"))
    next_url = safe_next(request.form.get("next"), "main.role_home")

    errors = []
    if not email:
        errors.append("Email address is required.")
    elif not _valid_email(email):
        errors.append("Enter a valid email address (example: name@agc.edu.in).")
    if not password:
        errors.append("Password is required.")
    if errors:
        for message in errors:
            flash(message, "danger")
        return (
            render_template(
                "auth/login.html",
                role_key=role,
                role_value=role_value,
                role_label=role_label,
                role_icon=icon,
                welcome=LOGIN_WELCOME[role_value],
                form={"email": email, "remember": remember},
            ),
            400,
        )

    user = User.query.filter(func.lower(User.email) == email).first()
    if user is None:
        flash("No account found with that email address.", "danger")
        return (
            render_template(
                "auth/login.html",
                role_key=role,
                role_value=role_value,
                role_label=role_label,
                role_icon=icon,
                welcome=LOGIN_WELCOME[role_value],
                form={"email": email, "remember": remember},
            ),
            401,
        )
    if not user.check_password(password):
        flash("Incorrect password. Please try again.", "danger")
        return (
            render_template(
                "auth/login.html",
                role_key=role,
                role_value=role_value,
                role_label=role_label,
                role_icon=icon,
                welcome=LOGIN_WELCOME[role_value],
                form={"email": email, "remember": remember},
            ),
            401,
        )
    if user.role != role_value:
        flash(
            f"This account is registered as {user.role_label}. "
            f"Please use the {user.role_label} login page.",
            "danger",
        )
        return (
            render_template(
                "auth/login.html",
                role_key=role,
                role_value=role_value,
                role_label=role_label,
                role_icon=icon,
                welcome=LOGIN_WELCOME[role_value],
                form={"email": email, "remember": remember},
            ),
            403,
        )
    if not user.is_active_account:
        flash("This account has been deactivated. Contact the event organizer.", "danger")
        return redirect(url_for(f"auth.login_{role}"))

    user.last_login_at = utcnow()
    db.session.commit()
    login_user(user, remember=remember)
    session.permanent = True
    flash(f"Welcome back, {user.name.split()[0]}! You are signed in as {user.role_label}.", "success")
    return redirect(next_url or url_for(_home_endpoint(user.role)))


def _home_endpoint(role):
    return {
        ROLE_STUDENT: "student.dashboard",
        ROLE_FACULTY: "faculty.dashboard",
        ROLE_ORGANIZER: "organizer.dashboard",
    }.get(role, "auth.login")


# Explicit friendly URLs: /auth/login/student, /auth/login/faculty, ...
auth_bp.add_url_rule(
    "/login/student",
    endpoint="login_student",
    view_func=lambda: _role_login_view("student"),
    methods=["GET", "POST"],
)
auth_bp.add_url_rule(
    "/login/faculty",
    endpoint="login_faculty",
    view_func=lambda: _role_login_view("faculty"),
    methods=["GET", "POST"],
)
auth_bp.add_url_rule(
    "/login/organizer",
    endpoint="login_organizer",
    view_func=lambda: _role_login_view("organizer"),
    methods=["GET", "POST"],
)


def _role_login_view(role):
    return login_role(role)


@auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/register/student", methods=["GET", "POST"])
def register_student():
    """Student self-registration."""
    if current_user.is_authenticated:
        return redirect(url_for("main.role_home"))

    form = {}
    if request.method == "GET":
        return render_template(
            "auth/register_student.html",
            form=form,
            departments=DEPARTMENTS,
            years=YEARS_OF_STUDY,
        )

    form = {
        "name": (request.form.get("name") or "").strip(),
        "email": (request.form.get("email") or "").strip().lower(),
        "roll_number": (request.form.get("roll_number") or "").strip(),
        "department": (request.form.get("department") or "").strip(),
        "year_of_study": (request.form.get("year_of_study") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "bio": (request.form.get("bio") or "").strip(),
    }
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""
    agree = request.form.get("agree")

    errors = []
    if not form["name"] or len(form["name"]) < 3:
        errors.append("Full name is required (minimum 3 characters).")
    if not _valid_email(form["email"]):
        errors.append("A valid email address is required (example: name@agc.edu.in).")
    if not form["roll_number"]:
        errors.append("Roll number / enrollment number is required.")
    if not form["department"]:
        errors.append("Please select your department.")
    if not form["year_of_study"]:
        errors.append("Please select your year of study.")
    if form["phone"] and (not form["phone"].isdigit() or not (7 <= len(form["phone"]) <= 15)):
        errors.append("Phone number must contain 7 to 15 digits.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters long.")
    if password != confirm:
        errors.append("Password and confirmation password do not match.")
    if not agree:
        errors.append("Please accept the AGC event participation guidelines.")
    if _valid_email(form["email"]) and User.query.filter(
        func.lower(User.email) == form["email"]
    ).first():
        errors.append("An account with this email address already exists.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return (
            render_template(
                "auth/register_student.html",
                form=form,
                departments=DEPARTMENTS,
                years=YEARS_OF_STUDY,
            ),
            400,
        )

    user = User(
        name=form["name"],
        email=form["email"],
        role=ROLE_STUDENT,
        roll_number=form["roll_number"],
        department=form["department"],
        year_of_study=form["year_of_study"],
        phone=form["phone"] or None,
        bio=form["bio"] or None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    from ..services.email_service import send_email

    send_email(
        subject="[CEMS-AGC] Student account created",
        recipients=user.email,
        body=(
            f"Dear {user.name},\n\n"
            f"Your CEMS student account has been created successfully.\n"
            f"Email: {user.email}\n\n"
            f"You can now browse AGC campus events and register for them from the dashboard.\n\n"
            f"-- CEMS | AGC Campus Event Management System\n"
            f"   Amritsar Group of Colleges, Amritsar"
        ),
    )

    login_user(user)
    session.permanent = True
    flash("Student account created. Welcome to CEMS - AGC!", "success")
    return redirect(url_for("student.dashboard"))


@auth_bp.route("/register/faculty", methods=["GET", "POST"])
def register_faculty():
    """Faculty self-registration."""
    if current_user.is_authenticated:
        return redirect(url_for("main.role_home"))

    form = {}
    if request.method == "GET":
        return render_template(
            "auth/register_faculty.html",
            form=form,
            departments=DEPARTMENTS,
        )

    form = {
        "name": (request.form.get("name") or "").strip(),
        "email": (request.form.get("email") or "").strip().lower(),
        "employee_id": (request.form.get("employee_id") or "").strip(),
        "designation": (request.form.get("designation") or "").strip(),
        "department": (request.form.get("department") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "bio": (request.form.get("bio") or "").strip(),
    }
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""
    agree = request.form.get("agree")

    errors = []
    if not form["name"] or len(form["name"]) < 3:
        errors.append("Full name is required (minimum 3 characters).")
    if not _valid_email(form["email"]):
        errors.append("A valid email address is required (example: name@agc.edu.in).")
    if not form["employee_id"]:
        errors.append("Employee ID is required.")
    if not form["designation"]:
        errors.append("Designation is required (e.g., Assistant Professor, Associate Professor, Professor).")
    if not form["department"]:
        errors.append("Please select your department.")
    if form["phone"] and (not form["phone"].isdigit() or not (7 <= len(form["phone"]) <= 15)):
        errors.append("Phone number must contain 7 to 15 digits.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters long.")
    if password != confirm:
        errors.append("Password and confirmation password do not match.")
    if not agree:
        errors.append("Please accept the AGC event participation guidelines.")
    if _valid_email(form["email"]) and User.query.filter(
        func.lower(User.email) == form["email"]
    ).first():
        errors.append("An account with this email address already exists.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return (
            render_template(
                "auth/register_faculty.html",
                form=form,
                departments=DEPARTMENTS,
            ),
            400,
        )

    user = User(
        name=form["name"],
        email=form["email"],
        role=ROLE_FACULTY,
        employee_id=form["employee_id"],
        designation=form["designation"],
        department=form["department"],
        phone=form["phone"] or None,
        bio=form["bio"] or None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    from ..services.email_service import send_email

    send_email(
        subject="[CEMS-AGC] Faculty account created",
        recipients=user.email,
        body=(
            f"Dear {user.name},\n\n"
            f"Your CEMS faculty account has been created successfully.\n"
            f"Email: {user.email}\n\n"
            f"You can now access the faculty dashboard to monitor events, verify attendance, and view feedback.\n\n"
            f"-- CEMS | AGC Campus Event Management System\n"
            f"   Amritsar Group of Colleges, Amritsar"
        ),
    )

    login_user(user)
    session.permanent = True
    flash("Faculty account created. Welcome to CEMS - AGC!", "success")
    return redirect(url_for("faculty.dashboard"))


@auth_bp.route("/register/organizer", methods=["GET", "POST"])
def register_organizer():
    """Organizer self-registration."""
    if current_user.is_authenticated:
        return redirect(url_for("main.role_home"))

    form = {}
    if request.method == "GET":
        return render_template(
            "auth/register_organizer.html",
            form=form,
        )

    form = {
        "name": (request.form.get("name") or "").strip(),
        "email": (request.form.get("email") or "").strip().lower(),
        "designation": (request.form.get("designation") or "").strip(),
        "organization": (request.form.get("organization") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "bio": (request.form.get("bio") or "").strip(),
    }
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm_password") or ""
    agree = request.form.get("agree")

    errors = []
    if not form["name"] or len(form["name"]) < 3:
        errors.append("Full name is required (minimum 3 characters).")
    if not _valid_email(form["email"]):
        errors.append("A valid email address is required (example: name@agc.edu.in).")
    if not form["designation"]:
        errors.append("Designation is required (e.g., Event Coordinator, Technical Secretary).")
    if not form["organization"]:
        errors.append("Organization/Committee name is required (e.g., AGC Technical & Cultural Committee).")
    if form["phone"] and (not form["phone"].isdigit() or not (7 <= len(form["phone"]) <= 15)):
        errors.append("Phone number must contain 7 to 15 digits.")
    if len(password) < 6:
        errors.append("Password must be at least 6 characters long.")
    if password != confirm:
        errors.append("Password and confirmation password do not match.")
    if not agree:
        errors.append("Please accept the AGC event participation guidelines.")
    if _valid_email(form["email"]) and User.query.filter(
        func.lower(User.email) == form["email"]
    ).first():
        errors.append("An account with this email address already exists.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return (
            render_template(
                "auth/register_organizer.html",
                form=form,
            ),
            400,
        )

    user = User(
        name=form["name"],
        email=form["email"],
        role=ROLE_ORGANIZER,
        designation=form["designation"],
        organization=form["organization"],
        phone=form["phone"] or None,
        bio=form["bio"] or None,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    from ..services.email_service import send_email

    send_email(
        subject="[CEMS-AGC] Organizer account created",
        recipients=user.email,
        body=(
            f"Dear {user.name},\n\n"
            f"Your CEMS organizer account has been created successfully.\n"
            f"Email: {user.email}\n\n"
            f"You can now create and manage events, handle registrations, verify attendance, and issue certificates.\n\n"
            f"-- CEMS | AGC Campus Event Management System\n"
            f"   Amritsar Group of Colleges, Amritsar"
        ),
    )

    login_user(user)
    session.permanent = True
    flash("Organizer account created. Welcome to CEMS - AGC!", "success")
    return redirect(url_for("organizer.dashboard"))


@auth_bp.route("/logout", methods=["GET", "POST"])
@auth_bp.route("/logout/", methods=["GET", "POST"])
def logout():
    if current_user.is_authenticated:
        role = current_user.role
        name = current_user.name.split()[0]
        logout_user()
        session.clear()
        flash(f"Goodbye, {name}. You have been signed out of CEMS.", "info")
    else:
        flash("You are already signed out.", "info")
    return redirect(url_for("main.home"))


@auth_bp.route("/account-type")
def account_type():
    """Small helper used by the login page tabs."""
    role_key = (request.args.get("role") or "").lower()
    if role_key in ROLE_TABS:
        return redirect(url_for(f"auth.login_{role_key}"))
    return redirect(url_for("auth.login"))


def get_dev_emails():
    return list(getattr(g, "dev_emails", []))


__all__ = ["auth_bp", "role_required"]