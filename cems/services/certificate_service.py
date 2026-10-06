"""PDF certificate generation for CEMS - AGC Campus Event Management System."""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph

from .errors import CertificateError

PAGE_SIZE = landscape(A4)

MAROON = colors.HexColor("#7B1E3B")
MAROON_DARK = colors.HexColor("#4A1226")
GOLD = colors.HexColor("#C9A227")
INK = colors.HexColor("#1F2430")
GREY = colors.HexColor("#5B6270")
LIGHT = colors.HexColor("#F4F6F9")

ORG_NAME = "Amritsar Group of Colleges"
SYSTEM_NAME = "AGC Campus Event Management System"
SHORT_NAME = "CEMS"


def _centered(c, text, y, font="Helvetica", size=12, color=INK, char_space=0):
    c.setFont(font, size)
    c.setFillColor(color)
    if char_space and len(text) > 1:
        widths = [c.stringWidth(ch, font, size) for ch in text]
        total = sum(widths) + char_space * (len(text) - 1)
        x = PAGE_SIZE[0] / 2.0 - total / 2.0
        for index, ch in enumerate(text):
            c.drawString(x, y, ch)
            x += widths[index] + char_space
        return
    c.drawCentredString(PAGE_SIZE[0] / 2.0, y, text)


def _draw_border(c):
    width, height = PAGE_SIZE
    c.setStrokeColor(MAROON)
    c.setLineWidth(3)
    c.rect(12 * mm, 12 * mm, width - 24 * mm, height - 24 * mm)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.rect(16 * mm, 16 * mm, width - 32 * mm, height - 32 * mm)

    corner = 14 * mm
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    for (x, y, sx, sy) in [
        (16 * mm, 16 * mm, 1, 1),
        (width - 16 * mm, 16 * mm, -1, 1),
        (16 * mm, height - 16 * mm, 1, -1),
        (width - 16 * mm, height - 16 * mm, -1, -1),
    ]:
        c.line(x, y, x + sx * corner, y)
        c.line(x, y, x, y + sy * corner)
    return corner


def _draw_logo(c, cx, cy, radius=15 * mm):
    c.saveState()
    c.setFillColor(MAROON)
    c.circle(cx, cy, radius, stroke=0, fill=1)
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.circle(cx, cy, radius, stroke=1, fill=0)
    _centered(c, "AGC", cy - 3, "Helvetica-Bold", 20, colors.white)
    _centered(c, "1996", cy - 12, "Helvetica", 7, colors.HexColor("#F2D98B"))
    c.restoreState()


def build_certificate_pdf(certificate):
    """Return PDF bytes for the given :class:`Certificate` instance."""
    try:
        buffer = io.BytesIO()
        c = pdfcanvas.Canvas(buffer, pagesize=PAGE_SIZE)
        width, height = PAGE_SIZE
        _draw_border(c)

        _draw_logo(c, width / 2.0, height - 32 * mm)

        _centered(c, ORG_NAME.upper(), height - 54 * mm, "Helvetica-Bold", 13, MAROON_DARK, 1.5)
        _centered(c, f"{SHORT_NAME}  |  {SYSTEM_NAME}", height - 63 * mm, "Helvetica", 9.5, GREY)

        c.setStrokeColor(GOLD)
        c.setLineWidth(1.5)
        c.line(width / 2 - 45 * mm, height - 70 * mm, width / 2 + 45 * mm, height - 70 * mm)

        _centered(c, "CERTIFICATE OF PARTICIPATION", height - 83 * mm, "Helvetica-Bold", 22, MAROON)
        _centered(
            c,
            "This is to certify that",
            height - 96 * mm,
            "Helvetica-Oblique",
            12,
            GREY,
        )

        student_name = (certificate.student.name or "").upper()
        name_size = 30 if len(student_name) < 30 else 24
        _centered(c, student_name, height - 113 * mm, "Helvetica-Bold", name_size, INK)
        c.setStrokeColor(MAROON)
        c.setLineWidth(1)
        c.line(width / 2 - 70 * mm, height - 117 * mm, width / 2 + 70 * mm, height - 117 * mm)

        _centered(c, "has successfully participated in", height - 127 * mm, "Helvetica", 11, GREY)
        event_title = certificate.event.title
        _centered(c, event_title, height - 138 * mm, "Helvetica-Bold", 17, MAROON_DARK)

        event = certificate.event
        details = (
            f"held on {event.event_date.strftime('%d %B %Y')} at {event.venue}, "
            f"{ORG_NAME}, Amritsar"
        )
        _centered(c, details, height - 148 * mm, "Helvetica", 10.5, GREY)

        _centered(
            c,
            f"Registration ID: {certificate.registration.registration_id}",
            height - 158 * mm,
            "Helvetica",
            9,
            GREY,
        )

        # signature blocks
        base_y = 46 * mm
        issued_by = certificate.issued_by
        organizer = event.organizer
        faculty_name = issued_by.name if issued_by else "Event Coordinator"

        blocks = [
            (34 * mm, "Event Organizer", organizer.name if organizer else "-", ORG_NAME),
            (width / 2.0, "Verified By (Faculty)", faculty_name, "AGC Faculty"),
            (width - 34 * mm, "Principal", "Principal", ORG_NAME),
        ]
        for x, role, name, sub in blocks:
            c.setStrokeColor(GREY)
            c.setLineWidth(0.8)
            c.line(x - 28 * mm, base_y + 12 * mm, x + 28 * mm, base_y + 12 * mm)
            c.setFont("Helvetica-Bold", 9.5)
            c.setFillColor(INK)
            c.drawCentredString(x, base_y + 7 * mm, name)
            c.setFont("Helvetica", 8)
            c.setFillColor(GREY)
            c.drawCentredString(x, base_y + 2.5 * mm, f"{role} - {sub}")

        # certificate id strip
        strip_h = 14 * mm
        c.setFillColor(LIGHT)
        c.rect(16 * mm, 16 * mm, width - 32 * mm, strip_h, stroke=0, fill=1)
        c.setFillColor(MAROON_DARK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, 16 * mm + strip_h / 2 + 1 * mm, f"Certificate ID: {certificate.certificate_id}")
        c.setFont("Helvetica", 8)
        c.setFillColor(GREY)
        c.drawRightString(
            width - 20 * mm,
            16 * mm + strip_h / 2 + 1 * mm,
            f"Issued on {certificate.issued_at.strftime('%d %B %Y') if certificate.issued_at else '-'}",
        )
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(
            width / 2.0,
            16 * mm + strip_h / 2 + 1 * mm,
            "Verified by CEMS - AGC Campus Event Management System",
        )

        c.showPage()
        c.save()
        return buffer.getvalue()
    except CertificateError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise CertificateError(f"Could not build certificate PDF: {exc}") from exc


def build_attendance_record_pdf(registrations, student):
    """Personal attendance record PDF that a student can download."""
    try:
        buffer = io.BytesIO()
        page = landscape(A4)
        c = pdfcanvas.Canvas(buffer, pagesize=page)
        page_w, page_h = page
        margin = 15 * mm

        c.setFillColor(MAROON)
        c.rect(0, page_h - 16 * mm, page_w, 16 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, page_h - 10.5 * mm, f"CEMS  |  {SYSTEM_NAME}")
        c.setFont("Helvetica", 9)
        c.drawRightString(page_w - margin, page_h - 10.5 * mm, ORG_NAME + ", Amritsar")

        y = page_h - 26 * mm
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(margin, y, "Personal Attendance Record")
        y -= 6 * mm
        c.setFont("Helvetica", 9.5)
        c.setFillColor(GREY)
        c.drawString(
            margin,
            y,
            f"Student: {student.name}   |   {student.roll_number or '-'}   |   {student.department or '-'}   |   {student.email}",
        )
        y -= 10 * mm

        columns = [10 * mm, 78 * mm, 45 * mm, 35 * mm, 35 * mm, 40 * mm]
        headers = ["#", "Event", "Date", "Registration ID", "Attendance", "Marked On"]
        row_h = 8 * mm

        def draw_header(top):
            c.setFillColor(MAROON)
            c.rect(margin, top - row_h, sum(columns), row_h, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 8.5)
            x = margin
            for col, label in zip(columns, headers):
                c.drawString(x + 2 * mm, top - row_h + 2.8 * mm, label)
                x += col
            return top - row_h

        y = draw_header(y)
        c.setFont("Helvetica", 8)
        for index, reg in enumerate(registrations, start=1):
            if y - row_h < margin:
                c.showPage()
                page_w, page_h = page
                c.setFillColor(INK)
                c.setFont("Helvetica-Bold", 12)
                c.drawString(margin, page_h - 10 * mm, f"CEMS  |  {SYSTEM_NAME}")
                y = draw_header(page_h - 18 * mm)
                c.setFont("Helvetica", 8)
            if index % 2 == 0:
                c.setFillColor(LIGHT)
                c.rect(margin, y - row_h, sum(columns), row_h, stroke=0, fill=1)
            c.setFillColor(INK)
            attendance = reg.attendance
            values = [
                str(index),
                (reg.event.title or "")[:46],
                reg.event.event_date.strftime("%d %b %Y"),
                reg.registration_id,
                reg.attendance_status,
                attendance.marked_at.strftime("%d %b %Y") if attendance and attendance.marked_at else "-",
            ]
            x = margin
            for col, value in zip(columns, values):
                c.drawString(x + 2 * mm, y - row_h + 2.8 * mm, str(value))
                x += col
            y -= row_h

        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(GREY)
        c.drawString(
            margin,
            margin / 2,
            f"Generated on {datetime.now():%d %B %Y %H:%M} | CEMS | {SYSTEM_NAME} | "
            f"Amritsar Group of Colleges, Amritsar",
        )
        c.showPage()
        c.save()
        return buffer.getvalue()
    except Exception as exc:  # pragma: no cover - defensive
        raise CertificateError(f"Could not build attendance record PDF: {exc}") from exc


def build_attendance_report_pdf(event, registrations, marked_by=None):
    """Attendance register PDF for an event (faculty / organizer use)."""
    try:
        buffer = io.BytesIO()
        c = pdfcanvas.Canvas(buffer, pagesize=landscape(A4))
        page_w, page_h = landscape(A4)
        margin = 15 * mm

        title_style = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=16, textColor=MAROON_DARK, alignment=TA_CENTER)
        sub_style = ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, textColor=GREY, alignment=TA_CENTER)

        header = [
            Paragraph(f"<b>CEMS | {SYSTEM_NAME}</b>", title_style),
            Paragraph(ORG_NAME + ", Amritsar &mdash; Attendance Register", sub_style),
            Paragraph(f"<b>{event.title}</b>", sub_style),
            Paragraph(
                f"{event.event_date.strftime('%d %B %Y')} &nbsp;|&nbsp; {event.time_range} "
                f"&nbsp;|&nbsp; {event.venue}",
                sub_style,
            ),
        ]
        y = page_h - margin
        for flow in header:
            w, h = flow.wrap(page_w - 2 * margin, 100)
            flow.drawOn(c, margin, y - h)
            y -= h + 2 * mm

        columns = [12 * mm, 55 * mm, 45 * mm, 45 * mm, 40 * mm, 45 * mm]
        headers = ["#", "Student", "Registration ID", "Department", "Roll No", "Attendance"]
        row_h = 9 * mm

        def draw_header():
            nonlocal y
            c.setFillColor(MAROON)
            c.rect(margin, y - row_h, sum(columns), row_h, stroke=0, fill=1)
            x = margin
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 9)
            for col, label in zip(columns, headers):
                c.drawString(x + 2 * mm, y - row_h + 3 * mm, label)
                x += col
            y -= row_h

        draw_header()
        c.setFont("Helvetica", 8.5)
        for index, reg in enumerate(registrations, start=1):
            if y - row_h < margin:
                c.showPage()
                y = page_h - margin
                draw_header()
                c.setFont("Helvetica", 8.5)
            if index % 2 == 0:
                c.setFillColor(LIGHT)
                c.rect(margin, y - row_h, sum(columns), row_h, stroke=0, fill=1)
            c.setFillColor(INK)
            student = reg.student
            values = [
                str(index),
                (student.name if student else "-")[:34],
                reg.registration_id,
                (student.department if student else "-")[:22] or "-",
                (student.roll_number if student else "-") or "-",
                reg.attendance_status,
            ]
            x = margin
            for col, value in zip(columns, values):
                c.drawString(x + 2 * mm, y - row_h + 3 * mm, str(value))
                x += col
            y -= row_h

        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(GREY)
        footer = (
            f"Generated on {datetime.now():%d %B %Y %H:%M} by "
            f"{marked_by.name if marked_by else 'CEMS'} | CEMS | {SYSTEM_NAME}"
        )
        c.drawString(margin, margin / 2, footer)

        c.showPage()
        c.save()
        return buffer.getvalue()
    except Exception as exc:  # pragma: no cover - defensive
        raise CertificateError(f"Could not build attendance report PDF: {exc}") from exc