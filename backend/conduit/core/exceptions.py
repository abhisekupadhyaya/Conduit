"""Domain exceptions + FastAPI handlers.

Kept deliberately small. The product invariant "nothing is silently lost"
means failures must surface, never be swallowed.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ConduitError(Exception):
    """Base for expected, mapped errors."""

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ConduitError):
    status_code = 404


class AuthError(ConduitError):
    status_code = 401


class ForbiddenError(ConduitError):
    status_code = 403


class ConflictError(ConduitError):
    status_code = 409


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConduitError)
    async def _handle(_: Request, exc: ConduitError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "message": exc.message},
        )
