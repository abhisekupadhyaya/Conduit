"""Entry point for the Conduit API service (engine runs in-process — AD4).

Run:
    uvicorn apps.api_main:app --reload --port 8000
"""

from conduit.main import app

__all__ = ["app"]
