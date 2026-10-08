"""Plain data containers shared by the GitHub client, the analyzer and the report builder."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Profile:
    login: str
    html_url: str
    avatar_url: str = ""
    name: Optional[str] = None
    bio: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    blog: Optional[str] = None
    public_repos: int = 0
    followers: int = 0
    created_at: Optional[datetime] = None


@dataclass
class Commit:
    sha: str
    message: str            # first line only
    date: Optional[datetime]
    url: str


@dataclass
class RepoData:
    name: str
    html_url: str
    description: Optional[str] = None
    language: Optional[str] = None
    stars: int = 0
    size_kb: int = 0
    pushed_at: Optional[datetime] = None
    license: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    archived: bool = False
    pinned: bool = False
    is_empty: bool = False                       # GitHub reported an empty repository
    readme: Optional[str] = None                 # None means no README was found
    tree_paths: Optional[List[str]] = None       # None means the file list is unknown
    commits: List[Commit] = field(default_factory=list)  # recent commits authored by the owner


@dataclass
class Snapshot:
    """Everything fetched about one profile, before any judgement is made."""
    profile: Profile
    repos: List[RepoData]                        # repositories analysed in depth
    own_repo_count: int                          # public repositories that are not forks
    fork_count: int
    profile_readme: Optional[str] = None         # README of the username/username repository
    push_event_dates: List[datetime] = field(default_factory=list)
    pinned_known: bool = False                   # True when pinned repositories could be read
    repo_list_truncated: bool = False            # True when the owner has more than 100 repositories
    sample: bool = False                         # True for the offline sample profiles
