"""Application settings, read from environment variables (no secrets in code)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class Settings:
    github_token: Optional[str] = None      # optional: raises the GitHub limit from 60 to 5000 requests/hour
    gemini_api_key: Optional[str] = None    # optional: without it the app uses its built-in templates
    gemini_model: str = "gemini-2.5-flash"
    cache_ttl_seconds: int = 3600
    max_repos: int = 6                      # repositories analysed in depth (about 3 API calls each)
    request_timeout: int = 10
    rate_limit_per_minute: int = 10         # per-visitor limit on /api/analyze


def _int(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    """Read an integer setting, falling back to the default when missing or invalid."""
    try:
        value = int(env.get(name, default))
    except (TypeError, ValueError):
        return default
    return min(max(value, low), high)


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    """Build Settings from the environment (or a mapping, which makes tests easy)."""
    env = os.environ if env is None else env
    return Settings(
        github_token=env.get("GITHUB_TOKEN") or None,
        gemini_api_key=env.get("GEMINI_API_KEY") or None,
        gemini_model=env.get("GEMINI_MODEL") or "gemini-2.5-flash",
        cache_ttl_seconds=_int(env, "CACHE_TTL_SECONDS", 3600, 0, 86400),
        max_repos=_int(env, "MAX_REPOS", 6, 1, 12),
        request_timeout=_int(env, "REQUEST_TIMEOUT", 10, 1, 60),
        rate_limit_per_minute=_int(env, "RATE_LIMIT_PER_MINUTE", 10, 1, 600),
    )
