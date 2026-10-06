class QRServiceError(RuntimeError):
    """Raised when a QR code cannot be produced."""


class CertificateError(RuntimeError):
    """Raised when a certificate PDF cannot be produced."""


class EmailError(RuntimeError):
    """Raised when an email could not be delivered."""