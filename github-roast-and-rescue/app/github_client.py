"""Reads public profile data from the GitHub REST API, with caching and rate-limit handling."""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from .cache import TTLCache
from .models import Commit, Profile, RepoData, Snapshot

API = "https://api.github.com"
README_LIMIT = 20_000      # characters of README text kept per repository
COMMITS_PER_REPO = 30      # recent commits sampled per analysed repository


class GitHubError(Exception):
    """Something went wrong while talking to GitHub."""


class UserNotFound(GitHubError):
    """No public GitHub user has this name."""


class NotAUser(GitHubError):
    """The account exists but is an organisation, not a person."""


class RateLimited(GitHubError):
    """GitHub's rate limit was reached."""

    def __init__(self, reset_at: Optional[int] = None):
        super().__init__("GitHub rate limit reached")
        self.reset_at = reset_at


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse GitHub's ISO timestamps into timezone-aware datetimes."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class GitHubClient:
    def __init__(self, token: Optional[str], cache: TTLCache,
                 session: Optional[requests.Session] = None, timeout: int = 10):
        self._token = token
        self._cache = cache
        self._session = session or requests.Session()
        self._timeout = timeout

    # ---- low-level HTTP -------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-roast-and-rescue",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @staticmethod
    def _raise_if_rate_limited(response: Any) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        limited = response.status_code == 429 or (
            response.status_code == 403
            and (remaining == "0" or "rate limit" in (response.text or "").lower())
        )
        if limited:
            reset = response.headers.get("X-RateLimit-Reset")
            raise RateLimited(int(reset) if reset and reset.isdigit() else None)

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        """GET a path and return (status, json). 404 and 409 are returned, not raised. Cached."""
        key = ("GET", path, tuple(sorted((params or {}).items())))
        hit, cached = self._cache.get(key)
        if hit:
            return cached
        try:
            response = self._session.get(API + path, headers=self._headers(),
                                         params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            raise GitHubError("Could not reach GitHub. Please try again.") from exc
        self._raise_if_rate_limited(response)
        if response.status_code in (404, 409):
            result: Tuple[int, Any] = (response.status_code, None)
        elif response.ok:
            result = (response.status_code, response.json())
        else:
            raise GitHubError(f"GitHub returned an unexpected status ({response.status_code}).")
        self._cache.set(key, result)
        return result

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request(path, params)[1]

    # ---- building blocks ------------------------------------------------

    def _readme_text(self, owner: str, repo: str) -> Optional[str]:
        data = self._get(f"/repos/{owner}/{repo}/readme")
        if not data:
            return None
        try:
            return base64.b64decode(data.get("content", "")).decode("utf-8", "replace")[:README_LIMIT]
        except (ValueError, TypeError):
            return ""

    def _pinned_names(self, login: str) -> Optional[List[str]]:
        """Pinned repositories exist only in GraphQL, which requires a token. None means unknown."""
        if not self._token:
            return None
        key = ("PINNED", login)
        hit, cached = self._cache.get(key)
        if hit:
            return cached
        query = ("query($login:String!){user(login:$login){pinnedItems(first:6,types:REPOSITORY)"
                 "{nodes{... on Repository{name}}}}}")
        try:
            response = self._session.post(API + "/graphql", headers=self._headers(),
                                          json={"query": query, "variables": {"login": login}},
                                          timeout=self._timeout)
            nodes = response.json()["data"]["user"]["pinnedItems"]["nodes"]
            names: Optional[List[str]] = [n["name"] for n in nodes if n]
        except (requests.RequestException, ValueError, KeyError, TypeError):
            names = None
        self._cache.set(key, names)
        return names

    def _deep_repo(self, owner: str, raw: Dict[str, Any], pinned: List[str]) -> RepoData:
        """Fetch the README, file list and recent commits for one repository."""
        name = raw["name"]
        lic = raw.get("license") or {}
        repo = RepoData(
            name=name,
            html_url=raw["html_url"],
            description=raw.get("description"),
            language=raw.get("language"),
            stars=raw.get("stargazers_count", 0),
            size_kb=raw.get("size", 0),
            pushed_at=parse_datetime(raw.get("pushed_at")),
            license=lic.get("spdx_id") or lic.get("name"),
            topics=raw.get("topics") or [],
            archived=bool(raw.get("archived")),
            pinned=name in pinned,
        )
        branch = raw.get("default_branch") or "HEAD"
        status, tree = self._request(f"/repos/{owner}/{name}/git/trees/{branch}", {"recursive": "1"})
        if status == 409:                       # GitHub's answer for an empty repository
            repo.is_empty = True
            return repo
        if tree and not tree.get("truncated"):
            repo.tree_paths = [item["path"] for item in tree.get("tree", [])]
        repo.readme = self._readme_text(owner, name)
        commits = self._get(f"/repos/{owner}/{name}/commits",
                            {"per_page": COMMITS_PER_REPO, "author": owner}) or []
        for item in commits:
            info = item.get("commit", {})
            repo.commits.append(Commit(
                sha=item.get("sha", ""),
                message=(info.get("message") or "").split("\n", 1)[0].strip(),
                date=parse_datetime((info.get("author") or {}).get("date")),
                url=item.get("html_url", repo.html_url),
            ))
        return repo

    # ---- public entry point ---------------------------------------------

    def fetch_snapshot(self, username: str, max_repos: int = 6) -> Snapshot:
        """Collect everything the analyzer needs about one GitHub user."""
        user = self._get(f"/users/{username}")
        if user is None:
            raise UserNotFound(username)
        if user.get("type") != "User":
            raise NotAUser(username)
        login = user["login"]
        profile = Profile(
            login=login, html_url=user["html_url"], avatar_url=user.get("avatar_url", ""),
            name=user.get("name"), bio=user.get("bio"), company=user.get("company"),
            location=user.get("location"), blog=user.get("blog") or None,
            public_repos=user.get("public_repos", 0), followers=user.get("followers", 0),
            created_at=parse_datetime(user.get("created_at")),
        )
        raw_repos = self._get(f"/users/{login}/repos",
                              {"per_page": 100, "type": "owner", "sort": "pushed"}) or []
        own = [r for r in raw_repos if not r.get("fork")]
        pinned = self._pinned_names(login)
        by_name = {r["name"]: r for r in own}
        ordered = [by_name[n] for n in (pinned or []) if n in by_name]
        ordered += [r for r in own if r not in ordered]       # already sorted by last push
        chosen = ordered[:max_repos] if len(own) >= 2 else []   # nearly empty profiles skip deep reads
        events = self._get(f"/users/{login}/events/public", {"per_page": 100}) or []
        push_dates = [d for d in (parse_datetime(e.get("created_at")) for e in events
                                  if e.get("type") == "PushEvent") if d]
        return Snapshot(
            profile=profile,
            repos=[self._deep_repo(login, r, pinned or []) for r in chosen],
            own_repo_count=len(own),
            fork_count=len(raw_repos) - len(own),
            profile_readme=self._readme_text(login, login),
            push_event_dates=push_dates,
            pinned_known=pinned is not None,
            repo_list_truncated=profile.public_repos > len(raw_repos),
        )
