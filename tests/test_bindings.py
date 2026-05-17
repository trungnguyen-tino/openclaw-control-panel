"""Phase 05 — channel→agent binding tests."""

from __future__ import annotations

from pathlib import Path


def _auth_h(tmp_home: Path) -> dict[str, str]:
    key = "b" * 64
    (tmp_home / ".env").write_text(f"OPENCLAW_MGMT_API_KEY={key}\n")
    return {"Authorization": f"Bearer {key}"}


def test_create_list_delete_bindings(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    for ch in ("telegram", "discord", "slack"):
        r = client.post(
            "/api/bindings",
            json={"agentId": "alpha", "match": {"channel": ch}},
            headers=h,
        )
        assert r.status_code == 201
    listing = client.get("/api/bindings", headers=h)
    bindings = listing.get_json()["bindings"]
    assert len(bindings) == 3
    # Delete the middle binding.
    r = client.delete("/api/bindings/1", headers=h)
    assert r.status_code == 200
    listing2 = client.get("/api/bindings", headers=h)
    bindings2 = listing2.get_json()["bindings"]
    assert len(bindings2) == 2
    channels_left = [b["match"]["channel"] for b in bindings2]
    assert channels_left == ["telegram", "slack"]


def test_binding_requires_channel(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.post(
        "/api/bindings",
        json={"agentId": "alpha", "match": {}},
        headers=h,
    )
    assert r.status_code == 400


def test_update_binding_at_index(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    client.post(
        "/api/bindings",
        json={"agentId": "alpha", "match": {"channel": "telegram"}},
        headers=h,
    )
    r = client.put(
        "/api/bindings/0",
        json={"agentId": "beta"},
        headers=h,
    )
    assert r.status_code == 200
    listing = client.get("/api/bindings", headers=h)
    assert listing.get_json()["bindings"][0]["agentId"] == "beta"


def test_delete_out_of_bounds_returns_404(client, tmp_openclaw_home: Path) -> None:  # type: ignore[no-untyped-def]
    h = _auth_h(tmp_openclaw_home)
    r = client.delete("/api/bindings/99", headers=h)
    assert r.status_code == 404
