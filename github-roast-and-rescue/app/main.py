"""Flask web app: one page plus a JSON API."""
from __future__ import annotations

import time
from typing import Any, Optional, Tuple

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import load_settings
from .github_client import GitHubError, NotAUser, RateLimited, UserNotFound
from .ratelimit import RateLimiter
from .service import ReportService
from .validation import ValidationError

CSP = ("default-src 'self'; img-src 'self' https://avatars.githubusercontent.com data:; "
       "style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


def _error(message: str, status: int) -> Tuple[Any, int]:
    return jsonify({"error": message}), status


def create_app(service: Optional[ReportService] = None) -> Flask:
    """Application factory. Tests pass in a fake service; production builds one from the environment."""
    settings = load_settings()
    service = service or ReportService(settings)
    limiter = RateLimiter(settings.rate_limit_per_minute)

    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)          # Cloud Run adds the real client IP

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.get("/api/analyze")
    def analyze():
        if not limiter.allow(request.remote_addr or "unknown"):
            return _error("Too many requests. Please wait a minute and try again.", 429)
        try:
            return jsonify(service.analyze(request.args.get("username", "")))
        except ValidationError as exc:
            return _error(str(exc), 400)
        except UserNotFound:
            return _error("No public GitHub profile with that username. Check the spelling.", 404)
        except NotAUser:
            return _error("That is an organisation account. Enter a personal username.", 422)
        except RateLimited as exc:
            wait = ""
            if exc.reset_at:
                wait = f" Try again in about {max(int((exc.reset_at - time.time()) // 60) + 1, 1)} minutes."
            return _error("GitHub's rate limit was reached." + wait, 429)
        except GitHubError as exc:
            return _error(str(exc), 502)

    return app


# Vercel (and other platforms) look for a top-level "app" Flask instance.
app = create_app()
