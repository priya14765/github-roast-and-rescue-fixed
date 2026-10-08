"""Assembles the full JSON-ready report: score, roast and rescue plan."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Dict, Optional

from . import gemini as gemini_module
from .analyzer import analyze
from .models import Snapshot
from .rescue import (build_description_suggestions, build_fixes, build_profile_readme, build_starter_plan)
from .roast import build_roast


def _repository_health(snap: Snapshot, analysis: Any) -> list[Dict[str, Any]]:
    """Build per-repository summaries using only checks already performed."""
    findings_by_repo: Dict[str, list[Any]] = {}
    for finding in analysis.findings:
        if finding.repo:
            findings_by_repo.setdefault(finding.repo, []).append(finding)

    health = []
    for repo in snap.repos:
        issues = findings_by_repo.get(repo.name, [])
        if analysis.mode == "starter":
            status = "Not scored"
        elif issues:
            status = "Needs attention"
        else:
            status = "No issues detected"
        health.append({
            "name": repo.name,
            "url": repo.html_url,
            "status": status,
            "language": repo.language,
            "stars": repo.stars,
            "last_push": repo.pushed_at.date().isoformat() if repo.pushed_at else None,
            "issues": [
                {"title": finding.title, "detail": finding.detail}
                for finding in sorted(issues, key=lambda item: -item.impact)
            ],
        })
    return health


def _seven_day_plan(fixes: list[Dict[str, Any]]) -> Dict[str, Any]:
    """Schedule ranked fixes first, then reserve time for review and a fresh check."""
    if not fixes:
        return {
            "days": [],
            "message": "No priority fixes were found by the current checks. Re-run the review after your next meaningful profile update.",
        }

    days = [
        {
            "day": index,
            "title": fix["title"],
            "how": fix.get("how", ""),
            "evidence": fix.get("evidence", []),
        }
        for index, fix in enumerate(fixes[:5], start=1)
    ]
    for index in range(len(days) + 1, 6):
        days.append({
            "day": index,
            "title": "Buffer day",
            "how": "Use this time to finish a priority fix or take a break before the final review.",
            "evidence": [],
        })
    days.extend([
        {
            "day": 6,
            "title": "Review your changes",
            "how": "Check off the fixes you completed and confirm the linked profile or repository pages show the updates.",
            "evidence": [],
        },
        {
            "day": 7,
            "title": "Run your profile check again",
            "how": "Refresh Roast and Rescue to see which findings changed. The score is based on the public data available at that time.",
            "evidence": [],
        },
    ])
    return {
        "days": days,
        "message": "Start with the highest-priority fix. Use the review days to fit the work around your schedule.",
    }


def _portfolio_snapshot(snap: Snapshot) -> Dict[str, Any]:
    """Summarize stars and languages for the repositories actually analysed."""
    languages = Counter(
        repo.language.strip()
        for repo in snap.repos
        if repo.language and repo.language.strip()
    )
    top_repositories = sorted(
        (repo for repo in snap.repos if repo.stars > 0),
        key=lambda repo: (-repo.stars, repo.name.casefold()),
    )[:3]
    return {
        "analyzed_repos": len(snap.repos),
        "total_stars": sum(repo.stars for repo in snap.repos),
        "languages": [
            {"name": name, "repositories": count}
            for name, count in sorted(languages.items(), key=lambda item: (-item[1], item[0].casefold()))
        ],
        "top_repositories": [
            {"name": repo.name, "url": repo.html_url, "stars": repo.stars}
            for repo in top_repositories
        ],
    }


def build_report(snap: Snapshot, now: datetime, gemini_key: Optional[str] = None,
                 gemini_model: str = "gemini-2.5-flash", session: Any = None) -> Dict[str, Any]:
    """Run the analysis and return a report dictionary. Gemini polish is applied when available."""
    analysis = analyze(snap, now)
    p = snap.profile
    roast = build_roast(analysis)
    notes = []
    if snap.sample:
        notes.append("This is built-in SAMPLE data, not a real GitHub account. Links are illustrative.")
    if not snap.pinned_known:
        notes.append("Pinned repositories could not be read (GitHub needs a token for that), so the most "
                     "recently pushed repositories were analysed instead.")
    if snap.repo_list_truncated:
        notes.append("This account has more than 100 repositories; only the 100 most recently pushed were considered.")

    if analysis.mode == "starter":
        plan = build_starter_plan(snap, analysis)
        rescue = {"mode": "starter", "fixes": plan["steps"], "readme": plan["readme"],
                  "repo_descriptions": [], "finish_first": []}
        facts = None
        notes.append(f"Only {snap.own_repo_count} public non-fork repositories found, which is too little to "
                     "score fairly. Private repositories cannot be seen through the public API.")
    else:
        suggestions = build_description_suggestions(snap.repos)
        readme = build_profile_readme(snap, analysis, suggestions)
        rescue = {"mode": "scored", "fixes": build_fixes(analysis), "readme": readme,
                  "repo_descriptions": suggestions, "finish_first": analysis.picks}
        facts = gemini_module.build_facts(roast, readme, suggestions)

    ai = "template"
    polished = gemini_module.polish(gemini_key, gemini_model, facts, session) if facts else None
    if polished:
        ai = "gemini"
        roast, rescue["readme"] = polished["roast"], polished["readme"]
        for item in rescue["repo_descriptions"]:
            if item["repo"] in polished["descriptions"]:
                item["suggested"] = polished["descriptions"][item["repo"]]
    for item in rescue["repo_descriptions"]:
        item.pop("excerpt", None)          # internal-only field, not part of the public response

    return {
        "username": p.login,
        "profile": {"name": p.name, "bio": p.bio, "url": p.html_url, "avatar_url": p.avatar_url,
                    "public_repos": p.public_repos, "followers": p.followers},
        "mode": analysis.mode,
        "score": analysis.score, "grade": analysis.grade, "grade_label": analysis.grade_label,
        "breakdown": analysis.breakdown,
        "roast": roast,
        "rescue": rescue,
        "strengths": analysis.strengths,
        "activity_months": analysis.activity_months,
        "portfolio": _portfolio_snapshot(snap),
        "repository_health": _repository_health(snap, analysis),
        "action_plan": _seven_day_plan(rescue["fixes"]),
        "meta": {"generated_at": now.isoformat(), "repos_analyzed": len(snap.repos), "ai": ai,
                 "sample": snap.sample, "notes": notes},
    }
