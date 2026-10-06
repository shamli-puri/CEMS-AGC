"""Database models for CEMS - AGC Campus Event Management System.

Exactly three user roles exist: STUDENT, FACULTY and ORGANIZER.
There is deliberately no ADMIN role.
"""

import secrets
import string
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

# --------------------------------------------------------------------------
# Role constants
# --------------------------------------------------------------------------
ROLE_STUDENT = "STUDENT"
ROLE_FACULTY = "FACULTY"
ROLE_ORGANIZER = "ORGANIZER"
ALL_ROLES = (ROLE_STUDENT, ROLE_FACULTY, ROLE_ORGANIZER)

ROLE_LABELS = {
    ROLE_STUDENT: "Student",
    ROLE_FACULTY: "Faculty",
    ROLE_ORGANIZER: "Organizer",
}

# --------------------------------------------------------------------------
# Event / registration / attendance / notice constants
# --------------------------------------------------------------------------
EVENT_UPCOMING = "UPCOMING"
EVENT_ONGOING = "ONGOING"
EVENT_COMPLETED = "COMPLETED"
EVENT_CANCELLED = "CANCELLED"
EVENT_STATUSES = (EVENT_UPCOMING, EVENT_ONGOING, EVENT_COMPLETED, EVENT_CANCELLED)

EVENT_CATEGORIES = (
    "Technical",
    "Cultural",
    "Sports",
    "Workshop",
    "Seminar",
    "Community",
    "Placement",
)

DEPARTMENTS = (
    "Computer Science & Engineering",
    "Information Technology",
    "Electronics & Communication",
    "Mechanical Engineering",
    "Civil Engineering",
    "Electrical Engineering",
    "Management Studies",
    "Computer Applications (BCA)",
    "Other",
)

YEARS_OF_STUDY = ("1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year")

REG_CONFIRMED = "CONFIRMED"
REG_CANCELLED = "CANCELLED"

ATT_PRESENT = "PRESENT"
ATT_ABSENT = "ABSENT"

ATTENDANCE_PRESENT = "Present"
ATTENDANCE_ABSENT = "Absent"
ATTENDANCE_PENDING = "Not Marked"

AUDIENCE_ALL = "ALL"
AUDIENCE_STUDENT = "STUDENT"
AUDIENCE_FACULTY = "FACULTY"
AUDIENCE_ORGANIZER = "ORGANIZER"
AUDIENCES = (AUDIENCE_ALL, AUDIENCE_STUDENT, AUDIENCE_FACULTY, AUDIENCE_ORGANIZER)

ALPHABET = string.ascii_uppercase + string.digits


def utcnow():
    """Naive UTC datetime (SQLite friendly)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_code(prefix, length=6):
    """Human friendly unique code, e.g. AGC-REG-7F3K9Q."""
    body = "".join(secrets.choice(ALPHABET) for _ in range(length))
    return f"{prefix}-{body}"


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --------------------------------------------------------------------------
# User
# --------------------------------------------------------------------------
class User(db.Model, UserMixin, TimestampMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)

    phone = db.Column(db.String(25))
    department = db.Column(db.String(80))
    roll_number = db.Column(db.String(40))
    year_of_study = db.Column(db.String(20))
    employee_id = db.Column(db.String(40))
    designation = db.Column(db.String(80))
    organization = db.Column(db.String(120))
    bio = db.Column(db.Text)

    is_active_account = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime)

    # relationships
    organized_events = db.relationship(
        "Event",
        back_populates="organizer",
        foreign_keys="Event.organizer_id",
        cascade="all, delete-orphan",
    )
    registrations = db.relationship(
        "Registration",
        back_populates="student",
        foreign_keys="Registration.student_id",
        cascade="all, delete-orphan",
    )
    certificates = db.relationship(
        "Certificate",
        back_populates="student",
        foreign_keys="Certificate.student_id",
        cascade="all, delete-orphan",
    )
    feedback_entries = db.relationship(
        "Feedback",
        back_populates="student",
        foreign_keys="Feedback.student_id",
        cascade="all, delete-orphan",
    )
    notices = db.relationship(
        "Notice", back_populates="author", foreign_keys="Notice.author_id", cascade="all, delete-orphan"
    )

    # ------------------------------------------------------------------
    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        if not raw_password or not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_student(self):
        return self.role == ROLE_STUDENT

    @property
    def is_faculty(self):
        return self.role == ROLE_FACULTY

    @property
    def is_organizer(self):
        return self.role == ROLE_ORGANIZER

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def initials(self):
        parts = [p for p in (self.name or "").split() if p]
        if not parts:
            return "AG"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def display_meta(self):
        """Small role specific line shown under the name."""
        if self.is_student:
            bits = [b for b in (self.roll_number, self.department, self.year_of_study) if b]
            return " | ".join(bits) if bits else "Student, AGC"
        if self.is_faculty:
            bits = [b for b in (self.designation, self.department, self.employee_id) if b]
            return " | ".join(bits) if bits else "Faculty, AGC"
        bits = [b for b in (self.organization, self.designation) if b]
        return " | ".join(bits) if bits else "Event Organizer, AGC"

    def __repr__(self):
        return f"<User {self.id} {self.email} {self.role}>"


# --------------------------------------------------------------------------
# Event
# --------------------------------------------------------------------------
class Event(db.Model, TimestampMixin):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    event_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    venue = db.Column(db.String(160), nullable=False)
    organizer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    max_capacity = db.Column(db.Integer, nullable=False, default=100)
    registration_deadline = db.Column(db.DateTime, nullable=False)
    image_filename = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default=EVENT_UPCOMING, index=True)
    requires_attendance = db.Column(db.Boolean, default=True, nullable=False)
    certificate_eligible = db.Column(db.Boolean, default=True, nullable=False)
    certificate_minutes = db.Column(db.Integer, default=0, nullable=False)

    organizer = db.relationship("User", back_populates="organized_events", foreign_keys=[organizer_id])
    registrations = db.relationship(
        "Registration", back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )
    feedback_entries = db.relationship("Feedback", back_populates="event", cascade="all, delete-orphan")
    certificates = db.relationship("Certificate", back_populates="event", cascade="all, delete-orphan")

    # ------------------------------------------------------------------
    @property
    def start_datetime(self):
        return datetime.combine(self.event_date, self.start_time)

    @property
    def end_datetime(self):
        return datetime.combine(self.event_date, self.end_time)

    @property
    def time_range(self):
        return f"{self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"

    @property
    def is_cancelled(self):
        return self.status == EVENT_CANCELLED

    @property
    def is_completed(self):
        return self.status == EVENT_COMPLETED

    def confirmed_registrations(self):
        return [r for r in self.registrations if r.status == REG_CONFIRMED]

    def active_registration_count(self):
        return len(self.confirmed_registrations())

    def attendee_count(self):
        return len([r for r in self.registrations if r.attendance and r.attendance.status == ATT_PRESENT])

    @property
    def seats_taken(self):
        return self.active_registration_count()

    @property
    def seats_left(self):
        return max(self.max_capacity - self.seats_taken, 0)

    @property
    def is_full(self):
        return self.seats_taken >= self.max_capacity

    @property
    def registration_closed(self):
        return self.registration_deadline is not None and self.registration_deadline < utcnow()

    @property
    def registration_open(self):
        return not self.registration_closed and not self.is_cancelled and not self.is_full

    @property
    def is_past(self):
        return self.end_datetime < utcnow()

    def registration_state(self):
        """Returns (is_open: bool, reason: str)"""
        if self.is_cancelled:
            return False, "This event has been cancelled."
        if self.registration_closed:
            return False, "The registration deadline for this event has passed."
        if self.is_full:
            return False, "This event has reached its maximum capacity."
        if self.is_past:
            return False, "This event has already taken place."
        return True, "Registration is open."

    def status_class(self):
        return {
            EVENT_UPCOMING: "badge-upcoming",
            EVENT_ONGOING: "badge-ongoing",
            EVENT_COMPLETED: "badge-completed",
            EVENT_CANCELLED: "badge-cancelled",
        }.get(self.status, "badge-muted")

    def refresh_status(self):
        """Derive UPCOMING / ONGOING / COMPLETED from the current clock."""
        if self.status == EVENT_CANCELLED:
            return self.status
        now = utcnow()
        if now < self.start_datetime:
            self.status = EVENT_UPCOMING
        elif self.start_datetime <= now < self.end_datetime:
            self.status = EVENT_ONGOING
        else:
            self.status = EVENT_COMPLETED
        return self.status

    def feedback_count(self):
        return len(self.feedback_entries)

    def average_rating(self):
        ratings = [f.rating for f in self.feedback_entries if f.rating]
        if not ratings:
            return 0.0
        return round(sum(ratings) / len(ratings), 2)

    def __repr__(self):
        return f"<Event {self.id} {self.title!r} {self.status}>"


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
class Registration(db.Model, TimestampMixin):
    __tablename__ = "registrations"

    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=REG_CONFIRMED, index=True)
    registered_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    cancelled_at = db.Column(db.DateTime)
    seat_note = db.Column(db.String(120))

    student = db.relationship("User", back_populates="registrations", foreign_keys=[student_id])
    event = db.relationship("Event", back_populates="registrations")
    attendance = db.relationship(
        "Attendance",
        back_populates="registration",
        uselist=False,
        cascade="all, delete-orphan",
    )
    feedback = db.relationship(
        "Feedback",
        back_populates="registration",
        uselist=False,
        cascade="all, delete-orphan",
    )
    certificate = db.relationship(
        "Certificate",
        back_populates="registration",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def is_cancelled(self):
        return self.status == REG_CANCELLED

    @property
    def is_confirmed(self):
        return self.status == REG_CONFIRMED

    @property
    def attendance_status(self):
        if self.attendance:
            return (
                ATTENDANCE_PRESENT
                if self.attendance.status == ATT_PRESENT
                else ATTENDANCE_ABSENT
            )
        return ATTENDANCE_PENDING

    @property
    def attendance_class(self):
        if not self.attendance:
            return "badge-muted"
        return "badge-success" if self.attendance.status == ATT_PRESENT else "badge-danger"

    def status_class(self):
        return "badge-success" if self.is_confirmed else "badge-danger"

    def __repr__(self):
        return f"<Registration {self.registration_id} student={self.student_id} event={self.event_id}>"


# --------------------------------------------------------------------------
# Attendance
# --------------------------------------------------------------------------
class Attendance(db.Model, TimestampMixin):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(
        db.Integer, db.ForeignKey("registrations.id"), unique=True, nullable=False, index=True
    )
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default=ATT_PRESENT, index=True)
    marked_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    marked_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    remarks = db.Column(db.String(160))

    registration = db.relationship("Registration", back_populates="attendance")
    student = db.relationship("User", foreign_keys=[student_id])
    event = db.relationship("Event", foreign_keys=[event_id])
    marked_by = db.relationship("User", foreign_keys=[marked_by_id])

    @property
    def status_label(self):
        return ATTENDANCE_PRESENT if self.status == ATT_PRESENT else ATTENDANCE_ABSENT

    def status_class(self):
        return "badge-success" if self.status == ATT_PRESENT else "badge-danger"

    def __repr__(self):
        return f"<Attendance reg={self.registration_id} {self.status}>"


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------
class Feedback(db.Model, TimestampMixin):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    registration_id = db.Column(
        db.Integer, db.ForeignKey("registrations.id"), unique=True, nullable=False, index=True
    )
    rating = db.Column(db.Integer, nullable=False)
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    student = db.relationship("User", back_populates="feedback_entries", foreign_keys=[student_id])
    event = db.relationship("Event", back_populates="feedback_entries")
    registration = db.relationship("Registration", back_populates="feedback")

    __table_args__ = (db.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),)

    @property
    def stars(self):
        return [("filled" if i <= self.rating else "empty") for i in range(1, 6)]

    @property
    def student_initials(self):
        return self.student.initials if self.student else "AG"

    def __repr__(self):
        return f"<Feedback event={self.event_id} rating={self.rating}>"


# --------------------------------------------------------------------------
# Notice
# --------------------------------------------------------------------------
class Notice(db.Model, TimestampMixin):
    __tablename__ = "notices"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    audience = db.Column(db.String(20), nullable=False, default=AUDIENCE_ALL, index=True)
    is_important = db.Column(db.Boolean, default=False, nullable=False, index=True)
    published_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    author = db.relationship("User", back_populates="notices", foreign_keys=[author_id])

    @property
    def author_name(self):
        return self.author.name if self.author else "AGC Administration"

    @property
    def importance_class(self):
        return "badge-important" if self.is_important else "badge-info"

    def visible_to(self, role):
        return self.audience == AUDIENCE_ALL or self.audience == role

    def __repr__(self):
        return f"<Notice {self.id} {self.title!r} important={self.is_important}>"


# --------------------------------------------------------------------------
# Certificate
# --------------------------------------------------------------------------
class Certificate(db.Model, TimestampMixin):
    __tablename__ = "certificates"

    id = db.Column(db.Integer, primary_key=True)
    certificate_id = db.Column(db.String(32), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    registration_id = db.Column(
        db.Integer, db.ForeignKey("registrations.id"), unique=True, nullable=False, index=True
    )
    issued_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    issued_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    student = db.relationship("User", back_populates="certificates", foreign_keys=[student_id])
    event = db.relationship("Event", back_populates="certificates")
    registration = db.relationship("Registration", back_populates="certificate")
    issued_by = db.relationship("User", foreign_keys=[issued_by_id])

    @property
    def issue_date_label(self):
        return self.issued_at.strftime("%d %B %Y") if self.issued_at else "-"

    def __repr__(self):
        return f"<Certificate {self.certificate_id}>"