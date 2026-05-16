"""Cross-cutting middleware: CORS + a request id for traceability."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from conduit.core.config import get_settings


def install_middleware(app: FastAPI) -> None:
    s = get_settings()

    # Absolute-base frontend → backend owns CORS (conscious AD6 divergence).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response
