"""Small helpers used across CEMS views and templates."""

import re
from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import request
from werkzeug.utils import secure_filename

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

SLUG_RE = re.compile(r"[^a-z0-9]+")


def safe_next(target, fallback_endpoint="main.role_home"):
    """Only allow same-host relative redirects."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    if not target.startswith("/"):
        return None
    return target


def slugify(value, max_length=60):
    slug = SLUG_RE.sub("-", (value or "").lower()).strip("-")
    return (slug or "item")[:max_length]


def parse_date(value, field_label="Date"):
    if not value:
        return None, f"{field_label} is required."
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date(), None
        except ValueError:
            continue
    return None, f"{field_label} must be a valid date (YYYY-MM-DD)."


def parse_time(value, field_label="Time"):
    if not value:
        return None, f"{field_label} is required."
    value = value.strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(value, fmt).time(), None
        except ValueError:
            continue
    return None, f"{field_label} must be a valid time (HH:MM)."


def parse_datetime(value, field_label="Date & time"):
    if not value:
        return None, f"{field_label} is required."
    value = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt), None
        except ValueError:
            continue
    return None, f"{field_label} must be a valid date and time."


def format_date(value):
    if not value:
        return "-"
    if isinstance(value, datetime):
        return f"{value.day} {MONTHS[value.month - 1]} {value.year}"
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def format_date_time(value):
    if not value:
        return "-"
    return value.strftime("%d %b %Y, %I:%M %p")


def format_time(value):
    if not value:
        return "-"
    return value.strftime("%I:%M %p")


def allowed_file(filename, allowed_extensions):
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].strip().lower()
    return ext in allowed_extensions


def unique_filename(original, suffix=""):
    name = secure_filename(original or "")
    stem, _, ext = name.partition(".")
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{stem or 'image'}_{stamp}{suffix}.{ext}" if ext else f"{stem}{stamp}{suffix}"


def current_filters():
    """Query string filters applied to event and feedback listings."""
    allowed = {"q", "category", "status", "date_from", "date_to", "scope", "rating"}
    return {k: v for k, v in request.args.items(multi=False) if k in allowed and v}


def build_query_string(**overrides):
    params = request.args.to_dict()
    for key, value in overrides.items():
        if value in (None, "", "all"):
            params.pop(key, None)
        else:
            params[key] = value
    from urllib.parse import urlencode

    return urlencode(params)


def rating_stars(rating):
    rating = int(round(float(rating or 0)))
    return "".join(["&#9733;" if i <= rating else "&#9734;" for i in range(1, 6)])


def initials_of(name):
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "AG"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def truncate(text, length=140):
    text = (text or "").strip()
    return text if len(text) <= length else text[: length - 1].rstrip() + "\u2026"


def absolute_url(endpoint, **values):
    from flask import url_for

    path = url_for(endpoint, **values)
    return urljoin(request.url_root, path)