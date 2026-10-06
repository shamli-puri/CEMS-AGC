"""Demo data seeding for CEMS - AGC Campus Event Management System.

Creates three demo logins (one per role), a realistic AGC event calendar,
registrations, attendance, feedback, notices and certificates.
There is deliberately NO admin account.
"""

from datetime import datetime, time, timedelta

from .extensions import db
from .models import (
    AUDIENCE_ALL,
    AUDIENCE_FACULTY,
    AUDIENCE_ORGANIZER,
    AUDIENCE_STUDENT,
    ATT_ABSENT,
    ATT_PRESENT,
    EVENT_CANCELLED,
    EVENT_CATEGORIES,
    EVENT_COMPLETED,
    EVENT_UPCOMING,
    ROLE_FACULTY,
    ROLE_ORGANIZER,
    ROLE_STUDENT,
    REG_CONFIRMED,
    Attendance,
    Certificate,
    Event,
    Feedback,
    Notice,
    Registration,
    User,
    utcnow,
)

DEMO_PASSWORD = "agc@2026"

DEMO_ACCOUNTS = [
    {
        "name": "Aarav Sharma",
        "email": "student@agc.edu.in",
        "role": ROLE_STUDENT,
        "password": DEMO_PASSWORD,
        "roll_number": "CSE-2023-0142",
        "department": "Computer Science & Engineering",
        "year_of_study": "3rd Year",
        "phone": "9876543210",
        "bio": "Final year CSE student at AGC, passionate about tech events and campus coding clubs.",
    },
    {
        "name": "Dr. Meenakshi Sharma",
        "email": "faculty@agc.edu.in",
        "role": ROLE_FACULTY,
        "password": DEMO_PASSWORD,
        "employee_id": "AGC-FAC-104",
        "designation": "Associate Professor",
        "department": "Computer Science & Engineering",
        "phone": "9815001122",
        "bio": "Head - Department of Computer Science & Engineering, Amritsar Group of Colleges.",
    },
    {
        "name": "Rohan Verma",
        "email": "organizer@agc.edu.in",
        "role": ROLE_ORGANIZER,
        "password": DEMO_PASSWORD,
        "designation": "Event Coordinator",
        "organization": "AGC Technical & Cultural Committee",
        "phone": "9878012345",
        "bio": "Coordinates technical, cultural and sports events across the AGC campus.",
    },
]

EXTRA_STUDENTS = [
    ("Jaspreet Kaur", "jaspreet@agc.edu.in", "CSE-2023-0187", "Computer Science & Engineering", "3rd Year"),
    ("Gurpreet Singh", "gurpreet@agc.edu.in", "IT-2022-0341", "Information Technology", "4th Year"),
    ("Simranjit Kaur", "simranjit@agc.edu.in", "ECE-2023-0508", "Electronics & Communication", "3rd Year"),
    ("Abhishek Gupta", "abhishek@agc.edu.in", "CSE-2022-0093", "Computer Science & Engineering", "4th Year"),
    ("Navjot Sidhu", "navjot@agc.edu.in", "BCA-2023-0270", "Computer Applications (BCA)", "3rd Year"),
    ("Harmanpreet Kaur", "harman@agc.edu.in", "CSE-2024-0455", "Computer Science & Engineering", "2nd Year"),
    ("Vikas Kumar", "vikas@agc.edu.in", "MECH-2022-0612", "Mechanical Engineering", "4th Year"),
    ("Kirandeep Kaur", "kirandeep@agc.edu.in", "BBA-2023-0733", "Management Studies", "3rd Year"),
]

NOTICE_SEED = [
    (
        "Registrations open for AGC Annual Technical Symposium 2026",
        "Registrations for the AGC Annual Technical Symposium (ATS-2026) are now open through the "
        "CEMS portal. Students can register from the Events section, download the digital ticket with "
        "QR code, and carry it to the venue for entry. Certificates will be issued automatically after "
        "attendance verification.",
        AUDIENCE_ALL,
        True,
    ),
    (
        "Campus event guidelines for student participants",
        "Every registered participant must carry a valid CEMS digital ticket containing the QR code. "
        "Entry will be allowed only after scanning the QR code at the registration desk. Please arrive "
        "30 minutes before the reported start time.",
        AUDIENCE_STUDENT,
        False,
    ),
    (
        "Faculty attendance verification responsibilities",
        "Faculty members are requested to complete attendance verification for events within 24 hours "
        "of completion. Attendance verification enables automatic certificate issuance for eligible "
        "participants.",
        AUDIENCE_FACULTY,
        True,
    ),
    (
        "Organizer submission checklist for AGC events",
        "Organizers must publish the event notice, keep the registration deadline accurate, and verify "
        "attendance before closing the event. Cancelled events automatically release all registrations.",
        AUDIENCE_ORGANIZER,
        False,
    ),
    (
        "Library and seminar hall booking is now via CEMS",
        "All seminar hall and library auditorium bookings for campus events must be routed through the "
        "CEMS organizer module so venue conflicts are avoided automatically.",
        AUDIENCE_ALL,
        False,
    ),
]

EVENT_TEMPLATES = [
    {
        "title": "AGC Annual Technical Symposium 2026",
        "description": (
            "The flagship inter-college technical event of Amritsar Group of Colleges featuring "
            "project exhibitions, technical paper presentations, coding sprints and industry "
            "expert keynotes across two days."
        ),
        "category": "Technical",
        "venue": "Main Auditorium & CSE Block, AGC Campus",
        "offset": 18,
        "start": "10:00",
        "end": "17:00",
        "capacity": 150,
        "deadline_days": 12,
    },
    {
        "title": "CodeSprint 4.0 - 6 Hour Hackathon",
        "description": (
            "A six hour intra-college hackathon judged on originality, implementation quality and "
            "scalability. Teams of up to four members compete for cash prizes and internship "
            "opportunities with partner companies."
        ),
        "category": "Technical",
        "venue": "Computer Laboratory 3, CSE Block",
        "offset": 9,
        "start": "09:30",
        "end": "16:00",
        "capacity": 80,
        "deadline_days": 6,
    },
    {
        "title": "AI & Data Science Career Workshop",
        "description": (
            "A hands-on workshop covering Python for data science, model building, and deployment. "
            "Participants build and deploy a small machine learning project before the session ends."
        ),
        "category": "Workshop",
        "venue": "Seminar Hall A, AGC Campus",
        "offset": 5,
        "start": "11:00",
        "end": "15:00",
        "capacity": 60,
        "deadline_days": 3,
    },
    {
        "title": "Vocal Night - Annual Cultural Evening",
        "description": (
            "An evening of solo singing, group performances and instrumental music organised by the "
            "AGC Cultural Committee. Audience entry is free for registered students."
        ),
        "category": "Cultural",
        "venue": "Open Air Auditorium, AGC Campus",
        "offset": -12,
        "start": "18:00",
        "end": "21:30",
        "capacity": 200,
        "deadline_days": -6,
    },
    {
        "title": "Inter-Department Cricket League Finals",
        "description": (
            "The finals of the AGC inter-department cricket league played on the main ground. "
            "Department teams compete for the AGC Champions Trophy."
        ),
        "category": "Sports",
        "venue": "AGC Main Ground",
        "offset": -5,
        "start": "08:00",
        "end": "13:00",
        "capacity": 120,
        "deadline_days": -9,
    },
    {
        "title": "Campus Placement Drive - TCS Digital Profile",
        "description": (
            "On-campus recruitment drive for the TCS Digital profile. Students who attended the "
            "pre-placement aptitude workshop are given priority for the interview slots."
        ),
        "category": "Placement",
        "venue": "Conference Room, Administration Block",
        "offset": 26,
        "start": "10:00",
        "end": "16:00",
        "capacity": 45,
        "deadline_days": 20,
    },
    {
        "title": "Cyber Security Awareness Seminar",
        "description": (
            "A seminar on practical cyber hygiene, password security, phishing awareness and legal "
            "aspects of digital safety, delivered with the district cybercrime resource centre."
        ),
        "category": "Seminar",
        "venue": "Seminar Hall B, AGC Campus",
        "offset": 14,
        "start": "12:00",
        "end": "14:30",
        "capacity": 90,
        "deadline_days": 10,
    },
    {
        "title": "Blood Donation Camp - Swasthya Jyoti",
        "description": (
            "A voluntary blood donation camp organised in association with the district blood bank. "
            "Registered donors receive a participation certificate issued through CEMS."
        ),
        "category": "Community",
        "venue": "AGC Health Centre",
        "offset": 21,
        "start": "09:00",
        "end": "14:00",
        "capacity": 100,
        "deadline_days": 15,
    },
    {
        "title": "Startup Bootcamp: Idea to Product",
        "description": (
            "Mentors from the regional startup ecosystem guide student teams from idea validation to a "
            "working product prototype, with a pitch competition at the end of the bootcamp."
        ),
        "category": "Workshop",
        "venue": "Innovation Cell, CSE Block",
        "offset": 33,
        "start": "10:30",
        "end": "17:30",
        "capacity": 75,
        "deadline_days": 25,
    },
]

FEEDBACK_SAMPLES = [
    (5, "Excellent organisation. The QR based entry queue was almost instant and the faculty support was outstanding."),
    (5, "Very informative sessions and the certificate came through CEMS within a day. Worth attending."),
    (4, "Content was strong. Would have liked a longer hands-on session at the end."),
    (4, "Great venue and smooth coordination. Registration and ticket system worked perfectly."),
    (3, "Overall good, but the event started about thirty minutes late than the announced time."),
    (5, "Best technical event I have attended at AGC so far. The project exhibition was excellent."),
    (4, "Good faculty coordination and the certificates were issued without any hassle."),
    (2, "The event was informative but the hall was crowded and seating was limited."),
]


def _build_datetime(day, hhmm):
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.combine(day, time(hour=hour, minute=minute))


def seed_if_empty():
    """Seed demo data only when the database has no users."""
    if User.query.count() > 0:
        return False
    seed_demo_data()
    return True


def seed_demo_data(force=False):
    if User.query.count() > 0 and not force:
        return {"status": "skipped", "reason": "database already contains users"}
    if force:
        _clear_existing_data()

    result = _create_data()
    db.session.commit()
    return result


def _clear_existing_data():
    """Remove every seeded row so that --force can be re-run safely."""
    db.session.query(Certificate).delete()
    db.session.query(Feedback).delete()
    db.session.query(Attendance).delete()
    db.session.query(Registration).delete()
    db.session.query(Event).delete()
    db.session.query(Notice).delete()
    db.session.query(User).delete()
    db.session.commit()


def _create_data():
    now = utcnow()
    today = now.date()

    users = {}
    for spec in DEMO_ACCOUNTS:
        user = User(
            name=spec["name"],
            email=spec["email"],
            role=spec["role"],
            phone=spec.get("phone"),
            department=spec.get("department"),
            roll_number=spec.get("roll_number"),
            year_of_study=spec.get("year_of_study"),
            employee_id=spec.get("employee_id"),
            designation=spec.get("designation"),
            organization=spec.get("organization"),
            bio=spec.get("bio"),
        )
        user.set_password(spec["password"])
        db.session.add(user)
        users[spec["role"]] = user

    students = [users[ROLE_STUDENT]]
    for name, email, roll, dept, year in EXTRA_STUDENTS:
        student = User(
            name=name,
            email=email,
            role=ROLE_STUDENT,
            roll_number=roll,
            department=dept,
            year_of_study=year,
            phone="98" + str(10000000 + len(students) * 137),
        )
        student.set_password(DEMO_PASSWORD)
        db.session.add(student)
        students.append(student)

    db.session.flush()

    # ---- events -----------------------------------------------------------
    events = []
    reg_counter = 1
    for template in EVENT_TEMPLATES:
        event_date = today + timedelta(days=template["offset"])
        start = _build_datetime(event_date, template["start"])
        end = _build_datetime(event_date, template["end"])
        deadline = now + timedelta(days=template["deadline_days"])
        if deadline.date() > event_date:
            deadline = start - timedelta(hours=6)

        status = EVENT_UPCOMING
        if end < now:
            status = EVENT_COMPLETED

        event = Event(
            title=template["title"],
            description=template["description"],
            category=template["category"],
            event_date=event_date,
            start_time=start.time(),
            end_time=end.time(),
            venue=template["venue"],
            organizer_id=users[ROLE_ORGANIZER].id,
            max_capacity=template["capacity"],
            registration_deadline=deadline,
            status=status,
            certificate_eligible=True,
        )
        db.session.add(event)
        events.append(event)
    db.session.flush()

    # ---- registrations, attendance, feedback, certificates -----------------
    for index, event in enumerate(events):
        pool = students[:]
        if index % 2 == 0:
            pool = pool[1:] + pool[:1]
        take = min(len(pool), max(2, int(event.max_capacity * (0.35 + (index % 3) * 0.12))))
        chosen = pool[:take]
        if event.status == EVENT_CANCELLED:
            chosen = chosen[:2]

        for position, student in enumerate(chosen):
            code = f"AGC-REG-{2026}{index:02d}{position:03d}"
            registration = Registration(
                registration_id=code,
                student_id=student.id,
                event_id=event.id,
                status=REG_CONFIRMED,
                registered_at=now - timedelta(days=max(1, 20 - index * 2)),
            )
            db.session.add(registration)
            db.session.flush()
            reg_counter += 1

            if event.status == EVENT_COMPLETED:
                status = ATT_PRESENT if (position % 4) != 3 else ATT_ABSENT
                db.session.add(
                    _attendance_row(registration, event, status, users[ROLE_FACULTY], now)
                )
                db.session.flush()

                if status == ATT_PRESENT:
                    rating, comments = FEEDBACK_SAMPLES[(index + position) % len(FEEDBACK_SAMPLES)]
                    db.session.add(
                        Feedback(
                            student_id=student.id,
                            event_id=event.id,
                            registration_id=registration.id,
                            rating=rating,
                            comments=comments,
                            created_at=now - timedelta(days=1),
                        )
                    )
                    db.session.flush()
                    db.session.add(
                        Certificate(
                            certificate_id=f"AGC-CERT-{2026}{index:02d}{position:03d}",
                            student_id=student.id,
                            event_id=event.id,
                            registration_id=registration.id,
                            issued_by_id=users[ROLE_ORGANIZER].id,
                            issued_at=now - timedelta(days=1, hours=position),
                        )
                    )

    db.session.flush()

    # ---- notices ----------------------------------------------------------
    for title, description, audience, important in NOTICE_SEED:
        db.session.add(
            Notice(
                title=title,
                description=description,
                author_id=users[ROLE_ORGANIZER].id,
                audience=audience,
                is_important=important,
                published_at=now - timedelta(days=len(title) % 7),
            )
        )

    # A cancelled event so the "cancelled" flow is demonstrable.
    cancelled = Event(
        title="Inter-Class Debate Competition (postponed)",
        description=(
            "The inter-class debate competition has been postponed due to a clash with the university "
            "examination schedule. A revised date will be announced through a CEMS notice."
        ),
        category="Cultural",
        event_date=today - timedelta(days=2),
        start_time=time(hour=11, minute=0),
        end_time=time(hour=14, minute=0),
        venue="Seminar Hall A, AGC Campus",
        organizer_id=users[ROLE_ORGANIZER].id,
        max_capacity=60,
        registration_deadline=now - timedelta(days=4),
        status=EVENT_CANCELLED,
        certificate_eligible=False,
    )
    db.session.add(cancelled)

    db.session.flush()
    for student in students[:4]:
        registration = Registration(
            registration_id=f"AGC-REG-CANCEL{student.id:03d}",
            student_id=student.id,
            event_id=cancelled.id,
            status=REG_CONFIRMED,
            registered_at=now - timedelta(days=10),
        )
        db.session.add(registration)
        db.session.flush()
        registration.status = "CANCELLED"
        registration.cancelled_at = now - timedelta(days=4)

    db.session.commit()
    return {
        "status": "created",
        "users": User.query.count(),
        "events": Event.query.count(),
        "registrations": Registration.query.count(),
        "certificates": Certificate.query.count(),
        "feedback": Feedback.query.count(),
        "notices": Notice.query.count(),
        "categories": list(EVENT_CATEGORIES),
    }


def _attendance_row(registration, event, status, marked_by, now):
    from .models import Attendance

    return Attendance(
        registration_id=registration.id,
        student_id=registration.student_id,
        event_id=event.id,
        status=status,
        marked_by_id=marked_by.id,
        marked_at=event.end_datetime + timedelta(minutes=20),
        remarks="Verified at the CEMS registration desk.",
    )