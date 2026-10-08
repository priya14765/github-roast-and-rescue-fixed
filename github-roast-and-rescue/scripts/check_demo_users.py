"""Check which real GitHub usernames make good demos (strong, messy, almost empty).

Run from a machine that can reach api.github.com:
    python scripts/check_demo_users.py someuser otheruser
Set GITHUB_TOKEN first if you check more than a couple of names (the anonymous limit is 60 requests/hour).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import load_settings          # noqa: E402
from app.github_client import GitHubError      # noqa: E402
from app.service import ReportService          # noqa: E402


def main(names):
    service = ReportService(load_settings())
    for name in names:
        try:
            report = service.analyze(name)
        except (GitHubError, ValueError) as exc:
            print(f"{name:20} ERROR: {exc}")
            continue
        label = "almost empty (starter plan)" if report["mode"] == "starter" else f"score {report['score']} ({report['grade']})"
        print(f"{name:20} {label}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
