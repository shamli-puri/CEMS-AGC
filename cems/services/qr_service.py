"""QR code generation helpers.

Uses the pure-python `qrcode` library. If Pillow is unavailable the module
degrades gracefully to an SVG renderer so the application never crashes.
"""

import io
import logging

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from .errors import QRServiceError  # noqa: F401  (re-exported)

logger = logging.getLogger(__name__)


def build_qr_payload(registration):
    """Text encoded inside the ticket QR code (kept short and verifiable)."""
    return f"AGC-CEMS|{registration.registration_id}|{registration.id}"


def qr_png_bytes(payload, box_size=10, border=2):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#1b1b2f", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


def qr_svg(payload, box_size=10, border=2):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    # ``qrcode.image.svg`` is an optional submodule and is not imported by
    # default, so import it explicitly before looking the factory up.
    try:
        from qrcode.image import svg as svg_module
    except ImportError as exc:  # pragma: no cover - very old qrcode builds
        raise QRServiceError("SVG QR rendering unavailable") from exc

    factory = getattr(qrcode.image, "svg", None) or svg_module
    buffer = io.BytesIO()
    qr.make_image(image_factory=svg_module.SvgImage).save(buffer)
    return buffer.read()


def qr_data_uri(payload, box_size=8):
    import base64

    encoded = base64.b64encode(qr_png_bytes(payload, box_size=box_size)).decode("ascii")
    return f"data:image/png;base64,{encoded}"