"""Full-application smoke test.

Hits every GET route as every role and runs the core POST workflows, printing a
PASS/FAIL table. Run it with:

    python tests/smoke_test.py
"""

import os
import re
import sys
import tempfile
from datetime import datetime, time, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cems import create_app  # noqa: E402
from cems.extensions import db  # noqa: E402
from cems.models import (  # noqa: E402
    ATT_PRESENT,
    Certificate,
    Event,
    Feedback,
    Notice,
    Registration,
    ROLE_ORGANIZER,
    ROLE_STUDENT,
    User,
)

PASSWORD = "agc@2026"
RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {name}" + (f"\n        -> {detail}" if detail and not ok else ""))


def check(client, method, url, expect=(200, 302), name=None, **kwargs):
    label = name or f"{method} {url}"
    try:
        response = getattr(client, method.lower())(url, **kwargs)
    except Exception as exc:  # noqa: BLE001
        record(label, False, f"EXCEPTION {type(exc).__name__}: {exc}")
        return None
    if isinstance(expect, int):
        expect = (expect,)
    if response.status_code not in expect:
        body = response.get_data(as_text=True)
        match = re.search(r"((?:Error|Exception)[^<]{0,200})", body)
        record(label, False, f"HTTP {response.status_code} {match.group(1) if match else ''}")
    else:
        record(label, True)
    return response


def build_fixture_event(app, organizer_id, student_id):
    """Return the ids of (fresh_event, completed_event, cancelled_event)."""
    with app.app_context():
        fresh_id = None
        candidates = (
            Event.query.filter(Event.status == "UPCOMING")
            .order_by(Event.event_date.asc())
            .all()
        )
        for candidate in candidates:
            existing = Registration.query.filter_by(
                event_id=candidate.id, student_id=student_id, status="CONFIRMED"
            ).first()
            if not existing and candidate.max_capacity > 5 and not candidate.is_full:
                fresh_id = candidate.id
                break
        if fresh_id is None:
            base = datetime.utcnow() + timedelta(days=30)
            fresh = Event(
                title="AGC Smoke Test Fresh Event",
                description="A freshly created event used only by the CEMS smoke test suite.",
                category="Technical",
                event_date=base.date(),
                start_time=time(10, 0),
                end_time=time(15, 0),
                venue="Innovation Lab, AGC Campus",
                organizer_id=organizer_id,
                max_capacity=90,
                registration_deadline=base - timedelta(days=1),
                status="UPCOMING",
            )
            db.session.add(fresh)
            db.session.commit()
            fresh_id = fresh.id

        completed = Event.query.filter_by(status="COMPLETED").first()
        cancelled = Event.query.filter_by(status="CANCELLED").first()
        return fresh_id, completed.id, cancelled.id


def main():
    tmp = tempfile.mkdtemp(prefix="cems-smoke-")
    app = create_app(
        "development",
        SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(tmp, "smoke.sqlite3"),
        SEED_ON_START=False,
    )
    with app.app_context():
        db.create_all()
        from cems.seed import seed_demo_data

        seed_demo_data(force=True)
        users = {u.role: (u.id, u.email) for u in User.query.all()}
        student_id = users[ROLE_STUDENT][0]
        student_email = users[ROLE_STUDENT][1]
        faculty_email = users["FACULTY"][1]
        organizer_id = users[ROLE_ORGANIZER][0]
        organizer_email = users[ROLE_ORGANIZER][1]
        extra_students = [
            (u.id, u.email)
            for u in User.query.filter_by(role=ROLE_STUDENT).all()
            if u.id != student_id
        ]

    event_id, completed_id, cancelled_id = build_fixture_event(app, organizer_id, student_id)

    check(app.test_client(), "get", "/healthz", 200, "GET /healthz")

    # --------------------------------------------------------------- AUTH --
    client = app.test_client()
    r = client.get("/")
    record("GET / shows the welcome screen", r.status_code == 200 and b"CEMS" in r.data, f"got {r.status_code}")
    check(client, "get", "/auth/login", 200, "GET /auth/login (role chooser)")
    check(client, "get", "/auth/login/student", 200, "GET /auth/login/student")
    check(client, "get", "/auth/login/faculty", 200, "GET /auth/login/faculty")
    check(client, "get", "/auth/login/organizer", 200, "GET /auth/login/organizer")
    check(client, "get", "/auth/register", 200, "GET /auth/register")
    check(client, "get", "/auth/login?role=student", 302, "GET /auth/login?role=student")

    r = client.post("/auth/login/student", data={"email": student_email, "password": "wrong"})
    record("POST student login wrong password -> 401", r.status_code == 401, f"got {r.status_code}")
    r = client.post("/auth/login/student", data={"email": "nobody@agc.edu.in", "password": PASSWORD})
    record("POST student login unknown email -> 401", r.status_code == 401, f"got {r.status_code}")
    r = client.post("/auth/login/student", data={"email": faculty_email, "password": PASSWORD})
    record("POST student login with faculty account -> 403", r.status_code == 403, f"got {r.status_code}")
    r = client.post("/auth/login/student", data={"email": "", "password": ""})
    record("POST student login empty fields -> 400", r.status_code == 400, f"got {r.status_code}")

    stamp = int(datetime.utcnow().timestamp())
    r = client.post(
        "/auth/register",
        data={
            "name": "Smoke Test Student",
            "email": f"newstudent{stamp}@agc.edu.in",
            "roll_number": "CSE-2024-9999",
            "department": "Computer Science & Engineering",
            "year_of_study": "2nd Year",
            "phone": "9876500000",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            "agree": "1",
            "bio": "Created by the CEMS smoke test.",
        },
        follow_redirects=True,
    )
    record("POST /auth/register (valid)", r.status_code == 200 and b"Student account created" in r.data)
    client.get("/auth/logout")
    r = client.post("/auth/register", data={"name": "X", "email": "bad", "password": "1", "confirm_password": "2"})
    record("POST /auth/register (invalid) -> 400", r.status_code == 400, f"got {r.status_code}")
    client.get("/auth/logout")

    # ------------------------------------------------------------- STUDENT --
    client = app.test_client()
    r = client.post("/auth/login/student", data={"email": student_email, "password": PASSWORD})
    record(
        "POST student login redirects to /student/dashboard",
        r.status_code == 302 and "/student/dashboard" in r.headers.get("Location", ""),
        r.headers.get("Location", ""),
    )

    for url in [
        "/student/dashboard",
        "/student/events",
        f"/student/events/{event_id}",
        "/student/events?q=symposium&category=Technical&status=UPCOMING",
        "/student/registrations",
        "/student/registrations?scope=upcoming",
        "/student/registrations?scope=cancelled",
        "/student/attendance",
        "/student/certificates",
        "/student/feedback",
        "/student/notices",
        "/notices",
        "/events/catalogue",
        "/events/catalogue?category=Sports",
        f"/events/{event_id}",
        "/profile/",
        "/profile/edit",
        "/profile/password",
        "/events/search?q=symposium",
        "/about",
        "/student/attendance/record.pdf",
    ]:
        check(client, "get", url, 200, name=f"student GET {url}")

    for url in [
        "/faculty/dashboard",
        "/organizer/dashboard",
        "/organizer/events/create",
        "/faculty/events",
        "/organizer/statistics",
    ]:
        r = client.get(url, follow_redirects=False)
        record(
            f"student blocked from {url}",
            r.status_code == 302 and "/student/dashboard" in r.headers.get("Location", ""),
            f"HTTP {r.status_code} {r.headers.get('Location', '')}",
        )

    r = client.post(f"/student/events/{event_id}/register", follow_redirects=True)
    record(
        "POST student register for event",
        r.status_code == 200 and b"Registration successful" in r.data,
        f"HTTP {r.status_code}, message present: {b'Registration successful' in r.data}",
    )
    with app.app_context():
        reg = Registration.query.filter_by(
            student_id=student_id, event_id=event_id, status="CONFIRMED"
        ).first()
        reg_id = reg.id
        reg_code = reg.registration_id
    record(
        "registration stored with unique AGC-REG id",
        bool(reg_code and reg_code.startswith("AGC-REG-")),
        str(reg_code),
    )

    check(client, "get", f"/student/registrations/{reg_id}/ticket", 200, "student GET ticket page")
    check(client, "get", f"/student/registrations/{reg_id}/qr.png", 200, "student GET ticket QR png")
    check(client, "get", f"/events/verify/{reg_code}", 200, "GET public QR verification page")
    check(client, "get", "/events/verify/BOGUS-ID", 404, "GET verification with unknown code")
    check(client, "get", f"/student/events/{event_id}/participants", 200, "student GET participants")

    r = client.post(f"/student/events/{event_id}/register", follow_redirects=True)
    record("duplicate registration blocked", b"already registered" in r.data)

    r = client.post(f"/student/registrations/{reg_id}/cancel", follow_redirects=True)
    record("student cancels registration", r.status_code == 200 and b"cancel" in r.data.lower())
    with app.app_context():
        record(
            "registration marked CANCELLED",
            db.session.get(Registration, reg_id).status == "CANCELLED",
        )
    r = client.get(f"/student/registrations/{reg_id}/ticket", follow_redirects=True)
    record("cancelled ticket is refused", b"no longer valid" in r.data)

    r = client.post(f"/student/events/{event_id}/register", follow_redirects=True)
    record("re-registration after cancellation allowed", b"Registration successful" in r.data)
    with app.app_context():
        reg_id = Registration.query.filter_by(
            student_id=student_id, event_id=event_id, status="CONFIRMED"
        ).first().id

    # capacity / deadline / cancelled-event rules
    with app.app_context():
        small_id = None
        for candidate in (
            Event.query.filter(
                Event.status == "UPCOMING",
                Event.event_date > datetime.utcnow().date(),
                Event.max_capacity <= 1,
            )
            .order_by(Event.event_date.asc())
            .all()
        ):
            if Registration.query.filter_by(event_id=candidate.id, status="CONFIRMED").count() == 0:
                small_id = candidate.id
                break
        closed = Event.query.filter(
            Event.status == "UPCOMING", Event.registration_deadline < datetime.utcnow()
        ).first()
        closed_id = closed.id if closed else None
        if small_id is None or closed_id is None:
            base = datetime.utcnow()
            if small_id is None:
                tiny = Event(
                    title="AGC Smoke Test Single Seat Workshop",
                    description="A one-seat workshop used only by the CEMS smoke test suite.",
                    category="Workshop",
                    event_date=(base + timedelta(days=45)).date(),
                    start_time=time(10, 0),
                    end_time=time(12, 0),
                    venue="Design Studio, AGC Campus",
                    organizer_id=organizer_id,
                    max_capacity=1,
                    registration_deadline=base + timedelta(days=40),
                    status="UPCOMING",
                )
                db.session.add(tiny)
                db.session.flush()
                small_id = tiny.id
            if closed_id is None:
                shut = Event(
                    title="AGC Smoke Test Closed Registration Talk",
                    description="A talk whose registration deadline has already passed.",
                    category="Seminar",
                    event_date=(base + timedelta(days=50)).date(),
                    start_time=time(15, 0),
                    end_time=time(17, 0),
                    venue="Seminar Hall B, AGC Campus",
                    organizer_id=organizer_id,
                    max_capacity=40,
                    registration_deadline=base - timedelta(days=1),
                    status="UPCOMING",
                )
                db.session.add(shut)
                db.session.flush()
                closed_id = shut.id
            db.session.commit()

    s2 = app.test_client()
    s2.post("/auth/login/student", data={"email": extra_students[0][1], "password": PASSWORD})
    if small_id:
        r = s2.post(f"/student/events/{small_id}/register", follow_redirects=True)
        record("first registration fills a 1-seat event", b"Registration successful" in r.data)
        r = s2.post(f"/student/events/{small_id}/register", follow_redirects=True)
        record("registration blocked when capacity is full", b"maximum capacity" in r.data)
    else:
        record("capacity fixture available", False, "no 1-seat event found in seed data")
    if closed_id:
        r = s2.post(f"/student/events/{closed_id}/register", follow_redirects=True)
        record("registration blocked after the deadline", b"deadline" in r.data.lower())
    r = s2.post(f"/student/events/{cancelled_id}/register", follow_redirects=True)
    record("registration blocked for a cancelled event", b"cancelled" in r.data.lower())

    # feedback + certificates
    with app.app_context():
        attended_event_id = None
        for candidate in Event.query.filter_by(status="COMPLETED").all():
            row = Registration.query.filter_by(
                event_id=candidate.id, student_id=student_id, status="CONFIRMED"
            ).first()
            if row is None or not row.attendance or row.attendance.status != ATT_PRESENT:
                continue
            # Seed data always ships feedback for attended events, so clear one
            # row to exercise the genuine "submit feedback" path.
            existing = Feedback.query.filter_by(registration_id=row.id).first()
            if existing is not None:
                db.session.delete(existing)
                db.session.commit()
            attended_event_id = candidate.id
            break
    record(
        "seed provides an attended completed event for the demo student",
        attended_event_id is not None,
        "no PRESENT registration found",
    )

    if attended_event_id:
        r = client.post(
            f"/student/events/{attended_event_id}/feedback",
            data={"rating": 5, "comments": "Smoke test feedback - excellent event."},
            follow_redirects=True,
        )
        record("student submits feedback", r.status_code == 200 and b"recorded" in r.data)
        r = client.post(
            f"/student/events/{attended_event_id}/feedback",
            data={"rating": 5, "comments": "Duplicate feedback attempt."},
            follow_redirects=True,
        )
        record("duplicate feedback blocked", b"already submitted" in r.data)
        r = client.post(
            f"/student/events/{event_id}/feedback",
            data={"rating": 4, "comments": "Feedback for an event I did not attend."},
            follow_redirects=True,
        )
        record("feedback blocked for an unattended event", b"attended" in r.data.lower())

    client.get("/student/certificates", follow_redirects=True)
    with app.app_context():
        certs = Certificate.query.filter_by(student_id=student_id).all()
        cert_id = certs[0].id if certs else None
    record("student owns at least one certificate", cert_id is not None)
    if cert_id:
        check(client, "get", f"/student/certificates/{cert_id}/pdf", 200, "student GET certificate PDF")
        check(
            client,
            "get",
            f"/student/certificates/{cert_id}/download",
            200,
            "student GET certificate download alias",
        )
        r = client.post(f"/student/certificates/{cert_id}/send", follow_redirects=True)
        record(
            "student certificate email uses dev fallback",
            r.status_code == 200 and b"development message" in r.data,
        )

    r = client.post(
        "/profile/edit",
        data={
            "name": "Aarav Sharma Updated",
            "phone": "9876500011",
            "department": "Computer Science & Engineering",
            "roll_number": "CSE-2023-0142",
            "year_of_study": "3rd Year",
            "bio": "Updated by the CEMS smoke test.",
        },
        follow_redirects=True,
    )
    record("POST profile edit", r.status_code == 200 and b"Profile updated" in r.data)
    r = client.post(
        "/profile/password",
        data={"current_password": PASSWORD, "new_password": "newpass123", "confirm_password": "newpass123"},
        follow_redirects=True,
    )
    record("POST password change", r.status_code == 200 and b"Password changed" in r.data)
    r = client.post(
        "/profile/password",
        data={"current_password": "wrong", "new_password": "abc123", "confirm_password": "abc123"},
    )
    record("POST password change with wrong current password -> 400", r.status_code == 400, f"got {r.status_code}")

    r = client.post("/auth/logout", follow_redirects=True)
    record("POST logout", r.status_code == 200 and b"signed out" in r.data)
    r = client.get("/student/dashboard", follow_redirects=False)
    record(
        "student dashboard blocked after logout",
        r.status_code == 302 and "/auth/login" in r.headers.get("Location", ""),
        r.headers.get("Location", ""),
    )

    # ------------------------------------------------------------- FACULTY --
    client = app.test_client()
    r = client.post("/auth/login/faculty", data={"email": faculty_email, "password": PASSWORD})
    record(
        "POST faculty login redirects to /faculty/dashboard",
        r.status_code == 302 and "/faculty/dashboard" in r.headers.get("Location", ""),
        r.headers.get("Location", ""),
    )

    with app.app_context():
        first_feedback = Feedback.query.first()
        feedback_id = first_feedback.id if first_feedback else None

    for url in [
        "/faculty/dashboard",
        "/faculty/events",
        f"/faculty/events/{event_id}",
        f"/faculty/events/{event_id}/registrations",
        f"/faculty/events/{event_id}/registrations?scope=present",
        f"/faculty/events/{event_id}/attendees",
        f"/faculty/events/{event_id}/attendance",
        f"/faculty/events/{event_id}/attendance/report.pdf",
        "/faculty/attendance",
        "/faculty/attendance_records",
        "/faculty/feedback",
        f"/faculty/feedback/{feedback_id or 1}",
        "/faculty/notices",
        "/profile/",
        "/profile/edit",
        "/events/catalogue",
        f"/events/{event_id}",
    ]:
        check(client, "get", url, (200, 302, 404), name=f"faculty GET {url}")

    for url in ["/student/dashboard", "/organizer/dashboard", "/organizer/events/create"]:
        r = client.get(url, follow_redirects=False)
        record(
            f"faculty blocked from {url}",
            r.status_code == 302 and "/faculty/dashboard" in r.headers.get("Location", ""),
            f"HTTP {r.status_code} {r.headers.get('Location', '')}",
        )

    r = client.post(f"/faculty/registrations/{reg_id}/toggle-attendance", follow_redirects=True)
    record("faculty toggles attendance", r.status_code == 200 and b"marked" in r.data)
    r = client.post(
        f"/faculty/events/{event_id}/attendance",
        data={"present": [reg_id], "absent": [reg_id], "scope": "marked", "remarks": "Verified at desk"},
        follow_redirects=True,
    )
    record("faculty bulk attendance save", r.status_code == 200 and b"Attendance saved" in r.data)
    r = client.post(f"/faculty/events/{event_id}/remind", follow_redirects=True)
    record("faculty participant reminder uses dev fallback", r.status_code == 200)

    # ----------------------------------------------------------- ORGANIZER --
    client = app.test_client()
    r = client.post("/auth/login/organizer", data={"email": organizer_email, "password": PASSWORD})
    record(
        "POST organizer login redirects to /organizer/dashboard",
        r.status_code == 302 and "/organizer/dashboard" in r.headers.get("Location", ""),
        r.headers.get("Location", ""),
    )

    for url in [
        "/organizer/dashboard",
        "/organizer/events",
        "/organizer/events?status=UPCOMING",
        "/organizer/events/create",
        f"/organizer/events/{event_id}",
        f"/organizer/events/{event_id}/edit",
        f"/organizer/events/{event_id}/registrations",
        f"/organizer/events/{event_id}/attendees",
        f"/organizer/events/{event_id}/attendance",
        f"/organizer/events/{event_id}/attendance/report.pdf",
        f"/organizer/events/{event_id}/certificates",
        f"/organizer/events/{event_id}/statistics",
        "/organizer/statistics",
        "/organizer/participants",
        "/organizer/participants.csv",
        "/organizer/attendance",
        "/organizer/attendance_records",
        "/organizer/feedback",
        "/organizer/notices",
        "/organizer/notices?scope=mine",
        "/organizer/notices/create",
        "/profile/",
        "/profile/edit",
        "/events/catalogue",
    ]:
        check(client, "get", url, (200, 302), name=f"organizer GET {url}")

    for url in ["/student/dashboard", "/faculty/dashboard", "/student/registrations"]:
        r = client.get(url, follow_redirects=False)
        record(
            f"organizer blocked from {url}",
            r.status_code == 302 and "/organizer/dashboard" in r.headers.get("Location", ""),
            f"HTTP {r.status_code} {r.headers.get('Location', '')}",
        )

    new_day = (datetime.utcnow() + timedelta(days=20)).strftime("%Y-%m-%d")
    deadline = (datetime.utcnow() + timedelta(days=15)).strftime("%Y-%m-%dT%H:%M")
    r = client.post(
        "/organizer/events/create",
        data={
            "title": "Smoke Test Mega Event",
            "description": "A newly created event from the CEMS smoke test suite for verification.",
            "category": "Technical",
            "event_date": new_day,
            "start_time": "10:00",
            "end_time": "16:00",
            "venue": "Innovation Lab, AGC Campus",
            "max_capacity": "75",
            "registration_deadline": deadline,
            "certificate_eligible": "1",
        },
        follow_redirects=True,
    )
    record("organizer creates event", r.status_code == 200 and b"created successfully" in r.data)
    with app.app_context():
        created = Event.query.filter_by(title="Smoke Test Mega Event").first()
        created_id = created.id if created else None
        record(
            "created event persisted as UPCOMING",
            bool(created and created.status == "UPCOMING"),
        )
        check(
            app.test_client(),
            "get",
            "/organizer/dashboard",
            (200, 302),
            "GET /organizer/dashboard while logged out",
        )

    r = client.post(
        "/organizer/events/create",
        data={"title": "x", "description": "short", "category": "Nope", "max_capacity": "abc"},
    )
    record("invalid event create -> 400", r.status_code == 400, f"got {r.status_code}")

    if created_id:
        r = client.post(
            f"/organizer/events/{created_id}/edit",
            data={
                "title": "Smoke Test Mega Event Renamed",
                "description": "Updated description that is definitely long enough to pass validation.",
                "category": "Workshop",
                "event_date": new_day,
                "start_time": "11:00",
                "end_time": "17:00",
                "venue": "Innovation Lab Block B",
                "max_capacity": "80",
                "registration_deadline": deadline,
                "certificate_eligible": "1",
            },
            follow_redirects=True,
        )
        record("organizer edits event", r.status_code == 200 and b"has been updated" in r.data)

        s3 = app.test_client()
        s3.post("/auth/login/student", data={"email": extra_students[1][1], "password": PASSWORD})
        r = s3.post(f"/student/events/{created_id}/register", follow_redirects=True)
        record("student registers for the created event", b"Registration successful" in r.data)
        with app.app_context():
            row = Registration.query.filter_by(event_id=created_id, status="CONFIRMED").first()
            reg3_id = row.id if row else None
        if reg3_id:
            r = client.post(f"/organizer/registrations/{reg3_id}/cancel", follow_redirects=True)
            record("organizer cancels a registration", r.status_code == 200 and b"cancel" in r.data.lower())
            r = client.post(f"/organizer/registrations/{reg3_id}/restore", follow_redirects=True)
            record("organizer restores a registration", r.status_code == 200 and b"restored" in r.data.lower())
            r = client.post(f"/organizer/registrations/{reg3_id}/toggle-attendance", follow_redirects=True)
            record("organizer toggles attendance", r.status_code == 200 and b"marked" in r.data)
            r = client.post(
                f"/organizer/events/{created_id}/attendance",
                data={"present": [reg3_id], "absent": [reg3_id], "scope": "marked", "remarks": "ok"},
                follow_redirects=True,
            )
            record("organizer bulk attendance save", r.status_code == 200 and b"verified" in r.data)

        r = client.post(f"/organizer/events/{created_id}/cancel", follow_redirects=True)
        record("organizer cancels event", r.status_code == 200 and b"has been cancelled" in r.data)
        with app.app_context():
            cancelled_row = db.session.get(Event, created_id)
            record(
                "cancelled event released all registrations",
                cancelled_row.status == "CANCELLED"
                and all(not x.is_confirmed for x in cancelled_row.registrations),
            )
        r = client.post(f"/organizer/events/{created_id}/restore", follow_redirects=True)
        record("organizer restores cancelled event", r.status_code == 200)
        r = client.post(f"/organizer/events/{created_id}/delete", follow_redirects=True)
        record("organizer deletes event", r.status_code == 200 and b"deleted" in r.data.lower())
        with app.app_context():
            record("deleted event removed from database", db.session.get(Event, created_id) is None)

    # ownership guard
    with app.app_context():
        guard = User.query.filter(User.role == ROLE_ORGANIZER, User.id != organizer_id).first()
        if guard is None:
            guard = User(
                name="Ownership Guard Organizer",
                email=f"guard{stamp}@agc.edu.in",
                role=ROLE_ORGANIZER,
                organization="AGC Audit Committee",
            )
            guard.set_password(PASSWORD)
            db.session.add(guard)
            db.session.commit()
        base = datetime.utcnow() + timedelta(days=60)
        foreign = Event(
            title="AGC Smoke Test Foreign Organizer Event",
            description="An event owned by a different organizer account.",
            category="Technical",
            event_date=base.date(),
            start_time=time(10, 0),
            end_time=time(13, 0),
            venue="Innovation Lab, AGC Campus",
            organizer_id=guard.id,
            max_capacity=50,
            registration_deadline=base - timedelta(days=1),
            status="UPCOMING",
        )
        db.session.add(foreign)
        db.session.commit()
        foreign_id = foreign.id
    r = client.post(f"/organizer/events/{foreign_id}/delete", follow_redirects=True)
    record("organizer cannot delete another organizer's event", b"only manage events" in r.data)
    with app.app_context():
        record("guarded event still exists", db.session.get(Event, foreign_id) is not None)

    # notices CRUD
    r = client.post(
        "/organizer/notices/create",
        data={
            "title": "Smoke Test Notice",
            "description": "This notice was created by the CEMS smoke test suite.",
            "audience": "STUDENT",
            "is_important": "1",
        },
        follow_redirects=True,
    )
    record("organizer creates notice", r.status_code == 200 and b"published successfully" in r.data)
    with app.app_context():
        notice = Notice.query.filter_by(title="Smoke Test Notice").first()
        notice_id = notice.id if notice else None
    if notice_id:
        r = client.post(
            f"/organizer/notices/{notice_id}/edit",
            data={
                "title": "Smoke Test Notice Edited",
                "description": "Updated description of the smoke test notice body.",
                "audience": "ALL",
            },
            follow_redirects=True,
        )
        record("organizer edits notice", r.status_code == 200 and b"updated successfully" in r.data)
        check(client, "get", f"/organizer/notices/{notice_id}", 200, "GET organizer notice detail")
        r = client.post(f"/organizer/notices/{notice_id}/delete", follow_redirects=True)
        record("organizer deletes notice", r.status_code == 200 and b"deleted" in r.data)
    r = client.post("/organizer/notices/create", data={"title": "no", "description": "x", "audience": "BAD"})
    record("invalid notice create -> 400", r.status_code == 400, f"got {r.status_code}")

    # organizer certificate issuing
    with app.app_context():
        comp = Event.query.filter_by(status="COMPLETED", organizer_id=organizer_id).first()
        if comp is None:
            comp = Event.query.filter_by(status="COMPLETED").first()
            if comp is not None:
                comp.organizer_id = organizer_id
        if comp:
            from cems.services.domain import mark_attendance_bulk

            comp.certificate_eligible = True
            for row in comp.registrations:
                if row.is_confirmed:
                    mark_attendance_bulk(comp, [row.id], {row.id}, organizer_id, "bulk")
            db.session.commit()
            comp_id = comp.id
        else:
            comp_id = None
    if comp_id:
        r = client.post(f"/organizer/events/{comp_id}/certificates", follow_redirects=True)
        record("organizer issues certificates", r.status_code == 200, f"HTTP {r.status_code}")
        with app.app_context():
            row = Certificate.query.filter_by(event_id=comp_id).first()
            cert_pk = row.id if row else None
        if cert_pk:
            check(client, "get", f"/organizer/certificates/{cert_pk}/pdf", 200, "organizer GET certificate PDF")
            r = client.post(f"/organizer/certificates/{cert_pk}/send", follow_redirects=True)
            record("organizer certificate email uses dev fallback", r.status_code == 200)

    # --------------------------------------------------------- ANONYMOUS ---
    anon = app.test_client()
    check(anon, "get", "/student/dashboard", 302, "anonymous GET protected page redirects")
    check(anon, "get", "/", 200, "anonymous GET / shows welcome screen")
    check(anon, "get", "/definitely-not-a-page", 404, "404 error page renders")
    check(anon, "get", "/events/999999", 404, "unknown event -> 404")

    client.post("/auth/logout")

    failed = [row for row in RESULTS if not row[1]]
    print("\n" + "=" * 78)
    print(f"TOTAL: {len(RESULTS)}   PASSED: {len(RESULTS) - len(failed)}   FAILED: {len(failed)}")
    if failed:
        print("-" * 78)
        for name, _, detail in failed:
            print(f"  FAIL {name}\n        {detail}")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())