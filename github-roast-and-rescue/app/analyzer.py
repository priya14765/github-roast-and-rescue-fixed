"""Turns a Snapshot into evidence-backed findings and a deterministic 0-100 score.

Score (100): Profile 20 + Repository quality 50 + Activity 20 + Finishing 10.
Every finding carries a link and the exact detail that is missing, so nothing is guessed.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .models import RepoData, Snapshot

# ---- scoring weights --------------------------------------------------------
PROFILE_MAX, REPO_MAX, ACTIVITY_MAX, FINISH_MAX = 20, 50, 20, 10
W_BIO, W_PROFILE_README, W_CONTACT = 5, 10, 5
W_DESC, W_README, W_README_FULL, W_LICENSE, W_TESTS, W_TOPICS = 10, 10, 10, 6, 10, 4
W_RECENT, W_CONSISTENT = 12, 8
W_NOT_ABANDONED, W_COMMIT_MESSAGES = 7, 3

ABANDONED_AFTER_DAYS = 365
MIN_OWN_REPOS_TO_SCORE = 2

# ---- detection patterns -----------------------------------------------------
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|specs?)(/|$)|(^|/)test_[^/]+\.py$|_test\.(py|go)$"
    r"|\.(test|spec)\.[jt]sx?$|(^|/)test\.(js|ts|py)$", re.IGNORECASE)
USAGE_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*(install|installation|setup|set up|getting started|usage|how to|run|running|quick ?start)",
    re.IGNORECASE | re.MULTILINE)
VAGUE_COMMIT_RE = re.compile(
    r"^(update|updates|fix|fixes|change|changes|commit|stuff|wip|asdf|misc|test|tests|final|done"
    r"|minor changes?|\.+|(create|update|delete) \S+|add files via upload)$", re.IGNORECASE)
NO_TESTS_EXPECTED = {"HTML", "CSS", "SCSS", "Jupyter Notebook", "TeX", "Markdown"}
THIN_README_CHARS = 200

GRADES = [(85, "A", "Strong"), (70, "B", "Solid"), (55, "C", "Getting there"), (40, "D", "Needs work")]


@dataclass
class Finding:
    code: str
    title: str
    detail: str            # the exact thing that is missing, in plain words
    url: str               # where to see it
    impact: float          # points lost in the score because of this
    repo: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Analysis:
    mode: str                                  # "scored" or "starter"
    score: Optional[int] = None
    grade: Optional[str] = None
    grade_label: Optional[str] = None
    breakdown: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    strengths: List[Dict[str, str]] = field(default_factory=list)
    picks: List[Dict[str, Any]] = field(default_factory=list)
    activity_months: List[Dict[str, Any]] = field(default_factory=list)
    latest_activity: Optional[datetime] = None


def grade_for(score: float):
    """Map a score to (letter, label)."""
    for floor, letter, label in GRADES:
        if score >= floor:
            return letter, label
    return "E", "Early days"


def _days_since(moment: datetime, now: datetime) -> int:
    return max((now - moment).days, 0)


def _is_vague(message: str) -> bool:
    return bool(VAGUE_COMMIT_RE.match(message.strip()))


# ---- profile-level checks ---------------------------------------------------

def profile_findings(snap: Snapshot) -> List[Finding]:
    """Checks on the profile page itself (bio, profile README, contact details)."""
    p = snap.profile
    found: List[Finding] = []
    if not (p.bio or "").strip():
        found.append(Finding("no_bio", "No bio", "The bio field on the profile is empty.",
                             p.html_url, W_BIO))
    if snap.profile_readme is None:
        found.append(Finding("no_profile_readme", "No profile README",
                             f"The repository {p.login}/{p.login} does not exist or has no README, "
                             "so the profile page shows no introduction.",
                             f"https://github.com/{p.login}/{p.login}", W_PROFILE_README))
    if not any((p.blog, p.location, p.company)):
        found.append(Finding("no_contact", "No way to reach you",
                             "Website, location and company are all empty.", p.html_url, W_CONTACT))
    return found


# ---- per-repository checks --------------------------------------------------

def _repo_findings(repo: RepoData, n_repos: int):
    """Return (ratio_earned, findings) for the repository-quality part of the score."""
    if repo.is_empty:
        return 0.0, [Finding("empty_repo", "Empty repository",
                             "GitHub reports this repository has no commits or files.",
                             repo.html_url, REPO_MAX / n_repos, repo.name)]
    tests_expected = (repo.tree_paths is not None and repo.language is not None
                      and repo.language not in NO_TESTS_EXPECTED)
    available = W_DESC + W_README + W_README_FULL + W_LICENSE + W_TOPICS + (W_TESTS if tests_expected else 0)
    lost = 0.0
    found: List[Finding] = []

    def add(code: str, title: str, detail: str, weight: float, **data: Any) -> None:
        nonlocal lost
        lost += weight
        found.append(Finding(code, title, detail, repo.html_url,
                             REPO_MAX * (weight / available) / n_repos, repo.name, data))

    if not (repo.description or "").strip():
        add("no_description", "No description", "The repository description field is empty.", W_DESC)
    if repo.readme is None:
        add("no_readme", "No README", "There is no README file in the repository.",
            W_README + W_README_FULL)
    else:
        text = repo.readme.strip()
        if len(text) < THIN_README_CHARS:
            add("readme_thin", "README is a stub",
                f"README.md has only {len(text)} characters (under {THIN_README_CHARS}).",
                W_README_FULL, chars=len(text))
        elif not USAGE_RE.search(text) and "```" not in text:
            add("readme_no_usage", "README never says how to run it",
                "README.md has no install, setup or usage heading and no code block.", W_README_FULL)
    if not repo.license:
        add("no_license", "No license", "GitHub detected no license file, so nobody may legally reuse it.",
            W_LICENSE)
    if tests_expected and not any(TEST_PATH_RE.search(path) for path in repo.tree_paths or []):
        add("no_tests", "No tests",
            f"No tests folder or test file found among {len(repo.tree_paths or [])} files "
            f"(language: {repo.language}).", W_TESTS)
    if not repo.topics:
        add("no_topics", "No topics", "The repository has no topics, so people cannot discover it.", W_TOPICS)
    return (available - lost) / available, found


def _abandoned_findings(repos: List[RepoData], now: datetime) -> List[Finding]:
    found = []
    for repo in repos:
        if repo.is_empty or repo.archived or repo.pushed_at is None:
            continue
        days = _days_since(repo.pushed_at, now)
        if days > ABANDONED_AFTER_DAYS:
            found.append(Finding(
                "abandoned", "Looks abandoned",
                f"Last push was {repo.pushed_at.date().isoformat()} ({days} days ago) and the "
                "repository is not archived.", repo.html_url, W_NOT_ABANDONED / len(repos),
                repo.name, {"days": days}))
    return found


def _vague_commit_findings(repos: List[RepoData]) -> (List[Finding], float):
    """Return (findings, share of sampled commits with vague messages)."""
    total = sum(len(r.commits) for r in repos)
    vague_total = 0
    found: List[Finding] = []
    for repo in repos:
        vague = [c for c in repo.commits if _is_vague(c.message)]
        vague_total += len(vague)
        if len(repo.commits) >= 3 and len(vague) / len(repo.commits) >= 0.4 and total:
            examples = ", ".join(f'"{c.message}"' for c in vague[:3])
            found.append(Finding(
                "vague_commits", "Vague commit messages",
                f"{len(vague)} of {len(repo.commits)} sampled commits have messages like {examples}.",
                vague[0].url, W_COMMIT_MESSAGES * len(vague) / total, repo.name,
                {"count": len(vague), "example": vague[0].message}))
    return found, (vague_total / total if total else 0.0)


def _activity(snap: Snapshot, now: datetime):
    """Return (findings, points, months, latest) for the Activity part of the score."""
    dates = [r.pushed_at for r in snap.repos if r.pushed_at] + list(snap.push_event_dates)
    latest = max(dates) if dates else None
    days = _days_since(latest, now) if latest else None
    recent = (W_RECENT if days is not None and days <= 30 else 8 if days is not None and days <= 90
              else 4 if days is not None and days <= 180 else 0)
    cutoff = now - timedelta(days=365)
    months = Counter(c.date.strftime("%Y-%m") for r in snap.repos for c in r.commits
                     if c.date and c.date >= cutoff)
    consistency = {0: 0, 1: 2, 2: 4, 3: 6}.get(len(months), W_CONSISTENT)
    url = snap.profile.html_url
    found: List[Finding] = []
    if recent < W_RECENT:
        detail = (f"Latest public push was {latest.date().isoformat()} ({days} days ago)."
                  if latest else "No push dates were found for this profile.")
        found.append(Finding("inactive", "Not much recent activity", detail, url, W_RECENT - recent,
                             data={"days": days}))
    if consistency < W_CONSISTENT:
        found.append(Finding("thin_history", "Commit history is patchy",
                             f"Commits found in {len(months)} of the last 12 months "
                             "(sample of up to 30 recent commits per analysed repository).",
                             url, W_CONSISTENT - consistency, data={"months": len(months)}))
    timeline = [{"month": m, "commits": months[m]} for m in sorted(months)]
    return found, recent + consistency, timeline, latest


# ---- strengths and project picks ---------------------------------------------

def _strengths(snap: Snapshot, latest: Optional[datetime], now: datetime) -> List[Dict[str, str]]:
    p, out = snap.profile, []
    if snap.profile_readme is not None:
        out.append({"text": "You have a profile README.", "url": f"https://github.com/{p.login}/{p.login}"})
    solid = [r.name for r in snap.repos if not r.is_empty and r.description and r.license
             and r.readme and len(r.readme.strip()) >= THIN_README_CHARS]
    if solid:
        out.append({"text": f"{len(solid)} analysed repositories have a description, a license and a "
                            f"real README: {', '.join(solid[:3])}.", "url": p.html_url})
    tested = [r for r in snap.repos if r.tree_paths and any(TEST_PATH_RE.search(x) for x in r.tree_paths)]
    if tested:
        out.append({"text": f"Tests found in {', '.join(r.name for r in tested[:3])}.",
                    "url": tested[0].html_url})
    if latest and _days_since(latest, now) <= 30:
        out.append({"text": f"Recently active: last public push {latest.date().isoformat()}.",
                    "url": p.html_url})
    return out[:4]


def _pick_projects(repos: List[RepoData], findings: List[Finding], now: datetime) -> List[Dict[str, Any]]:
    """Choose the two repositories most worth finishing: real substance, recent, not yet polished."""
    scored = []
    for repo in repos:
        if repo.is_empty or repo.archived or repo.pushed_at is None:
            continue
        age = _days_since(repo.pushed_at, now)
        if age > 730 or (len(repo.commits) < 2 and not repo.readme):
            continue
        substance = min(len(repo.commits), 30) / 30 * 4 + (1 if repo.stars else 0) + min(repo.size_kb, 2000) / 2000 * 2
        recency = 3 if age <= 90 else 2 if age <= 180 else 1 if age <= 365 else 0
        scored.append((substance + recency, repo, age))
    scored.sort(key=lambda t: -t[0])
    picks = []
    for _, repo, age in scored[:2]:
        todo = [f.title for f in sorted((f for f in findings if f.repo == repo.name), key=lambda f: -f.impact)]
        picks.append({
            "repo": repo.name, "url": repo.html_url, "todo": todo,
            "why": (f"{len(repo.commits)} of your commits sampled, last push {repo.pushed_at.date().isoformat()} "
                    f"({age} days ago), repository size {repo.size_kb} KB. "
                    + (f"Still missing: {', '.join(todo).lower()}." if todo else "Nothing major is missing."))})
    return picks


# ---- entry point ----------------------------------------------------------------

def analyze(snap: Snapshot, now: datetime) -> Analysis:
    """Score a snapshot, or return a starter-mode analysis when there is too little public work."""
    profile_f = profile_findings(snap)
    if snap.own_repo_count < MIN_OWN_REPOS_TO_SCORE:
        return Analysis(mode="starter", findings=profile_f)

    repos, n = snap.repos, len(snap.repos)
    findings = list(profile_f)
    ratios = []
    for repo in repos:
        ratio, repo_f = _repo_findings(repo, n)
        ratios.append(ratio)
        findings += repo_f
    abandoned = _abandoned_findings(repos, now)
    vague, vague_share = _vague_commit_findings(repos)
    activity_f, activity_pts, months, latest = _activity(snap, now)
    findings += abandoned + vague + activity_f

    profile_pts = PROFILE_MAX - sum(f.impact for f in profile_f)
    repo_pts = REPO_MAX * sum(ratios) / n
    finish_pts = (W_NOT_ABANDONED * (1 - len(abandoned) / n) + W_COMMIT_MESSAGES * (1 - vague_share))
    breakdown = [
        {"name": "Profile", "earned": round(profile_pts, 1), "max": PROFILE_MAX},
        {"name": "Repository quality", "earned": round(repo_pts, 1), "max": REPO_MAX},
        {"name": "Activity", "earned": round(activity_pts, 1), "max": ACTIVITY_MAX},
        {"name": "Finishing what you start", "earned": round(finish_pts, 1), "max": FINISH_MAX},
    ]
    score = round(profile_pts + repo_pts + activity_pts + finish_pts)
    letter, label = grade_for(score)
    return Analysis(
        mode="scored", score=score, grade=letter, grade_label=label, breakdown=breakdown,
        findings=sorted(findings, key=lambda f: -f.impact),
        strengths=_strengths(snap, latest, now), picks=_pick_projects(repos, findings, now),
        activity_months=months, latest_activity=latest)
