"""Ties validation, GitHub fetching, analysis and caching together."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .cache import TTLCache
from .config import Settings
from .github_client import GitHubClient
from .report import build_report
from .samples import build_sample
from .validation import clean_username, is_sample


class ReportService:
    def __init__(self, settings: Settings, github: Optional[GitHubClient] = None,
                 cache: Optional[TTLCache] = None, gemini_session: Any = None):
        self._settings = settings
        self._cache = cache or TTLCache(settings.cache_ttl_seconds)
        self._github = github or GitHubClient(settings.github_token, self._cache,
                                              timeout=settings.request_timeout)
        self._gemini_session = gemini_session

    def analyze(self, raw_username: Any) -> Dict[str, Any]:
        """Validate the username, then return a (cached) report. Raises ValidationError or GitHubError."""
        username = clean_username(raw_username)
        return self._cache.get_or_set(("report", username.lower()), lambda: self._build(username))

    def _build(self, username: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        if is_sample(username):
            snapshot = build_sample(username, now)
        else:
            snapshot = self._github.fetch_snapshot(username, self._settings.max_repos)
        return build_report(snapshot, now, self._settings.gemini_api_key,
                            self._settings.gemini_model, self._gemini_session)
