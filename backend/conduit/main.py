"""Conduit API — single deployable; the lifecycle engine runs in-process (AD4).

One FastAPI app composes the four portal slices under the configured API
prefix and, on startup, spawns the engine poll loop as a background task in
the same process (no second service).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from conduit.core.config import get_settings
from conduit.core.exceptions import install_exception_handlers
from conduit.core.middleware import install_middleware
from conduit.guest.api import router as guest_router
from conduit.public.api import router as public_router
from conduit.servicer.api import router as servicer_router
from conduit.shared.engine.runner import run_engine
from conduit.supervisor.api import router as supervisor_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = asyncio.Event()
    task = asyncio.create_task(run_engine(stop))
    try:
        yield
    finally:
        stop.set()
        await task


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Conduit", version="0.0.0", lifespan=lifespan)

    install_middleware(app)
    install_exception_handlers(app)

    for r in (public_router, guest_router, servicer_router, supervisor_router):
        app.include_router(r, prefix=s.api_prefix)

    return app


app = create_app()
