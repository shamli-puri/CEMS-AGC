"""Public landing / role aware home routes."""

from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user

main_bp = Blueprint("main", __name__)

ROLE_HOME = {
    "STUDENT": "student.dashboard",
    "FACULTY": "faculty.dashboard",
    "ORGANIZER": "organizer.dashboard",
}


@main_bp.route("/home")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("main.role_home"))
    return render_template("welcome.html")


@main_bp.route("/about")
def about():
    return render_template("about.html")


@main_bp.route("/role-home")
def role_home():
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_HOME.get(current_user.role, "auth.login")))
    return redirect(url_for("auth.login"))