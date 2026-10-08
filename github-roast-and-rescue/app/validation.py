"""Input validation for user-supplied data."""
from __future__ import annotations

import re
from typing import Any

# GitHub rules: 1-39 characters, letters/digits/single hyphens, no leading or trailing hyphen.
_USERNAME_RE = re.compile(r"^(?!.*--)[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
# Offline sample profiles. Underscores are illegal in real GitHub names, so these never collide.
_SAMPLE_RE = re.compile(r"^sample_(strong|messy|empty)$")
_URL_PREFIX_RE = re.compile(r"^https?://(www\.)?github\.com/", re.IGNORECASE)


class ValidationError(ValueError):
    """Raised when user input is not acceptable."""


def is_sample(username: str) -> bool:
    """True for the built-in offline sample profiles."""
    return bool(_SAMPLE_RE.match(username))


def clean_username(raw: Any) -> str:
    """Normalise and validate a GitHub username (accepts '@name' and profile URLs too)."""
    if not isinstance(raw, str):
        raise ValidationError("Enter a GitHub username.")
    value = raw.strip()
    if len(value) > 200:
        raise ValidationError("That is too long to be a GitHub username.")
    value = _URL_PREFIX_RE.sub("", value).lstrip("@").split("/")[0].split("?")[0]
    if not value:
        raise ValidationError("Enter a GitHub username.")
    if _SAMPLE_RE.match(value):
        return value
    if not _USERNAME_RE.match(value):
        raise ValidationError(
            "Usernames use letters, numbers and single hyphens only, up to 39 characters."
        )
    return value
