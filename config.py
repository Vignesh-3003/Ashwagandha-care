"""Configuration, read from the environment (or a .env file).

Every value has a safe default so `python app.py` works with no setup at all.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _list(name: str) -> list[str]:
    raw = os.getenv(name, "") or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


class Config:
    """Flask configuration plus the settings the services need."""

    # ---- server -----------------------------------------------------------
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = _int("PORT", 5000)
    DEBUG = os.getenv("FLASK_DEBUG", "0") in {"1", "true", "True"}
    SECRET_KEY = os.getenv("SECRET_KEY", "ashwacare-dev-key")

    # 30 MB is what the page advertises. The slack covers multipart overhead;
    # services.imaging enforces the real ceiling on the image bytes themselves.
    MAX_IMAGE_MB = _int("MAX_IMAGE_MB", 30)
    MAX_CONTENT_LENGTH = (MAX_IMAGE_MB + 2) * 1024 * 1024

    # ---- image pipeline ---------------------------------------------------
    MAX_EDGE_PX = _int("MAX_EDGE_PX", 1600)
    JPEG_QUALITY = _int("JPEG_QUALITY", 82)

    # ---- vision model -----------------------------------------------------
    PROVIDER = (os.getenv("PROVIDER", "") or "").strip().lower()
    MODEL = (os.getenv("MODEL", "") or "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL_TIMEOUT = _int("MODEL_TIMEOUT_MS", 45000) / 1000.0

    # ---- abuse control and caching ---------------------------------------
    RATE_WINDOW_SECONDS = _int("RATE_WINDOW_MS", 900000) / 1000.0
    RATE_ANALYZE = _int("RATE_ANALYZE", 60)
    RATE_CHAT = _int("RATE_CHAT", 120)
    CACHE_MAX = _int("CACHE_MAX", 300)
    CACHE_TTL_SECONDS = _int("CACHE_TTL_MS", 21600000) / 1000.0

    # ---- CORS -------------------------------------------------------------
    ALLOWED_ORIGINS = _list("ALLOWED_ORIGINS")

    # Where the browser should send /api requests. Empty = same origin.
    API_BASE = os.getenv("API_BASE", "")
