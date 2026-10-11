from __future__ import annotations

import hashlib
import hmac
import os
import re


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Create a salted password hash using PBKDF2."""
    current_salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), current_salt, 120000)
    return f"{current_salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored_value: str) -> bool:
    """Verify a plaintext password against a stored salt:hash value."""
    try:
        salt_hex, hash_hex = stored_value.split(":", 1)
    except ValueError:
        return False
    candidate = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, stored_value)


def validate_username(username: str) -> tuple[bool, str]:
    """Validate username format for local accounts."""
    cleaned = (username or "").strip()
    if not cleaned:
        return False, "Username is required."
    if not USERNAME_PATTERN.fullmatch(cleaned):
        return False, "Username must be 3-32 characters and use only letters, numbers, dot, underscore, or dash."
    return True, ""


def validate_password_strength(password: str, username: str = "") -> tuple[bool, str]:
    """Validate password strength for local accounts."""
    value = password or ""
    if len(value) < 8:
        return False, "Password must be at least 8 characters long."
    if username and username.strip().lower() in value.lower():
        return False, "Password should not contain the username."
    if not re.search(r"[A-Z]", value):
        return False, "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", value):
        return False, "Password must include at least one lowercase letter."
    if not re.search(r"\d", value):
        return False, "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", value):
        return False, "Password must include at least one special character."
    return True, ""
