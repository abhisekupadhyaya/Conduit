"""Shared test fixtures. Kept minimal at scaffolding stage."""
from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
