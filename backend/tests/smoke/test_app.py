"""Smoke: the app composes and the public health route is mounted under /api."""
from __future__ import annotations


def test_app_composes_and_health_mounted() -> None:
    from conduit.main import app

    paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/api/health" in paths
