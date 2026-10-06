"""Blueprint registration for CEMS - AGC Campus Event Management System."""

from .auth import auth_bp
from .events import events_bp
from .faculty import faculty_bp
from .main import main_bp
from .notices import notices_bp
from .organizer import organizer_bp
from .profile import profile_bp
from .student import student_bp

__all__ = [
    "auth_bp",
    "student_bp",
    "faculty_bp",
    "organizer_bp",
    "events_bp",
    "notices_bp",
    "profile_bp",
    "main_bp",
]