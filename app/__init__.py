"""Flask application factory.

Routes are registered as blueprints in `register_blueprints`. Each phase adds its
blueprint registration here, keeping `create_app` linear and discoverable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, send_from_directory

# Resolve to an absolute path so Flask serves the SPA correctly regardless of
# the cwd `gunicorn` is launched from (systemd uses WorkingDirectory but tests
# do not).
_STATIC_DIST = (Path(__file__).resolve().parent.parent / "static" / "dist").resolve()


def create_app(config: dict[str, Any] | None = None) -> Flask:
    # static_folder=None disables Flask's auto-registered static route so our
    # explicit SPA fallback owns the entire URL space below /api/*. We serve
    # files manually via `send_from_directory(_STATIC_DIST, …)`.
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(config or {})
    # Cap body size globally — protects the single gunicorn worker from OOM
    # via a malicious 100 MB POST. 1 MB is generous for our JSON payloads.
    app.config.setdefault("MAX_CONTENT_LENGTH", 1 * 1024 * 1024)

    register_extensions(app)
    register_blueprints(app)
    register_cors(app)
    register_spa_fallback(app)
    return app


def register_extensions(app: Flask) -> None:
    import os

    from app.extensions import limiter

    limiter.init_app(app)
    # Start OAuth refresher only in real deployments. Tests / CLI set the env
    # var to skip background threads.
    if not app.config.get("TESTING") and os.environ.get("OPENCLAW_DISABLE_REFRESHER") != "1":
        try:
            from app.services.oauth_refresher_thread import start_once

            start_once()
        except Exception:
            # Never block app start because the refresher couldn't spin up.
            pass


def register_blueprints(app: Flask) -> None:
    # Blueprints are wired here as later phases land. Keep imports inside the
    # function so phase-01 boots even if later modules are absent.
    try:
        from app.routes.info_routes import info_bp

        app.register_blueprint(info_bp)
    except ImportError:
        pass
    try:
        from app.routes.control_routes import control_bp

        app.register_blueprint(control_bp)
    except ImportError:
        pass
    try:
        from app.routes.auth_routes import auth_bp

        app.register_blueprint(auth_bp)
    except ImportError:
        pass
    try:
        from app.routes.config_routes import config_bp

        app.register_blueprint(config_bp)
    except ImportError:
        pass
    try:
        from app.routes.agents_routes import agents_bp

        app.register_blueprint(agents_bp)
    except ImportError:
        pass
    try:
        from app.routes.bindings_routes import bindings_bp

        app.register_blueprint(bindings_bp)
    except ImportError:
        pass
    try:
        from app.routes.channels_routes import channels_bp

        app.register_blueprint(channels_bp)
    except ImportError:
        pass
    try:
        from app.routes.oauth_routes import oauth_bp

        app.register_blueprint(oauth_bp)
    except ImportError:
        pass
    try:
        from app.routes.devices_routes import devices_bp

        app.register_blueprint(devices_bp)
    except ImportError:
        pass
    try:
        from app.routes.cli_routes import cli_bp

        app.register_blueprint(cli_bp)
    except ImportError:
        pass
    try:
        from app.routes.domain_routes import domain_bp

        app.register_blueprint(domain_bp)
    except ImportError:
        pass
    try:
        from app.routes.env_routes import env_bp

        app.register_blueprint(env_bp)
    except ImportError:
        pass
    try:
        from app.routes.terminal_routes import terminal_bp

        app.register_blueprint(terminal_bp)
    except ImportError:
        pass
    try:
        from app.routes.health_routes import health_bp

        app.register_blueprint(health_bp)
    except ImportError:
        pass
    try:
        from app.routes.openclaw_chat_routes import openclaw_chat_bp

        app.register_blueprint(openclaw_chat_bp)
    except ImportError:
        pass


def register_cors(app: Flask) -> None:
    """Permissive CORS for the SPA + strict CSP to mitigate localStorage XSS."""

    @app.after_request
    def _security_headers(response):  # type: ignore[no-untyped-def]
        # SPA is same-origin; we don't need credentialed CORS. `*` is safe
        # because no endpoint relies on cookies — Bearer must be set explicitly.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "Authorization, Content-Type"
        )
        # CSP: lock asset sources to same-origin. `unsafe-inline` for styles
        # needed by Tailwind's runtime classes; can be tightened post-MVP via
        # nonces if we drop Tailwind's JIT inline styles.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "connect-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "script-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


def register_spa_fallback(app: Flask) -> None:
    """Serve React SPA for any non-API path so client-side routing works.

    `index.html` carries a `data-theme="__OPENCLAW_THEME__"` placeholder on
    <html>; we substitute the live value from env on every request. SPA reads
    the attribute at startup to pick the brand logo + colour palette.
    """
    valid_themes = {"default", "ictsaigon"}

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path: str):  # type: ignore[no-untyped-def]
        if path.startswith("api/"):
            return {"ok": False, "error": "Not found"}, 404
        static_root = str(_STATIC_DIST)
        candidate = _STATIC_DIST / path
        if path and candidate.is_file():
            return send_from_directory(static_root, path)
        index = _STATIC_DIST / "index.html"
        if index.is_file():
            theme = os.environ.get("OPENCLAW_THEME", "default")
            if theme not in valid_themes:
                theme = "default"
            html = index.read_text(encoding="utf-8").replace(
                "__OPENCLAW_THEME__", theme
            )
            return html, 200, {"Content-Type": "text/html; charset=utf-8"}
        return (
            "<h1>OpenClaw Panel</h1><p>SPA not built. Run <code>make build-ui</code>.</p>",
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )
