"""Builds the short roast from real findings. It targets the work, never the person."""
from __future__ import annotations

from typing import Dict, List

from .analyzer import Analysis, Finding

OPENERS = {
    "A": "This is a genuinely good profile, so the roast has to work hard for its living.",
    "B": "Solid foundations here, with a few loose floorboards.",
    "C": "There is real work here; the packaging has not caught up with it yet.",
    "D": "Plenty of ideas in here. Visitors are going to need a map.",
    "E": "A lot of this profile is still under construction, and the sign says so.",
}

LINES = {
    "no_description": "{repo} greets visitors with an empty description box, like a shop with no sign.",
    "no_readme": "{repo} has no README, so the front door is a blank wall.",
    "readme_thin": "{repo}'s README is {chars} characters long; a fortune cookie says more.",
    "readme_no_usage": "{repo}'s README never says how to run the thing, which makes it a very quiet instruction manual.",
    "no_license": "{repo} has no license, which technically means nobody may reuse it. Exclusive, at least.",
    "no_tests": "{repo} has no tests, so 'it works on my machine' is the whole quality plan.",
    "no_topics": "{repo} has no topics, so the only way to find it is to already know it exists.",
    "empty_repo": "{repo} is an empty repository: ambitious name, minimal contents.",
    "abandoned": "{repo} was last touched {days} days ago. Less a project, more a time capsule.",
    "vague_commits": "{repo} has commit messages like \"{example}\"; future you will have questions.",
    "inactive": "The latest push I can see is {days} days ago, so the profile is currently on a long coffee break.",
    "thin_history": "Commits show up in only {months} of the last 12 months, so the history reads like a few bursts.",
    "no_profile_readme": "The profile page has no README, so visitors get a list of repos and no story.",
    "no_bio": "The bio is blank, so a visitor has to guess what you do.",
    "no_contact": "There is no website, location or company, so the profile gives no way to reach you.",
}


def _line(finding: Finding) -> str:
    values: Dict[str, object] = {"repo": finding.repo or "", "days": "many", "months": 0, "chars": 0, "example": ""}
    values.update(finding.data)
    return LINES[finding.code].format(**values)


def build_roast(analysis: Analysis) -> str:
    """Two or three evidence-based jabs, then something kind. Starter profiles get a gentle note."""
    if analysis.mode == "starter":
        return ("There is barely any public work here to roast, and that is good news: you get to set it "
                "up properly from day one. The starter plan below goes step by step.")
    chosen: List[str] = []
    seen_codes = set()
    for finding in analysis.findings:
        if finding.code in seen_codes or finding.code not in LINES:
            continue
        seen_codes.add(finding.code)
        chosen.append(_line(finding))
        if len(chosen) == 3:
            break
    closer = (f"On the bright side: {analysis.strengths[0]['text'][0].lower()}{analysis.strengths[0]['text'][1:]}"
              if analysis.strengths else "All of this is fixable in an afternoon, and the Rescue plan below goes in order.")
    return " ".join([OPENERS.get(analysis.grade or "E", OPENERS["E"]), *chosen, closer])
