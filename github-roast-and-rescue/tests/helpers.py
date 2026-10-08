"""Shared test helpers: a fixed clock and fake HTTP objects (no network is ever used)."""
from datetime import datetime, timezone

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status=200, data=None, headers=None, text=""):
        self.status_code = status
        self._data = data
        self.headers = headers or {}
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._data


class FakeSession:
    """Serves canned GitHub responses by path and counts how many requests were made."""

    def __init__(self, routes):
        self.routes = routes          # path -> FakeResponse
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        path = url.replace("https://api.github.com", "")
        self.calls.append(path)
        return self.routes.get(path, FakeResponse(404, None))

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        return FakeResponse(200, {"data": {"user": {"pinnedItems": {"nodes": []}}}})
