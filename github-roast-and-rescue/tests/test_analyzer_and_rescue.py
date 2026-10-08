import unittest

from app.analyzer import analyze, grade_for
from app.rescue import (build_description_suggestions, build_fixes, build_profile_readme,
                        build_starter_plan, readme_excerpt)
from app.roast import build_roast
from app.samples import build_sample

from .helpers import NOW


class ScoringTests(unittest.TestCase):
    def test_strong_profile_scores_high_and_messy_scores_low(self):
        strong = analyze(build_sample("sample_strong", NOW), NOW)
        messy = analyze(build_sample("sample_messy", NOW), NOW)
        self.assertEqual(strong.mode, "scored")
        self.assertGreaterEqual(strong.score, 85)
        self.assertLessEqual(messy.score, 40)
        self.assertGreater(strong.score, messy.score)

    def test_score_is_deterministic_and_within_range(self):
        first = analyze(build_sample("sample_messy", NOW), NOW)
        second = analyze(build_sample("sample_messy", NOW), NOW)
        self.assertEqual(first.score, second.score)
        self.assertTrue(0 <= first.score <= 100)

    def test_breakdown_adds_up_to_score(self):
        result = analyze(build_sample("sample_messy", NOW), NOW)
        self.assertAlmostEqual(sum(part["earned"] for part in result.breakdown), result.score, delta=1.0)
        self.assertEqual(sum(part["max"] for part in result.breakdown), 100)

    def test_nearly_empty_profile_gets_starter_mode_without_a_score(self):
        result = analyze(build_sample("sample_empty", NOW), NOW)
        self.assertEqual(result.mode, "starter")
        self.assertIsNone(result.score)

    def test_grade_bands(self):
        self.assertEqual(grade_for(90)[0], "A")
        self.assertEqual(grade_for(70)[0], "B")
        self.assertEqual(grade_for(10)[0], "E")


class FindingEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = build_sample("sample_messy", NOW)
        self.result = analyze(self.snapshot, NOW)

    def codes(self, repo=None):
        return {f.code for f in self.result.findings if f.repo == repo}

    def test_detects_specific_problems_on_the_right_repository(self):
        self.assertIn("no_description", self.codes("test"))
        self.assertIn("no_license", self.codes("test"))
        self.assertIn("no_tests", self.codes("test"))
        self.assertIn("readme_thin", self.codes("untitled-project"))
        self.assertIn("empty_repo", self.codes("new-repo"))
        self.assertIn("abandoned", self.codes("myapp"))
        self.assertIn("vague_commits", self.codes("myapp"))
        self.assertIn("no_readme", self.codes("test"))

    def test_no_false_alarms_on_strong_profile(self):
        strong = analyze(build_sample("sample_strong", NOW), NOW)
        self.assertEqual([f.code for f in strong.findings], [])

    def test_every_finding_has_a_github_link_and_exact_detail(self):
        for finding in self.result.findings:
            with self.subTest(code=finding.code, repo=finding.repo):
                self.assertTrue(finding.url.startswith("https://github.com/sample_messy"))
                self.assertGreater(len(finding.detail), 10)
                self.assertGreater(finding.impact, 0)

    def test_unknown_file_list_is_not_reported_as_missing_tests(self):
        snap = build_sample("sample_messy", NOW)
        snap.repos[0].tree_paths = None                     # file list unknown, so we must not guess
        codes = {f.code for f in analyze(snap, NOW).findings if f.repo == "test"}
        self.assertNotIn("no_tests", codes)


class RescueTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = build_sample("sample_messy", NOW)
        self.analysis = analyze(self.snapshot, NOW)

    def test_five_fixes_ranked_by_points_with_evidence(self):
        fixes = build_fixes(self.analysis)
        self.assertEqual(len(fixes), 5)
        self.assertEqual([f["rank"] for f in fixes], [1, 2, 3, 4, 5])
        points = [f["points"] for f in fixes]
        self.assertEqual(points, sorted(points, reverse=True))
        for fix in fixes:
            self.assertTrue(fix["evidence"])
            for item in fix["evidence"]:
                self.assertTrue(item["url"].startswith("https://github.com/"))
                self.assertTrue(item["detail"])

    def test_two_projects_to_finish_with_reasons(self):
        picks = self.analysis.picks
        self.assertEqual(len(picks), 2)
        self.assertNotIn("new-repo", [p["repo"] for p in picks])      # empty repos are never picked
        for pick in picks:
            self.assertIn("last push", pick["why"])
            self.assertTrue(pick["url"].startswith("https://github.com/"))

    def test_descriptions_are_grounded_or_marked_todo(self):
        snap = build_sample("sample_strong", NOW)
        snap.repos[0].description = None
        suggestions = build_description_suggestions(snap.repos)
        self.assertEqual(len(suggestions), 1)
        self.assertTrue(suggestions[0]["grounded"])
        self.assertIn("small tool", suggestions[0]["suggested"])
        messy = build_description_suggestions(self.snapshot.repos)
        todo = [s for s in messy if not s["grounded"]]
        self.assertTrue(todo)
        self.assertTrue(all(s["suggested"].startswith("TODO") for s in todo))

    def test_readme_excerpt_skips_headings_badges_and_code(self):
        text = "# Title\n![badge](x.svg)\n\nReal sentence here.\n```\ncode\n```\n"
        self.assertEqual(readme_excerpt(text), "Real sentence here.")
        self.assertEqual(readme_excerpt(None), "")

    def test_profile_readme_uses_only_known_facts(self):
        readme = build_profile_readme(self.snapshot, self.analysis, build_description_suggestions(self.snapshot.repos))
        self.assertIn("# Hi, I'm sample_messy", readme)
        self.assertIn("TODO", readme)                                   # unknown facts stay TODO
        self.assertIn("https://github.com/sample_messy/myapp", readme)
        self.assertNotIn("Rust", readme)                                # no invented skills

    def test_starter_plan_cites_evidence_for_every_step(self):
        snap = build_sample("sample_empty", NOW)
        plan = build_starter_plan(snap, analyze(snap, NOW))
        self.assertGreaterEqual(len(plan["steps"]), 3)
        for step in plan["steps"]:
            self.assertTrue(step["evidence"][0]["detail"])
            self.assertTrue(step["evidence"][0]["url"].startswith("https://github.com/sample_empty"))


class RoastTests(unittest.TestCase):
    def test_roast_mentions_real_repositories_and_is_short(self):
        roast = build_roast(analyze(build_sample("sample_messy", NOW), NOW))
        self.assertTrue(any(name in roast for name in ["new-repo", "test", "myapp", "untitled-project"]))
        self.assertLess(len(roast), 900)

    def test_roast_is_kind_to_starter_profiles(self):
        roast = build_roast(analyze(build_sample("sample_empty", NOW), NOW))
        self.assertIn("good news", roast)


if __name__ == "__main__":
    unittest.main()
