"""Configuration objects for CEMS - AGC Campus Event Management System."""

import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

TRUE_VALUES = {"1", "true", "yes", "on"}


def _flag(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def _int(name, default):
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class Config:
    """Base configuration shared by every environment."""

    APP_NAME = "CEMS"
    APP_TITLE = "AGC Campus Event Management System"
    ORG_NAME = "Amritsar Group of Colleges"
    ORG_SHORT = "AGC"
    ORG_PLACE = "Amritsar, Punjab"
    APP_VERSION = "1.0.0"

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-me-in-production"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///" + os.path.join(
        INSTANCE_DIR, "cems_agc.sqlite3"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"future": True}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    MAX_CONTENT_LENGTH = 4 * 1024 * 1024
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or os.path.join(BASE_DIR, "static", "uploads")
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

    MAIL_ENABLED = _flag("MAIL_ENABLED", False)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USE_TLS = _flag("MAIL_USE_TLS", True)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "cems.agc@example.com")
    MAIL_LOG_FILE = os.environ.get("MAIL_LOG_FILE") or os.path.join(INSTANCE_DIR, "emails.log")

    SEED_ON_START = _flag("SEED_ON_START", True)
    DB_AUTO_CREATE = _flag("DB_AUTO_CREATE", True)


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "testing-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_SESSION_OPTIONS = {"expire_on_commit": False}
    WTF_CSRF_ENABLED = False
    SEED_ON_START = False
    MAIL_ENABLED = False
    SERVER_NAME = "localhost.localdomain"


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", False)


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name=None):
    key = (name or os.environ.get("FLASK_ENV") or "development").strip().lower()
    return CONFIG_MAP.get(key, DevelopmentConfig)