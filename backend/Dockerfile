# Conduit backend — API + in-process lifecycle/timer engine (AD4).
# Built for linux/arm64 (deployed on t4g/Graviton ECS-on-EC2, AD1).
#
# One image, three entrypoints:
#   API     (default CMD)            uvicorn apps.api_main:app
#   migrate (task-def command)       alembic upgrade head
#   seed    (task-def command)       python -m conduit.seed
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build toolchain only for the install step (bcrypt<4 / any sdist fallbacks).
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Dependency layer: copy metadata + package, install, then drop the toolchain.
COPY pyproject.toml ./
COPY conduit ./conduit
RUN pip install --upgrade pip \
 && pip install . \
 && apt-get purge -y build-essential \
 && apt-get autoremove -y

# Source the runtime needs from the working directory (cwd-relative):
#   apps/        — uvicorn target (not packaged in the wheel)
#   alembic.ini  — migrate task
#   migrations/  — Alembic revisions
COPY apps ./apps
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

# Run as non-root.
RUN useradd --system --uid 10001 conduit \
 && chown -R conduit:conduit /app
USER conduit

EXPOSE 8000

CMD ["uvicorn", "apps.api_main:app", "--host", "0.0.0.0", "--port", "8000"]
