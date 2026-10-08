import unittest
from unittest import mock

from app import service as service_module
from app.config import Settings
from app.github_client import GitHubError, NotAUser, RateLimited, UserNotFound
from app.main import create_app
from app.service import ReportService
from app.validation import ValidationError, clean_username


class RaisingService:
    """Fake service that raises whatever it is told to."""

    def __init__(self, error=None):
        self.error = error

    def analyze(self, username):
        clean_username(username)
        if self.error:
            raise self.error
        return {"username": username}


class WebAppTests(unittest.TestCase):
    def client(self, service=None):
        return create_app(service or ReportService(Settings())).test_client()

    def test_home_page_is_accessible_html(self):
        page = self.client().get("/").get_data(as_text=True)
        self.assertIn('<html lang="en">', page)
        self.assertIn('<label for="username">', page)
        self.assertIn('class="skip-link"', page)
        self.assertIn('id="copy"', page)
        self.assertIn('id="copy-summary"', page)
        self.assertIn('id="print-report"', page)
        self.assertIn('id="score-impact-planner"', page)
        self.assertIn('id="projected-score"', page)
        self.assertIn('id="fix-progress"', page)
        self.assertIn('id="reset-fix-progress"', page)
        self.assertIn('class="feature-strip"', page)
        self.assertIn('id="portfolio-heading">Portfolio snapshot</h2>', page)
        self.assertIn('id="health-heading">Repository health</h2>', page)
        self.assertIn('id="plan-heading">Your 7-day action plan</h2>', page)
        self.assertIn('data-sample="sample_messy"', page)
        self.assertIn('data-sample="sample_strong"', page)
        self.assertIn('data-sample="sample_empty"', page)
        for heading in ["Score", "Roast", "Rescue"]:
            self.assertIn(f">{heading}</h2>", page)

    def test_security_headers_and_health(self):
        response = self.client().get("/healthz")
        self.assertEqual(response.get_json(), {"status": "ok"})
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_static_assets_are_served(self):
        client = self.client()
        for path in ["/static/app.js", "/static/style.css"]:
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_report_actions_and_print_styles_are_available(self):
        client = self.client()
        script_response = client.get("/static/app.js")
        stylesheet_response = client.get("/static/style.css")
        script = script_response.get_data(as_text=True)
        stylesheet = stylesheet_response.get_data(as_text=True)
        script_response.close()
        stylesheet_response.close()
        self.assertIn("function reportSummary(data)", script)
        self.assertIn('window.print()', script)
        self.assertIn("@media print", stylesheet)
        self.assertIn("Generated from public GitHub data", script)
        self.assertIn("function updateScoreProjection()", script)
        self.assertIn("rough estimate, not guaranteed", script)
        self.assertIn("function saveFixProgress()", script)
        self.assertIn("function resetFixProgress()", script)
        self.assertIn("Fix progress:", script)

    def test_invalid_username_is_rejected_with_400(self):
        for value in ["", "bad name", "-x", "a" * 50]:
            with self.subTest(value=value):
                response = self.client().get("/api/analyze", query_string={"username": value})
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.get_json())

    def test_sample_profiles_work_offline_and_have_all_sections(self):
        client = self.client()
        for name, mode in [("sample_strong", "scored"), ("sample_messy", "scored"), ("sample_empty", "starter")]:
            with self.subTest(name=name):
                body = client.get("/api/analyze", query_string={"username": name}).get_json()
                self.assertEqual(body["mode"], mode)
                self.assertTrue(body["meta"]["sample"])
                self.assertTrue(body["roast"])
                self.assertTrue(body["rescue"]["readme"])
                self.assertEqual(body["portfolio"]["analyzed_repos"], body["meta"]["repos_analyzed"])
                self.assertEqual(len(body["repository_health"]), body["meta"]["repos_analyzed"])
                self.assertEqual(len(body["action_plan"]["days"]), 7 if body["rescue"]["fixes"] else 0)
                self.assertEqual([item["day"] for item in body["action_plan"]["days"]],
                                 list(range(1, 8)) if body["rescue"]["fixes"] else [])
                if name == "sample_strong":
                    self.assertEqual(body["rescue"]["fixes"], [])      # nothing to fix is a valid answer
                    self.assertEqual(body["action_plan"]["days"], [])
                    self.assertEqual(body["portfolio"]["total_stars"], 12)
                    self.assertEqual(body["portfolio"]["languages"], [{"name": "Python", "repositories": 4}])
                    self.assertEqual(len(body["portfolio"]["top_repositories"]), 3)
                    self.assertEqual(body["portfolio"]["top_repositories"][0]["stars"], 3)
                    self.assertEqual(body["portfolio"]["top_repositories"][0]["name"], "budget-tracker")
                elif name == "sample_empty":
                    self.assertEqual(body["repository_health"], [])
                    self.assertEqual(body["portfolio"]["total_stars"], 0)
                    self.assertEqual(body["portfolio"]["languages"], [])
                    self.assertEqual(body["portfolio"]["top_repositories"], [])
                else:
                    self.assertEqual(body["portfolio"]["languages"], [
                        {"name": "Python", "repositories": 2},
                        {"name": "Java", "repositories": 1},
                        {"name": "JavaScript", "repositories": 1},
                    ])
                    self.assertTrue(body["rescue"]["fixes"])
                    repos = {repo["name"]: repo for repo in body["repository_health"]}
                    self.assertEqual(repos["test"]["status"], "Needs attention")
                    self.assertTrue(repos["test"]["issues"])
                    self.assertEqual(body["action_plan"]["days"][0]["title"], body["rescue"]["fixes"][0]["title"])

    def test_error_mapping(self):
        cases = [(UserNotFound("x"), 404), (NotAUser("x"), 422), (RateLimited(None), 429), (GitHubError("down"), 502)]
        for error, status in cases:
            with self.subTest(error=type(error).__name__):
                response = self.client(RaisingService(error)).get("/api/analyze", query_string={"username": "dev"})
                self.assertEqual(response.status_code, status)

    def test_visitor_rate_limit(self):
        with mock.patch.dict("os.environ", {"RATE_LIMIT_PER_MINUTE": "2"}):
            client = self.client(RaisingService())
        statuses = [client.get("/api/analyze", query_string={"username": "dev"}).status_code for _ in range(3)]
        self.assertEqual(statuses, [200, 200, 429])

    def test_repeat_requests_hit_the_report_cache(self):
        service = ReportService(Settings())
        with mock.patch.object(service_module, "build_report", wraps=service_module.build_report) as spy:
            service.analyze("sample_strong")
            service.analyze("sample_strong")
        self.assertEqual(spy.call_count, 1)


if __name__ == "__main__":
    unittest.main()
