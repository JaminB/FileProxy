# config/env.py
from __future__ import annotations

import base64
import os


def env(name: str, default=None, *, required: bool = False) -> str | None:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def env_bool(name: str, default: bool = False) -> bool:
    val = env(name, str(default)).strip().lower()
    return val in {"1", "true", "yes", "y", "on"}


def env_bytes_b64url(name: str, *, required: bool = False, expected_len: int | None = None) -> bytes:
    """
    Reads a URL-safe base64 string from env and returns decoded bytes.
    """
    raw = env(name, required=required)
    assert raw is not None  # for type checkers

    try:
        decoded = base64.urlsafe_b64decode(raw.encode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid urlsafe base64 for {name}") from exc

    if expected_len is not None and len(decoded) != expected_len:
        raise RuntimeError(f"{name} must decode to {expected_len} bytes (got {len(decoded)})")

    return decoded