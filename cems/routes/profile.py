"""Shared profile routes for all three roles."""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func

from ..extensions import db
from ..models import (
    DEPARTMENTS,
    ROLE_FACULTY,
    ROLE_ORGANIZER,
    ROLE_STUDENT,
    YEARS_OF_STUDY,
    Certificate,
    Event,
    Feedback,
    Registration,
    User,
)
from ..services import domain
from ..utils.decorators import role_required
from ..utils.helpers import safe_next

profile_bp = Blueprint("profile", __name__)

ROLE_HOMES = {
    ROLE_STUDENT: "student.dashboard",
    ROLE_FACULTY: "faculty.dashboard",
    ROLE_ORGANIZER: "organizer.dashboard",
}


@profile_bp.route("/")
@role_required(ROLE_STUDENT, ROLE_FACULTY, ROLE_ORGANIZER)
def view():
    counts = {
        "registrations": Registration.query.filter_by(student_id=current_user.id).count()
        if current_user.is_student
        else 0,
        "events": Event.query.filter_by(organizer_id=current_user.id).count()
        if current_user.is_organizer
        else Event.query.count(),
        "certificates": Certificate.query.filter_by(student_id=current_user.id).count()
        if current_user.is_student
        else 0,
        "feedback": Feedback.query.filter_by(student_id=current_user.id).count()
        if current_user.is_student
        else Feedback.query.count(),
    }
    return render_template(
        "profile/view.html",
        counts=counts,
        profile_score=domain.profile_completeness(current_user),
        home_endpoint=ROLE_HOMES[current_user.role],
    )


@profile_bp.route("/edit", methods=["GET", "POST"])
@role_required(ROLE_STUDENT, ROLE_FACULTY, ROLE_ORGANIZER)
def edit():
    form = _form_from_user()

    if request.method == "GET":
        return render_template(
            "profile/edit.html",
            form=form,
            departments=DEPARTMENTS,
            years=YEARS_OF_STUDY,
            home_endpoint=ROLE_HOMES[current_user.role],
        )

    form = {
        "name": (request.form.get("name") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "department": (request.form.get("department") or "").strip(),
        "roll_number": (request.form.get("roll_number") or "").strip(),
        "year_of_study": (request.form.get("year_of_study") or "").strip(),
        "employee_id": (request.form.get("employee_id") or "").strip(),
        "designation": (request.form.get("designation") or "").strip(),
        "organization": (request.form.get("organization") or "").strip(),
        "bio": (request.form.get("bio") or "").strip(),
    }
    errors = []
    if len(form["name"]) < 3:
        errors.append("Full name must be at least 3 characters long.")
    if form["phone"] and (not form["phone"].isdigit() or not (7 <= len(form["phone"]) <= 15)):
        errors.append("Phone number must contain 7 to 15 digits.")
    if current_user.is_student and form["department"] and form["department"] not in DEPARTMENTS:
        errors.append("Please choose a valid department.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return (
            render_template(
                "profile/edit.html",
                form=form,
                departments=DEPARTMENTS,
                years=YEARS_OF_STUDY,
                home_endpoint=ROLE_HOMES[current_user.role],
            ),
            400,
        )

    current_user.name = form["name"]
    current_user.phone = form["phone"] or None
    current_user.bio = form["bio"] or None
    if current_user.is_student:
        current_user.department = form["department"] or current_user.department
        current_user.roll_number = form["roll_number"] or current_user.roll_number
        current_user.year_of_study = form["year_of_study"] or current_user.year_of_study
    elif current_user.is_faculty:
        current_user.department = form["department"] or current_user.department
        current_user.employee_id = form["employee_id"] or current_user.employee_id
        current_user.designation = form["designation"] or current_user.designation
    else:
        current_user.organization = form["organization"] or current_user.organization
        current_user.designation = form["designation"] or current_user.designation
    db.session.commit()

    flash("Profile updated successfully.", "success")
    return redirect(url_for("profile.view"))


@profile_bp.route("/password", methods=["GET", "POST"])
@role_required(ROLE_STUDENT, ROLE_FACULTY, ROLE_ORGANIZER)
def change_password():
    if request.method == "GET":
        return render_template(
            "profile/password.html", home_endpoint=ROLE_HOMES[current_user.role]
        )

    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    errors = []
    if not current_user.check_password(current_password):
        errors.append("Your current password is incorrect.")
    if len(new_password) < 6:
        errors.append("New password must be at least 6 characters long.")
    if new_password != confirm:
        errors.append("New password and confirmation do not match.")
    if new_password and new_password == current_password:
        errors.append("New password must be different from the current password.")

    if errors:
        for message in errors:
            flash(message, "danger")
        return (
            render_template(
                "profile/password.html", home_endpoint=ROLE_HOMES[current_user.role]
            ),
            400,
        )

    current_user.set_password(new_password)
    db.session.commit()
    flash("Password changed successfully. Use it the next time you log in.", "success")
    return redirect(url_for("profile.view"))


def _form_from_user():
    return {
        "name": current_user.name or "",
        "phone": current_user.phone or "",
        "department": current_user.department or "",
        "roll_number": current_user.roll_number or "",
        "year_of_study": current_user.year_of_study or "",
        "employee_id": current_user.employee_id or "",
        "designation": current_user.designation or "",
        "organization": current_user.organization or "",
        "bio": current_user.bio or "",
    }