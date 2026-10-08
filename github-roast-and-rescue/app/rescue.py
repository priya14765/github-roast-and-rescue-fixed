"""Builds the Rescue plan: five ordered fixes, a new profile README, repo descriptions, starter plan.

Everything here is derived from fetched data. Where a fact is unknown the output says TODO
instead of inventing one.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .analyzer import Analysis, Finding
from .models import RepoData, Snapshot

# code -> (how to fix it). Titles are built in _fix_title so they can include counts.
HOW_TO = {
    "no_profile_readme": "Create a public repository named exactly after your username and add a README.md. "
                         "GitHub shows it at the top of your profile. Use the rewritten README below.",
    "no_bio": "Add one sentence to your bio: what you build and what you are learning.",
    "no_contact": "Add a website, location or company so people know how to reach you.",
    "no_readme": "Add README.md with four things: what it does, how to install it, how to run it, "
                 "and a screenshot or sample output.",
    "readme_thin": "Expand the README: what problem it solves, install steps, a usage example.",
    "readme_no_usage": "Add an 'Installation' and a 'Usage' heading with the exact commands to run it.",
    "no_description": "Fill in the repository description (the one-line text under the repo name). "
                      "Suggested wording is in 'Better repository descriptions' below.",
    "no_license": "Add a LICENSE file (MIT is a common default for portfolio projects; choosealicense.com explains the options).",
    "no_tests": "Add a tests folder with a few tests for the core logic and show the command to run them in the README.",
    "no_topics": "Add 3-5 topics (language, framework, what it is) in the repository settings.",
    "empty_repo": "Either push the code or delete the repository so it does not look unfinished.",
    "abandoned": "Archive the repository (Settings, Archive) or finish it. An archived repo reads as a decision, "
                 "an untouched one reads as a dropped project.",
    "vague_commits": "Write commit messages that say what changed and why, for example 'Add input validation to signup form'.",
    "inactive": "Make a small commit on a real project this week. A steady trickle beats one burst.",
    "thin_history": "Commit in smaller pieces, more often, so the history shows steady progress.",
}
PROFILE_CODES = {"no_profile_readme", "no_bio", "no_contact"}


def _plural(count: int, word: str) -> str:
    """'1 repository' / '3 repositories' / '2 projects'."""
    if count == 1:
        return f"{count} {word}"
    if word.endswith("y") and word[-2] not in "aeiou":
        return f"{count} {word[:-1]}ies"
    return f"{count} {word}s"


def _fix_title(code: str, count: int, example: Optional[Finding]) -> str:
    titles = {
        "no_profile_readme": "Create a profile README",
        "no_bio": "Write a bio",
        "no_contact": "Add contact details to your profile",
        "no_readme": f"Add a README to {_plural(count, 'repository')}",
        "readme_thin": f"Expand {_plural(count, 'stub README')}",
        "readme_no_usage": f"Explain how to run {_plural(count, 'project')}",
        "no_description": f"Add a description to {_plural(count, 'repository')}",
        "no_license": f"Add a license to {_plural(count, 'repository')}",
        "no_tests": f"Add tests to {_plural(count, 'repository')}",
        "no_topics": f"Add topics to {_plural(count, 'repository')}",
        "empty_repo": f"Fill or remove {_plural(count, 'empty repository')}",
        "abandoned": f"Finish or archive {_plural(count, 'abandoned project')}",
        "vague_commits": "Write meaningful commit messages",
        "inactive": "Commit something this week",
        "thin_history": "Commit more steadily",
    }
    return titles.get(code, example.title if example else code)


def build_fixes(analysis: Analysis, limit: int = 5) -> List[Dict[str, Any]]:
    """Group findings by problem, rank groups by points lost, return the top few with evidence."""
    groups: Dict[str, List[Finding]] = defaultdict(list)
    for finding in analysis.findings:
        groups[finding.code].append(finding)
    ranked = sorted(groups.items(), key=lambda kv: -sum(f.impact for f in kv[1]))[:limit]
    fixes = []
    for rank, (code, items) in enumerate(ranked, start=1):
        points = sum(f.impact for f in items)
        evidence = [{"label": f.repo or "Profile", "url": f.url, "detail": f.detail} for f in items[:5]]
        more = len(items) - len(evidence)
        fixes.append({
            "rank": rank,
            "title": _fix_title(code, len(items), items[0]),
            "how": HOW_TO.get(code, ""),
            "points": round(points, 1),
            "why": f"Costs about {points:.0f} of 100 points" + (f" (and {more} more not listed)." if more > 0 else "."),
            "evidence": evidence,
        })
    return fixes


# ---- repository descriptions ----------------------------------------------------

def readme_excerpt(readme: Optional[str], limit: int = 600) -> str:
    """First meaningful prose of a README: no headings, badges, images or code fences."""
    if not readme:
        return ""
    lines = []
    in_code = False
    for line in readme.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped or stripped.startswith(("#", "![", "[![", "<", "|", "---")):
            continue
        lines.append(stripped)
        if sum(len(x) for x in lines) >= limit:
            break
    return re.sub(r"\s+", " ", " ".join(lines))[:limit].strip()


def _clip(text: str, width: int = 110) -> str:
    text = text.strip()
    if len(text) <= width:
        return text
    cut = text[:width].rsplit(" ", 1)[0].rstrip(",;:-")
    return cut + "..."


def build_description_suggestions(repos: List[RepoData]) -> List[Dict[str, Any]]:
    """Suggest a description for each repository that has none. `grounded` is True when it
    comes from the repository's own README; otherwise it is a clearly marked TODO."""
    out = []
    for repo in repos:
        if (repo.description or "").strip() or repo.is_empty:
            continue
        excerpt = readme_excerpt(repo.readme)
        if excerpt:
            text, grounded = _clip(excerpt), True
        else:
            lang = repo.language or "project"
            text, grounded = f"TODO: one sentence on what {repo.name} does ({lang})", False
        out.append({"repo": repo.name, "url": repo.html_url, "current": None,
                    "suggested": text, "grounded": grounded, "excerpt": excerpt})
    return out


# ---- profile README ---------------------------------------------------------------

def _language_line(repos: List[RepoData]) -> str:
    counts = Counter(r.language for r in repos if r.language)
    return ", ".join(f"{lang} ({_plural(n, 'repo')})" for lang, n in counts.most_common(4))


def build_profile_readme(snap: Snapshot, analysis: Analysis, suggestions: List[Dict[str, Any]]) -> str:
    """Draft a profile README using only facts from the profile; unknowns become TODO comments."""
    p = snap.profile
    suggested = {s["repo"]: s["suggested"] for s in suggestions}
    lines = [f"# Hi, I'm {p.name or p.login}", ""]
    lines += [(p.bio or "").strip() or "<!-- TODO: one sentence on what you build and what you are learning -->", ""]
    languages = _language_line(snap.repos)
    if languages:
        lines += ["## What I work with", "", languages, ""]
    featured = [r for r in snap.repos if r.name in {pick["repo"] for pick in analysis.picks}] or snap.repos[:2]
    if featured:
        lines += ["## Projects", ""]
        for repo in featured:
            desc = (repo.description or "").strip() or suggested.get(repo.name, "<!-- TODO: describe this project -->")
            lines.append(f"- [{repo.name}]({repo.html_url}): {desc}")
        lines.append("")
    lines += ["## Get in touch", ""]
    if p.blog:
        lines.append(f"- Website: {p.blog}")
    if p.location:
        lines.append(f"- Based in {p.location}")
    lines.append("- <!-- TODO: add an email address or LinkedIn link -->")
    return "\n".join(lines) + "\n"


# ---- starter plan for private or nearly empty profiles ----------------------------

def build_starter_plan(snap: Snapshot, analysis: Analysis, now: Optional[datetime] = None) -> Dict[str, Any]:
    """A short, honest plan when there is not enough public work to score.

    Each step is included only when a fact about this profile justifies it, and cites that fact.
    """
    p = snap.profile
    own, forks = snap.own_repo_count, snap.fork_count
    codes = {f.code for f in analysis.findings}
    candidates: List[Dict[str, Any]] = []

    def step(title: str, how: str, detail: str, url: str, label: str = "Profile") -> None:
        candidates.append({"title": title, "how": how,
                           "evidence": [{"label": label, "url": url, "detail": detail}]})

    if "no_profile_readme" in codes:
        step("Create a profile README", HOW_TO["no_profile_readme"],
             f"No README found at {p.login}/{p.login}.", f"https://github.com/{p.login}/{p.login}")
    if "no_bio" in codes:
        step("Write a bio", HOW_TO["no_bio"], "The bio field is empty.", p.html_url)
    step("Publish one small project and finish it",
         "Pick something you can finish in a weekend. Give it a description, a README with run "
         "instructions, a license and one or two tests. One finished project beats five half-done ones.",
         f"{p.login} has {_plural(own, 'public repository')} of its own (not forks).",
         p.html_url + "?tab=repositories")
    if forks and own == 0:
        step("Add something you wrote yourself", "Forks show what you read, not what you build. "
             "Start a repository of your own and keep the forks as reference.",
             f"All {_plural(forks, 'public repository')} found are forks.", p.html_url + "?tab=repositories")
    if "no_contact" in codes:
        step("Add contact details", HOW_TO["no_contact"], "Website, location and company are all empty.", p.html_url)
    if not snap.push_event_dates:
        step("Commit in small steps, often", HOW_TO["thin_history"],
             "No public pushes appear in GitHub's recent public activity feed.", p.html_url)

    steps = [dict(item, rank=i) for i, item in enumerate(candidates[:5], start=1)]
    return {"steps": steps, "readme": build_profile_readme(snap, analysis, [])}
