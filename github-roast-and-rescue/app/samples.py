"""Offline SAMPLE profiles (strong, messy, empty). Used by the demo and by the tests.

These are made-up data in the shape of real GitHub responses. Links point at github.com paths
that do not exist, and the UI labels them as sample data.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from .models import Commit, Profile, RepoData, Snapshot

LONG_README = ("# {name}\n\nA small tool that does one job well.\n\n## Installation\n\n```bash\npip install -r "
               "requirements.txt\n```\n\n## Usage\n\n```bash\npython main.py --help\n```\n\n## Tests\n\n"
               "```bash\npython -m unittest\n```\n") + "More details about design choices follow here. " * 4


def _commits(login: str, repo: str, now: datetime, messages: List[str], spacing_days: int) -> List[Commit]:
    return [Commit(sha=f"{i:040d}", message=msg, date=now - timedelta(days=5 + i * spacing_days),
                   url=f"https://github.com/{login}/{repo}/commit/{i:040d}")
            for i, msg in enumerate(messages)]


def _repo(login: str, name: str, now: datetime, days_ago: int, **kw) -> RepoData:
    return RepoData(name=name, html_url=f"https://github.com/{login}/{name}",
                    pushed_at=now - timedelta(days=days_ago), **kw)


def _strong(now: datetime) -> Snapshot:
    login = "sample_strong"
    good = ["Add input validation", "Cache GitHub responses", "Fix off-by-one in pagination",
            "Document setup steps", "Add tests for scoring", "Handle empty profiles"]
    repos = [
        _repo(login, name, now, days, description=f"{name}: a focused tool with docs and tests",
              language="Python", stars=3, size_kb=400, license="MIT", topics=["python", "cli"],
              readme=LONG_README.format(name=name), tree_paths=["app/main.py", "tests/test_main.py", "README.md"],
              commits=_commits(login, name, now, good, 40))
        for name, days in [("budget-tracker", 6), ("study-planner", 20), ("log-parser", 45), ("recipe-api", 70)]]
    return Snapshot(
        profile=Profile(login=login, html_url=f"https://github.com/{login}", avatar_url="", name="Sample Strong",
                        bio="Backend developer who likes small, well-tested tools.", blog="https://example.com",
                        location="Chennai", public_repos=4, followers=25, created_at=now - timedelta(days=900)),
        repos=repos, own_repo_count=4, fork_count=1, profile_readme="# Hi\n\nI build small tools.",
        push_event_dates=[now - timedelta(days=2)], sample=True)


def _messy(now: datetime) -> Snapshot:
    login = "sample_messy"
    vague = ["update", "fix", "changes", "Update main.py", "stuff", "fix"]
    repos = [
        _repo(login, "test", now, 700, language="Python", size_kb=12, tree_paths=["main.py"],
              commits=_commits(login, "test", now, vague, 3)),
        _repo(login, "untitled-project", now, 520, language="JavaScript", size_kb=80, readme="# untitled-project",
              tree_paths=["index.js", "package.json"], commits=_commits(login, "untitled-project", now, vague, 2)),
        _repo(login, "myapp", now, 400, language="Python", size_kb=300, description="app",
              readme="# myapp\n\nTODO", tree_paths=["app.py", "utils.py"],
              commits=_commits(login, "myapp", now, vague[:4], 5)),
        _repo(login, "new-repo", now, 380, language="Java", size_kb=0, is_empty=True),
    ]
    return Snapshot(
        profile=Profile(login=login, html_url=f"https://github.com/{login}", avatar_url="", name=None, bio=None,
                        public_repos=4, followers=1, created_at=now - timedelta(days=900)),
        repos=repos, own_repo_count=4, fork_count=3, profile_readme=None, push_event_dates=[], sample=True)


def _empty(now: datetime) -> Snapshot:
    login = "sample_empty"
    return Snapshot(
        profile=Profile(login=login, html_url=f"https://github.com/{login}", avatar_url="", name=None, bio=None,
                        public_repos=2, followers=0, created_at=now - timedelta(days=30)),
        repos=[], own_repo_count=0, fork_count=2, profile_readme=None, push_event_dates=[], sample=True)


_BUILDERS = {"sample_strong": _strong, "sample_messy": _messy, "sample_empty": _empty}


def build_sample(username: str, now: Optional[datetime] = None) -> Snapshot:
    """Return the offline sample profile with this name, with dates relative to `now`."""
    from datetime import timezone
    return _BUILDERS[username](now or datetime.now(timezone.utc))
