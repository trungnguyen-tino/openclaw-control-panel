"""Contract test — assert every Flask route claimed by the plan is registered.

This is the safety net that catches missing-blueprint regressions. If a route
disappears, this test fails before any downstream feature test.
"""

from __future__ import annotations


EXPECTED_ROUTES: set[tuple[str, str]] = {
    # health
    ("GET", "/api/health"),
    # auth
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/create-user"),
    ("GET", "/api/auth/user"),
    ("PUT", "/api/auth/change-password"),
    ("DELETE", "/api/auth/user"),
    # info
    ("GET", "/api/info"),
    ("GET", "/api/status"),
    ("GET", "/api/version"),
    ("GET", "/api/system"),
    ("GET", "/api/logs"),
    ("GET", "/api/logs/stream"),
    ("GET", "/api/domain"),
    # control
    ("POST", "/api/restart"),
    ("POST", "/api/stop"),
    ("POST", "/api/start"),
    ("POST", "/api/rebuild"),
    ("POST", "/api/upgrade"),
    ("POST", "/api/reset"),
    ("POST", "/api/self-update"),
    # providers / config
    ("GET", "/api/providers"),
    ("GET", "/api/config"),
    ("PUT", "/api/config/provider"),
    ("PUT", "/api/config/api-key"),
    ("DELETE", "/api/config/api-key"),
    ("POST", "/api/config/test-key"),
    ("POST", "/api/config/custom-provider"),
    ("GET", "/api/config/custom-providers"),
    ("PUT", "/api/config/custom-provider/<provider>"),
    ("DELETE", "/api/config/custom-provider/<provider>"),
    # agents
    ("GET", "/api/agents"),
    ("POST", "/api/agents"),
    ("GET", "/api/agents/<agent_id>"),
    ("PUT", "/api/agents/<agent_id>"),
    ("DELETE", "/api/agents/<agent_id>"),
    ("PUT", "/api/agents/<agent_id>/default"),
    ("GET", "/api/agents/<agent_id>/api-key"),
    ("PUT", "/api/agents/<agent_id>/api-key"),
    # bindings
    ("GET", "/api/bindings"),
    ("POST", "/api/bindings"),
    ("PUT", "/api/bindings/<int:index>"),
    ("DELETE", "/api/bindings/<int:index>"),
    # channels — multi-account
    ("GET", "/api/channels"),
    ("GET", "/api/channels/schema"),
    ("POST", "/api/channels/<channel>/accounts"),
    ("DELETE", "/api/channels/<channel>/accounts/<account_id>"),
    # channels — legacy single-account (back-compat)
    ("PUT", "/api/channels/<channel>"),
    ("DELETE", "/api/channels/<channel>"),
    # OAuth Codex
    ("POST", "/api/config/chatgpt-oauth/start"),
    ("POST", "/api/config/chatgpt-oauth/complete"),
    ("POST", "/api/config/chatgpt-oauth/refresh"),
    # devices
    ("GET", "/api/devices"),
    ("POST", "/api/devices/approve/<device_id>"),
    ("GET", "/pair"),
    # CLI / terminal
    ("POST", "/api/cli"),
    ("GET", "/api/terminal/stream"),
    # domain + env
    ("PUT", "/api/domain"),
    ("GET", "/api/env"),
    ("PUT", "/api/env/<key>"),
    ("DELETE", "/api/env/<key>"),
    # upgrade discovery
    ("GET", "/api/upgrade/versions"),
    # OpenClaw chat — live sessions
    ("GET", "/api/openclaw/sessions"),
    ("DELETE", "/api/openclaw/sessions/<sid>"),
    ("GET", "/api/openclaw/sessions/<sid>/messages"),
    ("GET", "/api/openclaw/sessions/<sid>/stream"),
    ("POST", "/api/openclaw/sessions/<sid>/send"),
}


def _registered(app) -> set[tuple[str, str]]:  # type: ignore[no-untyped-def]
    out: set[tuple[str, str]] = set()
    for rule in app.url_map.iter_rules():
        rule_str = str(rule.rule)
        for method in sorted(rule.methods or set()):
            if method in {"HEAD", "OPTIONS"}:
                continue
            out.add((method, rule_str))
    return out


def test_every_planned_endpoint_is_registered(app) -> None:  # type: ignore[no-untyped-def]
    registered = _registered(app)
    missing = EXPECTED_ROUTES - registered
    assert not missing, f"Missing routes:\n  " + "\n  ".join(
        f"{m} {p}" for m, p in sorted(missing)
    )


def test_no_unexpected_api_routes(app) -> None:  # type: ignore[no-untyped-def]
    """Catch typos/dupes — every `/api/*` and `/pair` route must be on the list."""
    registered = _registered(app)
    extra: set[tuple[str, str]] = set()
    for method, rule in registered:
        if rule.startswith("/api/") or rule == "/pair":
            if (method, rule) not in EXPECTED_ROUTES:
                extra.add((method, rule))
    assert not extra, f"Unexpected routes:\n  " + "\n  ".join(
        f"{m} {p}" for m, p in sorted(extra)
    )
