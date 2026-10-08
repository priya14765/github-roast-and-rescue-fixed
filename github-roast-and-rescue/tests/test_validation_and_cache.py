import unittest

from app.cache import TTLCache
from app.config import load_settings
from app.ratelimit import RateLimiter
from app.validation import ValidationError, clean_username


class UsernameValidationTests(unittest.TestCase):
    def test_accepts_normal_names(self):
        for name in ["octocat", "a", "user-name", "A1b2", "x" * 39]:
            self.assertEqual(clean_username(name), name)

    def test_strips_at_sign_whitespace_and_profile_urls(self):
        self.assertEqual(clean_username("  @octocat "), "octocat")
        self.assertEqual(clean_username("https://github.com/octocat"), "octocat")
        self.assertEqual(clean_username("https://github.com/octocat/Hello-World?tab=x"), "octocat")

    def test_rejects_bad_names(self):
        bad = ["", "   ", "-start", "end-", "dou--ble", "under_score", "has space", "x" * 40,
               "name;rm -rf", "../etc/passwd", "<script>", None, 42]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    clean_username(value)

    def test_sample_names_allowed(self):
        self.assertEqual(clean_username("sample_messy"), "sample_messy")
        with self.assertRaises(ValidationError):
            clean_username("sample_other")


class CacheTests(unittest.TestCase):
    def test_hit_miss_and_expiry(self):
        now = [0.0]
        cache = TTLCache(ttl=10, clock=lambda: now[0])
        self.assertEqual(cache.get("k"), (False, None))
        cache.set("k", None)                       # None is a legitimate cached value
        self.assertEqual(cache.get("k"), (True, None))
        now[0] = 11
        self.assertEqual(cache.get("k"), (False, None))

    def test_get_or_set_computes_once(self):
        cache, calls = TTLCache(ttl=60), []
        for _ in range(3):
            cache.get_or_set("k", lambda: calls.append(1) or "value")
        self.assertEqual(len(calls), 1)

    def test_errors_are_not_cached(self):
        cache = TTLCache(ttl=60)
        with self.assertRaises(RuntimeError):
            cache.get_or_set("k", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertEqual(cache.get("k"), (False, None))

    def test_evicts_least_recently_used(self):
        cache = TTLCache(ttl=60, max_items=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")
        cache.set("c", 3)
        self.assertTrue(cache.get("a")[0])
        self.assertFalse(cache.get("b")[0])


class RateLimiterAndConfigTests(unittest.TestCase):
    def test_limiter_blocks_then_recovers(self):
        now = [0.0]
        limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: now[0])
        self.assertTrue(limiter.allow("ip"))
        self.assertTrue(limiter.allow("ip"))
        self.assertFalse(limiter.allow("ip"))
        self.assertTrue(limiter.allow("other"))
        now[0] = 61
        self.assertTrue(limiter.allow("ip"))

    def test_settings_come_from_environment_with_safe_defaults(self):
        settings = load_settings({"GEMINI_API_KEY": "k", "MAX_REPOS": "3", "CACHE_TTL_SECONDS": "oops"})
        self.assertEqual(settings.gemini_api_key, "k")
        self.assertEqual(settings.max_repos, 3)
        self.assertEqual(settings.cache_ttl_seconds, 3600)       # invalid value falls back
        self.assertIsNone(settings.github_token)
        self.assertEqual(load_settings({"MAX_REPOS": "999"}).max_repos, 12)   # clamped


if __name__ == "__main__":
    unittest.main()
