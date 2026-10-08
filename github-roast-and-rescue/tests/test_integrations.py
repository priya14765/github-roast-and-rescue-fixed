import base64
import json
import unittest

from app.cache import TTLCache
from app.gemini import build_facts, polish
from app.github_client import GitHubClient, GitHubError, NotAUser, RateLimited, UserNotFound

from .helpers import NOW, FakeResponse, FakeSession


def b64(text):
    return base64.b64encode(text.encode()).decode()


def github_routes():
    """A tiny GitHub: one user with two repositories (one of them empty)."""
    repo = {"name": "demo", "html_url": "https://github.com/dev/demo", "description": None, "language": "Python",
            "stargazers_count": 1, "size": 10, "pushed_at": "2026-10-01T10:00:00Z", "license": None,
            "topics": [], "archived": False, "fork": False, "default_branch": "main"}
    empty = dict(repo, name="blank", html_url="https://github.com/dev/blank", size=0)
    fork = dict(repo, name="forked", fork=True)
    return {
        "/users/dev": FakeResponse(200, {"login": "dev", "type": "User", "html_url": "https://github.com/dev",
                                         "public_repos": 3, "followers": 2, "bio": None,
                                         "created_at": "2024-01-01T00:00:00Z"}),
        "/users/dev/repos": FakeResponse(200, [repo, empty, fork]),
        "/users/dev/events/public": FakeResponse(200, [{"type": "PushEvent", "created_at": "2026-10-02T10:00:00Z"},
                                                       {"type": "WatchEvent", "created_at": "2026-10-03T10:00:00Z"}]),
        "/repos/dev/demo/git/trees/main": FakeResponse(200, {"tree": [{"path": "main.py"}], "truncated": False}),
        "/repos/dev/blank/git/trees/main": FakeResponse(409, None),
        "/repos/dev/demo/readme": FakeResponse(200, {"content": b64("# demo")}),
        "/repos/dev/demo/commits": FakeResponse(200, [{"sha": "abc", "html_url": "https://github.com/dev/demo/commit/abc",
                                                       "commit": {"message": "fix\n\nlong body",
                                                                  "author": {"date": "2026-09-30T10:00:00Z"}}}]),
        "/users/octo": FakeResponse(200, {"login": "octo", "type": "Organization", "html_url": "https://github.com/octo"}),
    }


class GitHubClientTests(unittest.TestCase):
    def make(self, routes=None, token=None):
        session = FakeSession(routes or github_routes())
        return GitHubClient(token, TTLCache(3600), session=session), session

    def test_builds_snapshot_from_api_data(self):
        client, _ = self.make()
        snap = client.fetch_snapshot("dev", max_repos=5)
        self.assertEqual(snap.profile.login, "dev")
        self.assertEqual(snap.own_repo_count, 2)
        self.assertEqual(snap.fork_count, 1)
        self.assertEqual([r.name for r in snap.repos], ["demo", "blank"])
        demo, blank = snap.repos
        self.assertEqual(demo.readme, "# demo")
        self.assertEqual(demo.commits[0].message, "fix")             # first line only
        self.assertEqual(demo.tree_paths, ["main.py"])
        self.assertTrue(blank.is_empty)
        self.assertIsNone(snap.profile_readme)                       # dev/dev has no README
        self.assertEqual(len(snap.push_event_dates), 1)              # only PushEvents count
        self.assertFalse(snap.pinned_known)                          # no token, so pinned repos unknown

    def test_repeated_requests_are_served_from_cache(self):
        client, session = self.make()
        client.fetch_snapshot("dev")
        calls_after_first = len(session.calls)
        client.fetch_snapshot("dev")
        self.assertEqual(len(session.calls), calls_after_first)

    def test_unknown_user_and_organisation(self):
        client, _ = self.make()
        with self.assertRaises(UserNotFound):
            client.fetch_snapshot("nobody")
        with self.assertRaises(NotAUser):
            client.fetch_snapshot("octo")

    def test_rate_limit_is_reported_with_reset_time(self):
        limited = FakeResponse(403, {"message": "rate limit exceeded"},
                               {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1790000000"})
        client, _ = self.make({"/users/dev": limited})
        with self.assertRaises(RateLimited) as caught:
            client.fetch_snapshot("dev")
        self.assertEqual(caught.exception.reset_at, 1790000000)

    def test_other_http_errors_become_github_error_and_are_not_cached(self):
        client, session = self.make({"/users/dev": FakeResponse(500, None)})
        for _ in range(2):
            with self.assertRaises(GitHubError):
                client.fetch_snapshot("dev")
        self.assertEqual(len(session.calls), 2)

    def test_token_is_sent_only_as_a_header(self):
        client, _ = self.make(token="secret-token")
        self.assertEqual(client._headers()["Authorization"], "Bearer secret-token")
        self.assertNotIn("Authorization", self.make()[0]._headers())


class GeminiTests(unittest.TestCase):
    FACTS = build_facts("draft roast", "# Hi\n- [demo](https://github.com/dev/demo): thing",
                        [{"repo": "demo", "excerpt": "A tool that parses logs."},
                         {"repo": "blank", "excerpt": ""}])

    class Session:
        def __init__(self, response):
            self.response, self.sent = response, None

        def post(self, url, **kwargs):
            self.sent = (url, kwargs)
            return self.response

    @staticmethod
    def reply(payload):
        return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]})

    def good(self, **overrides):
        payload = {"roast": "Your repos are shy but promising. Give them descriptions.",
                   "readme": "# Hi\nI build things.\n- [demo](https://github.com/dev/demo): parses logs for you",
                   "descriptions": {"demo": "Parses logs.", "blank": "invented", "ghost": "nope"}}
        payload.update(overrides)
        return payload

    def test_no_api_key_means_no_call(self):
        session = self.Session(self.reply(self.good()))
        self.assertIsNone(polish(None, "m", self.FACTS, session))
        self.assertIsNone(session.sent)

    def test_valid_answer_is_accepted_and_ungrounded_descriptions_dropped(self):
        session = self.Session(self.reply(self.good()))
        result = polish("key", "gemini-test", self.FACTS, session)
        self.assertEqual(result["descriptions"], {"demo": "Parses logs."})   # blank has no excerpt, ghost unknown
        url, kwargs = session.sent
        self.assertIn("gemini-test:generateContent", url)
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "key")
        self.assertNotIn("key", url)                                          # key never goes in the URL

    def test_answer_that_drops_project_links_is_rejected(self):
        session = self.Session(self.reply(self.good(readme="# Hi\nNo links here, but long enough to pass the length check.")))
        self.assertIsNone(polish("key", "m", self.FACTS, session))

    def test_malformed_or_failed_answers_fall_back_to_none(self):
        bad_json = FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]})
        for response in [bad_json, FakeResponse(500, None), FakeResponse(200, {}), self.reply(["list"]),
                         self.reply(self.good(roast="x" * 5000))]:
            self.assertIsNone(polish("key", "m", self.FACTS, self.Session(response)))


if __name__ == "__main__":
    unittest.main()
