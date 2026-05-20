"""Phase 02 — subprocess_safe.run_cmd tests."""

from __future__ import annotations

import pytest

from app.utils.subprocess_safe import run_cmd


def test_run_cmd_returns_completed_process() -> None:
    r = run_cmd(["/bin/echo", "hello"])
    assert r.returncode == 0
    assert r.stdout.strip() == "hello"


def test_run_cmd_rejects_string_args() -> None:
    with pytest.raises(TypeError):
        run_cmd("echo hi")  # type: ignore[arg-type]


def test_run_cmd_env_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOULD_NOT_LEAK", "secret")
    # printenv exits 0 if var present, 1 if absent.
    r = run_cmd(["/usr/bin/env"])
    assert "SHOULD_NOT_LEAK" not in r.stdout


def test_run_cmd_env_extra_added() -> None:
    r = run_cmd(["/usr/bin/env"], env={"INJECTED": "yes"})
    assert "INJECTED=yes" in r.stdout


def test_run_cmd_timeout_raises() -> None:
    import subprocess

    with pytest.raises(subprocess.TimeoutExpired):
        run_cmd(["/bin/sleep", "5"], timeout=0.1)


def test_run_cmd_path_default_present() -> None:
    r = run_cmd(["/usr/bin/env"])
    assert "PATH=" in r.stdout
