"""Email delivery with a safe local-development fallback.

If SMTP is not configured the message is written to ``instance/emails.log``
and, when a Flask app context is active, appended to ``flask.g.dev_emails`` so
the UI can display a "development message" instead of failing.
"""

import logging
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app, g, has_app_context

logger = logging.getLogger(__name__)


def smtp_configured(app=None):
    app = app or (current_app if has_app_context() else None)
    if app is None:
        return False
    cfg = app.config
    if not cfg.get("MAIL_ENABLED"):
        return False
    return bool(cfg.get("MAIL_SERVER") and cfg.get("MAIL_USERNAME") and cfg.get("MAIL_PASSWORD"))


def _log_development_message(app, subject, recipients, body):
    log_path = app.config.get("MAIL_LOG_FILE") or os.path.join(app.instance_path, "emails.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write("=" * 78 + "\n")
            handle.write(f"[{stamp}] {subject}\n")
            handle.write(f"To: {', '.join(recipients)}\n")
            for line in body.splitlines():
                handle.write(f"    {line}\n")
    except OSError as exc:  # pragma: no cover - filesystem edge case
        logger.warning("Could not write development email log: %s", exc)

    if has_app_context():
        if not hasattr(g, "dev_emails"):
            g.dev_emails = []
        g.dev_emails.append({"subject": subject, "to": ", ".join(recipients), "body": body})
    logger.info("Development email queued -> %s | %s", recipients, subject)


def send_email(subject, recipients, body, sender_name=None, html=None):
    """Send an email. Returns a dict describing what happened.

    Never raises: a missing or broken SMTP setup degrades to a logged
    development message so the application keeps working.
    """
    if isinstance(recipients, str):
        recipients = [r for r in (recipients or "").split(",") if r.strip()]
    recipients = [r.strip() for r in (recipients or []) if r and r.strip()]

    app = current_app if has_app_context() else None
    if not recipients:
        return {"ok": False, "delivered": False, "reason": "No recipient supplied.", "subject": subject}

    if app is not None and smtp_configured(app):
        cfg = app.config
        try:
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = formataddr((sender_name or "CEMS - AGC", cfg["MAIL_DEFAULT_SENDER"]))
            message["To"] = ", ".join(recipients)
            message.set_content(body)
            if html:
                message.add_alternative(html, subtype="html")

            with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=15) as server:
                if cfg.get("MAIL_USE_TLS", True):
                    server.starttls()
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
                server.send_message(message)
            return {"ok": True, "delivered": True, "reason": "Email sent.", "subject": subject}
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning("SMTP delivery failed (%s) - falling back to log", exc)
            if app is not None:
                _log_development_message(app, subject, recipients, body)
            return {
                "ok": False,
                "delivered": False,
                "reason": f"SMTP error: {exc}. Saved as development message.",
                "subject": subject,
            }

    if app is not None:
        _log_development_message(app, subject, recipients, body)
        return {
            "ok": True,
            "delivered": False,
            "reason": "SMTP not configured - email recorded as a development message.",
            "subject": subject,
        }

    print(f"[CEMS email fallback] {subject} -> {', '.join(recipients)}")
    return {
        "ok": True,
        "delivered": False,
        "reason": "No application context - printed to console.",
        "subject": subject,
    }


# ---------------------------------------------------------------------------
# CEMS specific message templates
# ---------------------------------------------------------------------------
def send_registration_email(registration):
    event = registration.event
    student = registration.student
    subject = f"[CEMS-AGC] Registration confirmed: {event.title}"
    body = (
        f"Dear {student.name},\n\n"
        f"Your registration for \"{event.title}\" is confirmed.\n\n"
        f"Registration ID : {registration.registration_id}\n"
        f"Event date      : {event.event_date:%d %B %Y}\n"
        f"Venue           : {event.venue}\n\n"
        f"Please carry the digital ticket (with QR code) available in your CEMS dashboard.\n\n"
        f"-- CEMS | AGC Campus Event Management System\n"
        f"   Amritsar Group of Colleges, Amritsar"
    )
    return send_email(subject, student.email, body, sender_name="CEMS - AGC")


def send_registration_cancelled_email(registration):
    event = registration.event
    student = registration.student
    subject = f"[CEMS-AGC] Registration cancelled: {event.title}"
    body = (
        f"Dear {student.name},\n\n"
        f"Your registration ({registration.registration_id}) for \"{event.title}\" has been cancelled.\n\n"
        f"Event date : {event.event_date:%d %B %Y}\n"
        f"Venue      : {event.venue}\n\n"
        f"-- CEMS | AGC Campus Event Management System\n"
        f"   Amritsar Group of Colleges, Amritsar"
    )
    return send_email(subject, student.email, body, sender_name="CEMS - AGC")


def send_certificate_email(certificate):
    subject = f"[CEMS-AGC] Certificate issued: {certificate.event.title}"
    body = (
        f"Dear {certificate.student.name},\n\n"
        f"Congratulations! Your certificate for \"{certificate.event.title}\" is now available.\n\n"
        f"Certificate ID : {certificate.certificate_id}\n"
        f"Issued on      : {certificate.issued_at:%d %B %Y}\n\n"
        f"Download the PDF certificate from CEMS -> My Certificates.\n\n"
        f"-- CEMS | AGC Campus Event Management System\n"
        f"   Amritsar Group of Colleges, Amritsar"
    )
    return send_email(subject, certificate.student.email, body, sender_name="CEMS - AGC")


def send_event_cancelled_email(event):
    registrations = [r for r in event.registrations if r.is_confirmed]
    if not registrations:
        return {"ok": True, "delivered": False, "reason": "No confirmed registrations.", "subject": None}
    recipients = [r.student.email for r in registrations]
    subject = f"[CEMS-AGC] Event cancelled: {event.title}"
    body = (
        f"Dear student,\n\n"
        f"We regret to inform you that \"{event.title}\" scheduled for "
        f"{event.event_date:%d %B %Y} at {event.venue} has been cancelled.\n\n"
        f"Your registration has been released automatically. Refunds/arrangements will be "
        f"communicated by the event organizer.\n\n"
        f"-- CEMS | AGC Campus Event Management System\n"
        f"   Amritsar Group of Colleges, Amritsar"
    )
    return send_email(subject, recipients, body, sender_name="CEMS - AGC")