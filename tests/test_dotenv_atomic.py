"""Phase 02 — atomic .env writer tests."""

from __future__ import annotations

import threading
from pathlib import Path

from app.utils.dotenv_atomic import (
    dotenv_get,
    dotenv_read,
    dotenv_set,
    dotenv_unset,
)


def test_read_simple(tmp_openclaw_home: Path) -> None:
    env_file = tmp_openclaw_home / ".env"
    env_file.write_text("FOO=bar\nBAZ=qux\n")
    data = dotenv_read(env_file)
    assert data == {"FOO": "bar", "BAZ": "qux"}


def test_read_ignores_comments_and_blank_lines(tmp_openclaw_home: Path) -> None:
    env_file = tmp_openclaw_home / ".env"
    env_file.write_text("# a comment\n\nFOO=bar\n# trailing\n")
    assert dotenv_read(env_file) == {"FOO": "bar"}


def test_read_strips_quoted_values(tmp_openclaw_home: Path) -> None:
    env_file = tmp_openclaw_home / ".env"
    env_file.write_text("A=\"hello\"\nB='world'\n")
    assert dotenv_read(env_file) == {"A": "hello", "B": "world"}


def test_set_preserves_comments_and_order(tmp_openclaw_home: Path) -> None:
    env_file = tmp_openclaw_home / ".env"
    env_file.write_text("# header\nFOO=old\n# mid\nBAZ=keep\n")
    dotenv_set("FOO", "new", path=env_file)
    content = env_file.read_text()
    assert "# header" in content
    assert "# mid" in content
    assert "FOO=new" in content
    assert "FOO=old" not in content
    assert "BAZ=keep" in content


def test_set_appends_new_key(tmp_openclaw_home: Path) -> None:
    env_file = tmp_openclaw_home / ".env"
    env_file.write_text("EXISTING=1\n")
    dotenv_set("NEW", "2", path=env_file)
    data = dotenv_read(env_file)
    assert data == {"EXISTING": "1", "NEW": "2"}


def test_unset_removes_line(tmp_openclaw_home: Path) -> None:
    env_file = tmp_openclaw_home / ".env"
    env_file.write_text("A=1\nB=2\n")
    dotenv_unset("A", path=env_file)
    assert dotenv_read(env_file) == {"B": "2"}


def test_get_with_default(tmp_openclaw_home: Path) -> None:
    env_file = tmp_openclaw_home / ".env"
    env_file.write_text("PRESENT=yes\n")
    assert dotenv_get("PRESENT", path=env_file) == "yes"
    assert dotenv_get("MISSING", default="fallback", path=env_file) == "fallback"


def test_atomic_write_permissions(tmp_openclaw_home: Path) -> None:
    env_file = tmp_openclaw_home / ".env"
    dotenv_set("SECRET", "value", path=env_file)
    mode = env_file.stat().st_mode & 0o777
    assert mode == 0o600


def test_concurrent_set_no_corruption(tmp_openclaw_home: Path) -> None:
    """Stress: many threads writing different keys → final file has all of them."""
    env_file = tmp_openclaw_home / ".env"
    env_file.write_text("")
    n = 30

    def worker(i: int) -> None:
        dotenv_set(f"KEY_{i}", f"val_{i}", path=env_file)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    data = dotenv_read(env_file)
    # Atomic-rename guarantees no torn lines. Last-writer-wins on contention,
    # but every key written at least once should be readable for its value.
    for i in range(n):
        assert f"KEY_{i}" in data, f"KEY_{i} missing after concurrent writes"
        assert data[f"KEY_{i}"] == f"val_{i}"
