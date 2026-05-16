# Auth Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first buildable vertical — an `account` identity model and cookie-session auth for all three portals, with supervisor-managed provisioning and a regression-proof backend test bench.

**Architecture:** Vertical slice on the existing scaffold. Layering `api → services → dal → models`; ORM up, pydantic mapping only at the API edge; transactions commit at the request edge. httpOnly cookie session (JWT via the existing `issue_token`), bcrypt/passlib hashing. One React SPA, role-routed; auth direct in `auth-provider`, everything else TanStack Query. Work happens in an isolated git worktree with a copied venv; ends with tests green, a pushed branch, and a PR.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, asyncpg, PyJWT, passlib[bcrypt], pytest/pytest-asyncio/pytest-cov, httpx; React 19, TanStack Query, react-router 7, shadcn (radix-nova), Tailwind 4, react-hook-form + zod.

**Source spec:** `docs/superpowers/specs/2026-05-16-auth-slice-design.md` (read it before starting; it is the contract).

---

## Execution prerequisites (read first)

- **Postgres is required for the test bench** (the spec rejects sqlite — auth correctness needs `lower()` unique index, `timestamptz`, real CHECK behaviour). A reachable Postgres server is an execution prerequisite. The suite connects with `CONDUIT_TEST_ADMIN_URL` (default `postgresql+asyncpg://conduit:conduit@localhost:5432/postgres`) to **create and drop** a throwaway `conduit_test` database. Task 0c is a preflight that fails fast with clear instructions if no server is reachable — do not degrade to sqlite.
- The base interpreter at `/workspace/environment/python/bin` is shared across worktrees on this machine, so a **copied** `.venv` keeps a valid `bin/python` symlink. Always invoke tools as `.venv/bin/python -m <tool>` (pytest/alembic/uvicorn) — never the `bin/<tool>` wrapper scripts (their shebangs carry the old absolute path and break after copy).

---

## File structure (decomposition locked here)

**Backend — create**
- `backend/conduit/shared/models/account.py` — the `account` ORM table (the only DB contract for this slice).
- `backend/conduit/public/dal/accounts.py` — pure account persistence (owned here; imported by supervisor).
- `backend/conduit/public/schemas/auth.py` — `LoginIn`, `AuthUser`, `SelfUpdateIn`.
- `backend/conduit/public/services/auth.py` — `authenticate`, `current_account`, `update_self`.
- `backend/conduit/supervisor/schemas/accounts.py` — `AccountCreateIn`, `AccountUpdateIn`, `AccountOut`.
- `backend/conduit/supervisor/services/accounts.py` — `list_accounts`, `create_account`, `update_account` (+ lockout guards).
- `backend/conduit/supervisor/api/accounts.py` — supervisor account endpoints.
- `backend/conduit/seed.py` — idempotent bootstrap-supervisor seed (`python -m conduit.seed`).
- `backend/migrations/versions/0001_account.py` — first Alembic revision.
- `backend/tests/conftest.py` — replace: throwaway-DB + model-delete teardown + client/fixtures.
- `backend/tests/db/test_migration.py`, `tests/dal/test_accounts.py`, `tests/services/test_auth.py`, `tests/services/test_accounts.py`, `tests/api/test_auth.py`, `tests/api/test_accounts.py`, `tests/api/test_security_guards.py`, `tests/test_seed.py`.

**Backend — modify**
- `backend/conduit/core/security.py` — add cookie + password helpers.
- `backend/conduit/core/deps.py` — resolve `Actor` from cookie (drop `HTTPBearer`).
- `backend/conduit/core/config.py` — add `cookie_name`, `cookie_secure`, test-DB settings.
- `backend/conduit/core/exceptions.py` — add `ConflictError` (409).
- `backend/conduit/core/middleware.py` — CORS allow-credentials for the explicit origin.
- `backend/conduit/shared/models/__init__.py` — import `account` so Alembic sees metadata.
- `backend/conduit/public/api/auth.py` — real login/logout/me.
- `backend/conduit/public/api/__init__.py` — include the `me` routes.
- `backend/conduit/supervisor/api/__init__.py` — include `accounts_router`.
- `backend/pyproject.toml` — add `pytest-cov`; add coverage config.
- `backend/.env.example` — add cookie + seed + test-DB vars.
- `docs/archi/code-structure.md` — one-line note: `public/dal/accounts.py` owned, imported by supervisor.

**Frontend — create**
- `src/components/layout/page-header.tsx`, `src/components/common/{empty-state,error-state,status-badge,role-badge,confirm,data-table-shell}.tsx`.
- `src/components/app-boot-splash.tsx`.
- `src/auth/use-update-self.ts`.
- `src/shell/supervisor/hooks/use-accounts.ts`.
- `src/shell/supervisor/pages/{settings,manage-servicers,manage-guests}.tsx`.
- `src/shell/guest/settings.tsx`, `src/shell/servicer/settings.tsx`.
- `src/components/common/account-form-dialog.tsx` (shared create/edit dialog).

**Frontend — modify**
- `src/auth/auth-provider.tsx`, `src/auth/use-auth.ts` (add `refreshUser`, `loading`).
- `src/lib/api-client.ts` (register `onUnauthorized`).
- `src/components/layout/nav-user.tsx` (Settings item).
- `src/shell/supervisor/nav.tsx`, `src/App.tsx` (routes).
- `src/shell/supervisor/index.tsx`, `src/shell/guest/index.tsx`, `src/shell/servicer/index.tsx` (retrofit to primitives).
- `src/index.css` (remove the stray dark `--sidebar-primary` indigo).
- `src/main.tsx` (wrap with `<AppBootSplash>` gating).

---

# PHASE 0 — Isolated worktree, env, preflight

### Task 0a: Commit this plan, create the worktree

**Files:** none (git ops)

- [ ] **Step 1: Commit the plan on the design branch**

```bash
cd /workspace/Conduit
git add docs/superpowers/plans/2026-05-16-auth-slice.md
git commit -m "docs: auth slice implementation plan"
```

- [ ] **Step 2: Create the worktree on a fresh feature branch off the design branch**

```bash
cd /workspace/Conduit
git worktree add /workspace/Conduit-auth-slice -b feat/auth-slice auth-slice-design
```

Expected: `Preparing worktree (new branch 'feat/auth-slice')`. All subsequent work happens in `/workspace/Conduit-auth-slice`.

- [ ] **Step 3: Verify the worktree carries the spec + plan**

```bash
ls /workspace/Conduit-auth-slice/docs/superpowers/specs/2026-05-16-auth-slice-design.md
ls /workspace/Conduit-auth-slice/docs/superpowers/plans/2026-05-16-auth-slice.md
```

Expected: both paths exist.

### Task 0b: Seed the worktree venv from the existing one

**Files:** none (env ops)

- [ ] **Step 1: Copy the existing venv into the worktree**

```bash
cp -r /workspace/Conduit/backend/.venv /workspace/Conduit-auth-slice/backend/.venv
```

- [ ] **Step 2: Re-link the editable package to the worktree path**

```bash
cd /workspace/Conduit-auth-slice/backend
.venv/bin/python -m pip install -e ".[dev]"
```

Expected: deps already satisfied; pip only re-links `conduit` editable to the worktree. No network failures should block (all deps present in the copied venv).

- [ ] **Step 3: Sanity-check the interpreter and imports**

```bash
.venv/bin/python -c "import conduit, fastapi, sqlalchemy, passlib.hash, jwt; print('ok', conduit.__file__)"
```

Expected: `ok /workspace/Conduit-auth-slice/backend/conduit/__init__.py`

- [ ] **Step 4: Baseline test run (scaffold smoke must pass)**

```bash
.venv/bin/python -m pytest -q
```

Expected: the existing smoke test passes (1 passed). This proves the copied env works before any changes.

### Task 0c: Postgres preflight (fail fast, no silent degrade)

**Files:** none

- [ ] **Step 1: Probe the Postgres admin connection**

```bash
cd /workspace/Conduit-auth-slice/backend
CONDUIT_TEST_ADMIN_URL="${CONDUIT_TEST_ADMIN_URL:-postgresql+asyncpg://conduit:conduit@localhost:5432/postgres}" \
.venv/bin/python - <<'PY'
import asyncio, os, sys
import asyncpg
url = os.environ["CONDUIT_TEST_ADMIN_URL"].replace("postgresql+asyncpg://", "postgresql://")
async def main():
    try:
        c = await asyncpg.connect(url); await c.execute("SELECT 1"); await c.close()
        print("postgres reachable")
    except Exception as e:
        print("POSTGRES UNREACHABLE:", e); sys.exit(1)
asyncio.run(main())
PY
```

Expected: `postgres reachable`. **If it prints `POSTGRES UNREACHABLE`, stop and surface this to the user**: the test bench cannot run without a Postgres server; provide one and set `CONDUIT_TEST_ADMIN_URL`. Do not switch to sqlite.

---

# PHASE 1 — Backend (TDD; ends fully green)

> All commands below run from `/workspace/Conduit-auth-slice/backend`. Tool form is always `.venv/bin/python -m <tool>`.

### Task 1: Config — cookie + test-DB settings

**Files:**
- Modify: `backend/conduit/core/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add settings fields**

In `conduit/core/config.py`, inside `class Settings`, after `jwt_ttl_minutes`:

```python
    cookie_name: str = "conduit_session"
    cookie_secure: bool = False  # env-driven: true in prod (https), false on localhost
    cookie_samesite: str = "lax"

    seed_supervisor_username: str = ""
    seed_supervisor_password: str = ""

    test_admin_url: str = (
        "postgresql+asyncpg://conduit:conduit@localhost:5432/postgres"
    )
    test_database_name: str = "conduit_test"
```

- [ ] **Step 2: Append to `.env.example`**

Append:

```
# --- Session cookie ---
CONDUIT_COOKIE_NAME=conduit_session
CONDUIT_COOKIE_SECURE=false
CONDUIT_COOKIE_SAMESITE=lax

# --- Bootstrap supervisor seed (python -m conduit.seed) ---
CONDUIT_SEED_SUPERVISOR_USERNAME=
CONDUIT_SEED_SUPERVISOR_PASSWORD=

# --- Test bench (throwaway DB created/dropped per session) ---
CONDUIT_TEST_ADMIN_URL=postgresql+asyncpg://conduit:conduit@localhost:5432/postgres
CONDUIT_TEST_DATABASE_NAME=conduit_test
```

- [ ] **Step 3: Verify settings load**

Run: `.venv/bin/python -c "from conduit.core.config import get_settings as g; print(g().cookie_name, g().test_database_name)"`
Expected: `conduit_session conduit_test`

- [ ] **Step 4: Commit**

```bash
git add conduit/core/config.py .env.example
git commit -m "feat(config): cookie + seed + test-db settings"
```

### Task 2: Exceptions — add `ConflictError`

**Files:**
- Modify: `backend/conduit/core/exceptions.py`
- Test: `backend/tests/api/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_exceptions.py`:

```python
def test_conflict_error_is_409():
    from conduit.core.exceptions import ConflictError, ConduitError
    e = ConflictError("dupe")
    assert isinstance(e, ConduitError)
    assert e.status_code == 409
    assert e.message == "dupe"
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/api/test_exceptions.py -q`
Expected: FAIL — `ImportError: cannot import name 'ConflictError'`.

- [ ] **Step 3: Implement**

In `conduit/core/exceptions.py`, after `class ForbiddenError`:

```python
class ConflictError(ConduitError):
    status_code = 409
```

- [ ] **Step 4: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/api/test_exceptions.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add conduit/core/exceptions.py tests/api/test_exceptions.py
git commit -m "feat(exceptions): add ConflictError(409)"
```

### Task 3: Security — password + cookie helpers

**Files:**
- Modify: `backend/conduit/core/security.py`
- Test: `backend/tests/services/test_security.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_security.py`:

```python
import pytest


def test_password_hash_roundtrip():
    from conduit.core.security import hash_password, verify_password
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"
    assert verify_password("s3cret-pw", h) is True
    assert verify_password("wrong", h) is False


def test_password_long_input_does_not_crash():
    # bcrypt has a 72-byte cap; the helper must guard, not raise.
    from conduit.core.security import hash_password, verify_password
    pw = "a" * 200
    h = hash_password(pw)
    assert verify_password(pw, h) is True


def test_cookie_set_and_clear():
    from fastapi import Response
    from conduit.core.security import set_session_cookie, clear_session_cookie
    r = Response()
    set_session_cookie(r, "tok123")
    sc = r.headers["set-cookie"]
    assert "conduit_session=tok123" in sc
    assert "HttpOnly" in sc
    assert "SameSite=lax" in sc.replace("Lax", "lax")
    r2 = Response()
    clear_session_cookie(r2)
    assert "conduit_session=" in r2.headers["set-cookie"]
    assert ("Max-Age=0" in r2.headers["set-cookie"]) or ("expires=" in r2.headers["set-cookie"].lower())
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/services/test_security.py -q`
Expected: FAIL — `ImportError: cannot import name 'hash_password'`.

- [ ] **Step 3: Implement**

Append to `conduit/core/security.py`:

```python
from fastapi import Response
from passlib.hash import bcrypt

_BCRYPT_MAX = 72


def _clamp(pw: str) -> bytes:
    return pw.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(pw: str) -> str:
    return bcrypt.hash(_clamp(pw))


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.verify(_clamp(pw), hashed)
    except ValueError:
        return False


def set_session_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(
        key=s.cookie_name,
        value=token,
        httponly=True,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        path="/",
        max_age=s.jwt_ttl_minutes * 60,
    )


def clear_session_cookie(resp: Response) -> None:
    s = get_settings()
    resp.delete_cookie(key=s.cookie_name, path="/")
```

- [ ] **Step 4: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/services/test_security.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add conduit/core/security.py tests/services/test_security.py
git commit -m "feat(security): bcrypt password + session cookie helpers"
```

### Task 4: The `account` model + metadata registration

**Files:**
- Create: `backend/conduit/shared/models/account.py`
- Modify: `backend/conduit/shared/models/__init__.py`
- Test: `backend/tests/db/test_model_import.py`

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_model_import.py`:

```python
def test_account_table_registered_on_metadata():
    from conduit.shared.db import Base
    import conduit.shared.models  # noqa: F401  (must register account)
    t = Base.metadata.tables["account"]
    cols = set(t.columns.keys())
    assert cols == {
        "id", "role", "username", "secret_hash",
        "display_name", "status", "created_at", "updated_at",
    }
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/db/test_model_import.py -q`
Expected: FAIL — `KeyError: 'account'`.

- [ ] **Step 3: Implement the model**

Create `conduit/shared/models/account.py`:

```python
"""The account entity (IDENTITY). The only DB contract for the auth slice.

text + CHECK over PG enum keeps rule changes from migrating data
(datamodels principle: structure permissive, mechanism in code). Resolves
datamodels Q1 = unified account; account.id is the stable join target for
all later entities. Disable, never delete (D29).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base

ROLES = ("guest", "servicer", "supervisor", "duty_manager")
STATUSES = ("active", "disabled")


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (
        CheckConstraint(
            "role in ('guest','servicer','supervisor','duty_manager')",
            name="ck_account_role",
        ),
        CheckConstraint(
            "status in ('active','disabled')", name="ck_account_status"
        ),
        Index(
            "uq_account_username_lower",
            func.lower(text("username")),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="active"
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

- [ ] **Step 4: Register on import**

Replace `conduit/shared/models/__init__.py` body so the model is imported (keep the module docstring) — ensure these lines exist:

```python
from conduit.shared.db import Base
from conduit.shared.models.account import Account

__all__ = ["Base", "Account"]
```

- [ ] **Step 5: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/db/test_model_import.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add conduit/shared/models/account.py conduit/shared/models/__init__.py tests/db/test_model_import.py
git commit -m "feat(model): account table + metadata registration (D29, Q1 unified)"
```

### Task 5: First Alembic migration

**Files:**
- Create: `backend/migrations/versions/0001_account.py`
- Test: `backend/tests/db/test_migration.py`

- [ ] **Step 1: Write the failing test (uses the throwaway DB harness)**

> conftest does not exist yet; this test depends on Task 6. Write it now but expect it to error until Task 6 lands; that is the TDD ordering for the DB layer.

Create `tests/db/test_migration.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_account_constraints_enforced(db):
    from sqlalchemy import text
    # bad role rejected
    with pytest.raises(Exception):
        await db.execute(text(
            "insert into account(id,role,username,secret_hash,display_name)"
            " values (gen_random_uuid(),'wizard','u','h','U')"
        ))
        await db.flush()
    await db.rollback()
    # case-insensitive uniqueness
    from conduit.shared.models import Account
    db.add(Account(role="guest", username="Maria", secret_hash="h", display_name="M"))
    await db.flush()
    db.add(Account(role="guest", username="maria", secret_hash="h", display_name="M2"))
    with pytest.raises(Exception):
        await db.flush()
```

- [ ] **Step 2: Generate then hand-finalize the migration**

Run: `.venv/bin/python -m alembic revision -m "account" --rev-id 0001`
Then replace the generated `upgrade()`/`downgrade()` in `migrations/versions/0001_account.py` with:

```python
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.create_table(
        "account",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "role in ('guest','servicer','supervisor','duty_manager')",
            name="ck_account_role"),
        sa.CheckConstraint("status in ('active','disabled')",
                           name="ck_account_status"),
    )
    op.create_index("uq_account_username_lower", "account",
                     [sa.text("lower(username)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_account_username_lower", table_name="account")
    op.drop_table("account")
```

- [ ] **Step 3: Defer run to Task 6** (the harness builds the schema via `alembic upgrade head`). Mark this task's test as covered-by Task 6 Step 4.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0001_account.py tests/db/test_migration.py
git commit -m "feat(migration): 0001 account table + lower(username) unique"
```

### Task 6: Test harness — throwaway DB, model-delete teardown, client

**Files:**
- Modify: `backend/conduit/core/deps.py` (cookie actor — needed by the client fixture)
- Modify: `backend/pyproject.toml` (pytest-cov + coverage cfg)
- Replace: `backend/tests/conftest.py`

- [ ] **Step 1: Switch `current_actor` to read the cookie**

Replace the `_bearer`/`current_actor` section of `conduit/core/deps.py` with:

```python
from fastapi import Request

from conduit.core.config import get_settings
from conduit.core.exceptions import AuthError


async def current_actor(request: Request) -> Actor:
    s = get_settings()
    token = request.cookies.get(s.cookie_name)
    if not token:
        raise AuthError("not authenticated")
    payload = decode_token(token)
    return Actor(id=str(payload.get("sub")), role=str(payload.get("role")))
```

Remove the now-unused `HTTPBearer`/`HTTPAuthorizationCredentials` imports and `_bearer`. Keep `db_session`, `Actor`, `require_roles` unchanged (they depend on `current_actor`).

- [ ] **Step 2: Add pytest-cov + coverage config**

In `pyproject.toml` `[project.optional-dependencies] dev`, add `"pytest-cov>=5.0"`. Append:

```toml
[tool.coverage.run]
source = ["conduit"]

[tool.pytest.ini_options]
addopts = "-ra --strict-markers"
asyncio_mode = "auto"
testpaths = ["tests"]
```

(Replace the existing `[tool.pytest.ini_options]` block — keep `asyncio_mode`/`testpaths`.) Then:

Run: `.venv/bin/python -m pip install -e ".[dev]"`
Expected: installs `pytest-cov`.

- [ ] **Step 3: Replace `tests/conftest.py`**

```python
"""Test bench: a throwaway conduit_test DB built by alembic, function-scoped
model-delete teardown in a finally, an ASGI client bound to the test session,
and real-service factories. No sqlite — Postgres parity is required."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from conduit.core.config import get_settings


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


def _admin_url() -> str:
    return get_settings().test_admin_url


def _test_url() -> str:
    s = get_settings()
    base = s.test_admin_url.rsplit("/", 1)[0]
    return f"{base}/{s.test_database_name}"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_test_db() -> AsyncGenerator[None, None]:
    name = get_settings().test_database_name
    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await c.execute(text(f'CREATE DATABASE "{name}"'))
    await admin.dispose()

    # Build schema via alembic against the test DB.
    import os
    from alembic import command
    from alembic.config import Config

    os.environ["CONDUIT_DATABASE_URL"] = _test_url()
    get_settings.cache_clear()  # type: ignore[attr-defined]
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _test_url())
    command.upgrade(cfg, "head")

    yield

    admin = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


@pytest_asyncio.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(_test_url())
    Session = async_sessionmaker(engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        # Explicit model-level delete (no inverse service exists — D29).
        from conduit.shared.models import Account
        await session.rollback()
        await session.execute(delete(Account))
        await session.commit()
        await session.close()
        await engine.dispose()


@pytest_asyncio.fixture()
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from conduit.core.deps import db_session
    from conduit.main import app

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[db_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def make_account(db: AsyncSession):
    """Build precondition accounts through the REAL service path."""
    from conduit.supervisor.services import accounts as svc

    async def _make(role: str, username: str, password: str = "pw-123456",
                    display_name: str = "Test User"):
        acc = await svc.create_account(
            db, role=role, username=username,
            display_name=display_name, password=password)
        await db.commit()
        return acc

    return _make


@pytest_asyncio.fixture()
async def login(client: AsyncClient):
    async def _login(username: str, password: str):
        r = await client.post("/api/auth/login",
                              json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return r
    return _login
```

- [ ] **Step 4: Run the DB + migration + model tests**

Run: `.venv/bin/python -m pytest tests/db -q`
Expected: PASS — schema builds via alembic, constraints enforced, case-insensitive uniqueness rejected. (Engine background loop is off because tests never start the app lifespan; the ASGI client does not run lifespan.)

- [ ] **Step 5: Commit**

```bash
git add conduit/core/deps.py pyproject.toml tests/conftest.py
git commit -m "test(bench): throwaway DB harness + cookie actor + real-service factories"
```

### Task 7: DAL — `public/dal/accounts.py`

**Files:**
- Create: `backend/conduit/public/dal/accounts.py`
- Test: `backend/tests/dal/test_accounts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/dal/test_accounts.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_dal_crud_and_case_insensitive(db):
    from conduit.public.dal import accounts as dal

    a = await dal.insert_account(db, role="guest", username="Maria",
                                 secret_hash="h", display_name="M")
    await db.flush()
    assert a.id is not None

    assert (await dal.get_by_username(db, "maria")).id == a.id   # ci hit
    assert await dal.get_by_username(db, "nope") is None
    assert (await dal.get_by_id(db, a.id)).username == "Maria"

    await dal.insert_account(db, role="supervisor", username="sup",
                             secret_hash="h", display_name="S")
    await db.flush()
    only_guests = await dal.list_accounts(db, role="guest")
    assert [x.username for x in only_guests] == ["Maria"]

    await dal.update_account(db, a, display_name="Maria R")
    await db.flush()
    assert (await dal.get_by_id(db, a.id)).display_name == "Maria R"

    assert await dal.count_active_by_role(db, "supervisor") == 1
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/dal/test_accounts.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `conduit/public/dal/accounts.py`:

```python
"""Account persistence. Owned by the public slice; imported by supervisor
services. Pure SQL — no hashing, no rules (code-structure note)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import Account


async def get_by_username(s: AsyncSession, username: str) -> Account | None:
    res = await s.execute(
        select(Account).where(func.lower(Account.username) == username.lower())
    )
    return res.scalar_one_or_none()


async def get_by_id(s: AsyncSession, account_id: uuid.UUID | str) -> Account | None:
    return await s.get(Account, account_id)


async def list_accounts(
    s: AsyncSession, role: str | None = None, status: str | None = None
) -> list[Account]:
    q = select(Account)
    if role:
        q = q.where(Account.role == role)
    if status:
        q = q.where(Account.status == status)
    q = q.order_by(Account.created_at, Account.username)
    return list((await s.execute(q)).scalars().all())


async def insert_account(
    s: AsyncSession, *, role: str, username: str, secret_hash: str,
    display_name: str, status: str = "active",
) -> Account:
    a = Account(role=role, username=username, secret_hash=secret_hash,
                display_name=display_name, status=status)
    s.add(a)
    return a


async def update_account(s: AsyncSession, account: Account, **fields) -> Account:
    for k, v in fields.items():
        setattr(account, k, v)
    s.add(account)
    return account


async def count_active_by_role(s: AsyncSession, role: str) -> int:
    res = await s.execute(
        select(func.count()).select_from(Account)
        .where(Account.role == role, Account.status == "active")
    )
    return int(res.scalar_one())
```

- [ ] **Step 4: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/dal/test_accounts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add conduit/public/dal/accounts.py tests/dal/test_accounts.py
git commit -m "feat(dal): account persistence (public-owned)"
```

### Task 8: Supervisor service — `create_account` / `list_accounts` / `update_account` + lockout guards

**Files:**
- Create: `backend/conduit/supervisor/services/accounts.py`
- Test: `backend/tests/services/test_accounts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_accounts.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_create_hashes_and_rejects_dupe_and_bad_role(db):
    from conduit.supervisor.services import accounts as svc
    from conduit.core.exceptions import ConflictError, ConduitError
    from conduit.core.security import verify_password

    a = await svc.create_account(db, role="servicer", username="svc1",
                                 display_name="S", password="pw-123456")
    await db.flush()
    assert a.secret_hash != "pw-123456"
    assert verify_password("pw-123456", a.secret_hash)

    with pytest.raises(ConflictError):
        await svc.create_account(db, role="servicer", username="SVC1",
                                 display_name="dup", password="pw-123456")
    with pytest.raises(ConduitError):
        await svc.create_account(db, role="wizard", username="w",
                                 display_name="w", password="pw-123456")


async def test_update_lockout_guards(db):
    from conduit.supervisor.services import accounts as svc
    from conduit.core.exceptions import ConflictError
    from conduit.core.deps import Actor

    sup = await svc.create_account(db, role="supervisor", username="sup1",
                                   display_name="S", password="pw-123456")
    await db.flush()
    actor = Actor(id=str(sup.id), role="supervisor")

    # cannot disable self
    with pytest.raises(ConflictError):
        await svc.update_account(db, actor, sup.id, {"status": "disabled"})
    # cannot disable the last active supervisor (a different actor)
    other = Actor(id="00000000-0000-0000-0000-000000000000", role="supervisor")
    with pytest.raises(ConflictError):
        await svc.update_account(db, other, sup.id, {"status": "disabled"})

    sup2 = await svc.create_account(db, role="supervisor", username="sup2",
                                    display_name="S2", password="pw-123456")
    await db.flush()
    # now sup1 is not the last → disabling is allowed
    await svc.update_account(db, other, sup2.id, {"status": "disabled"})
    await db.flush()
    assert sup2.status == "disabled"
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/services/test_accounts.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `conduit/supervisor/services/accounts.py`:

```python
"""Supervisor account management — business logic only."""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor
from conduit.core.exceptions import ConflictError, ConduitError, NotFoundError
from conduit.core.security import hash_password
from conduit.public.dal import accounts as dal
from conduit.shared.models import Account
from conduit.shared.models.account import ROLES

_PATCHABLE = {"display_name", "status", "password"}


async def list_accounts(s: AsyncSession, role: str | None = None,
                         status: str | None = None) -> list[Account]:
    return await dal.list_accounts(s, role=role, status=status)


async def create_account(s: AsyncSession, *, role: str, username: str,
                         display_name: str, password: str) -> Account:
    if role not in ROLES:
        raise ConduitError(f"invalid role '{role}'")
    if not password or len(password) < 6:
        raise ConduitError("password too short")
    if await dal.get_by_username(s, username) is not None:
        raise ConflictError("username already exists")
    a = await dal.insert_account(
        s, role=role, username=username,
        secret_hash=hash_password(password), display_name=display_name)
    try:
        await s.flush()
    except IntegrityError as e:  # race on the unique index
        raise ConflictError("username already exists") from e
    return a


async def update_account(s: AsyncSession, actor: Actor,
                          account_id: uuid.UUID | str, patch: dict) -> Account:
    unknown = set(patch) - _PATCHABLE
    if unknown:
        raise ConduitError(f"unsupported fields: {sorted(unknown)}")
    acc = await dal.get_by_id(s, account_id)
    if acc is None:
        raise NotFoundError("account not found")

    if patch.get("status") == "disabled":
        if str(acc.id) == str(actor.id):
            raise ConflictError("cannot disable your own account")
        if acc.role == "supervisor" and acc.status == "active":
            if await dal.count_active_by_role(s, "supervisor") <= 1:
                raise ConflictError("cannot disable the last active supervisor")
    if "role" in patch:  # defense — role is not patchable, but guard anyway
        raise ConduitError("role is immutable")

    fields: dict = {}
    if "display_name" in patch:
        fields["display_name"] = patch["display_name"]
    if "status" in patch:
        fields["status"] = patch["status"]
    if patch.get("password"):
        fields["secret_hash"] = hash_password(patch["password"])
    await dal.update_account(s, acc, **fields)
    await s.flush()
    return acc
```

- [ ] **Step 4: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/services/test_accounts.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/services/accounts.py tests/services/test_accounts.py
git commit -m "feat(service): supervisor account mgmt + lockout guards"
```

### Task 9: Public auth service — `authenticate` / `current_account` / `update_self`

**Files:**
- Create: `backend/conduit/public/services/auth.py`
- Test: `backend/tests/services/test_auth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_auth.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_authenticate_paths(db, make_account):
    from conduit.public.services import auth
    from conduit.core.exceptions import AuthError

    await make_account("servicer", "svc1", "pw-123456")

    acc = await auth.authenticate(db, "svc1", "pw-123456")
    assert acc.username == "svc1"

    for u, p in [("svc1", "wrong"), ("ghost", "pw-123456")]:
        with pytest.raises(AuthError) as ei:
            await auth.authenticate(db, u, p)
        assert str(ei.value) == "invalid username or password"  # no enumeration

    await auth.update_self(db, acc, status_change=None, display_name=None,
                           current_password=None, new_password=None)  # no-op ok

    # disabled account cannot authenticate even with the right password
    from conduit.supervisor.services import accounts as svc
    from conduit.core.deps import Actor
    sup = await svc.create_account(db, role="supervisor", username="s9",
                                   display_name="S", password="pw-123456")
    await svc.create_account(db, role="supervisor", username="s10",
                             display_name="S", password="pw-123456")
    await db.flush()
    await svc.update_account(db, Actor(id="x", role="supervisor"), sup.id,
                             {"status": "disabled"})
    await db.flush()
    with pytest.raises(AuthError):
        await auth.authenticate(db, "s9", "pw-123456")


async def test_update_self_password(db, make_account):
    from conduit.public.services import auth
    from conduit.core.exceptions import AuthError
    from conduit.core.security import verify_password

    acc = await make_account("guest", "g1", "old-123456")
    with pytest.raises(AuthError):
        await auth.update_self(db, acc, status_change=None, display_name=None,
                               current_password="bad", new_password="new-123456")
    await auth.update_self(db, acc, status_change=None, display_name="Gee",
                           current_password="old-123456", new_password="new-123456")
    await db.flush()
    assert acc.display_name == "Gee"
    assert verify_password("new-123456", acc.secret_hash)
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/services/test_auth.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `conduit/public/services/auth.py`:

```python
"""Public auth — business logic only. Identical error for every failed
login (no user enumeration). status is re-checked, never trusted from a
token."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import AuthError, ConduitError
from conduit.core.security import hash_password, verify_password
from conduit.public.dal import accounts as dal
from conduit.shared.models import Account

_BAD = "invalid username or password"


async def authenticate(s: AsyncSession, username: str, password: str) -> Account:
    acc = await dal.get_by_username(s, username)
    if acc is None or not verify_password(password, acc.secret_hash):
        raise AuthError(_BAD)
    if acc.status != "active":
        raise AuthError(_BAD)
    return acc


async def current_account(s: AsyncSession, account_id: str) -> Account:
    acc = await dal.get_by_id(s, account_id)
    if acc is None or acc.status != "active":
        raise AuthError("not authenticated")
    return acc


async def update_self(s: AsyncSession, acc: Account, *, status_change=None,
                      display_name: str | None, current_password: str | None,
                      new_password: str | None) -> Account:
    if display_name is not None:
        if not display_name.strip():
            raise ConduitError("display name required")
        acc.display_name = display_name
    if new_password is not None:
        if not verify_password(current_password or "", acc.secret_hash):
            raise AuthError("current password is incorrect")
        if len(new_password) < 6:
            raise ConduitError("password too short")
        acc.secret_hash = hash_password(new_password)
    s.add(acc)
    await s.flush()
    return acc
```

- [ ] **Step 4: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/services/test_auth.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add conduit/public/services/auth.py tests/services/test_auth.py
git commit -m "feat(service): public auth (authenticate/current/update_self)"
```

### Task 10: Schemas

**Files:**
- Create: `backend/conduit/public/schemas/auth.py`
- Create: `backend/conduit/supervisor/schemas/accounts.py`

- [ ] **Step 1: Implement public schemas**

Create `conduit/public/schemas/auth.py`:

```python
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class LoginIn(BaseModel):
    username: str
    password: str


class AuthUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    username: str
    display_name: str


class SelfUpdateIn(BaseModel):
    display_name: str | None = None
    current_password: str | None = None
    new_password: str | None = None
```

- [ ] **Step 2: Implement supervisor schemas**

Create `conduit/supervisor/schemas/accounts.py`:

```python
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class AccountCreateIn(BaseModel):
    role: str
    username: str
    display_name: str
    password: str


class AccountUpdateIn(BaseModel):
    display_name: str | None = None
    status: str | None = None
    password: str | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    username: str
    display_name: str
    status: str
    created_at: dt.datetime
```

- [ ] **Step 3: Verify import**

Run: `.venv/bin/python -c "from conduit.public.schemas.auth import AuthUser; from conduit.supervisor.schemas.accounts import AccountOut; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add conduit/public/schemas/auth.py conduit/supervisor/schemas/accounts.py
git commit -m "feat(schemas): auth + account I/O models"
```

### Task 11: Public API — login / logout / me

**Files:**
- Modify: `backend/conduit/public/api/auth.py`
- Modify: `backend/conduit/public/api/__init__.py`
- Test: `backend/tests/api/test_auth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_auth.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_login_me_logout_cycle(client, make_account):
    await make_account("supervisor", "sup1", "pw-123456", "Sue")

    r = await client.post("/api/auth/login",
                          json={"username": "sup1", "password": "pw-123456"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "supervisor" and body["display_name"] == "Sue"
    sc = r.headers["set-cookie"]
    assert "conduit_session=" in sc and "HttpOnly" in sc
    assert "Secure" not in sc  # cookie_secure False in tests

    me = await client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["username"] == "sup1"

    out = await client.post("/api/auth/logout")
    assert out.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_login_failures_are_identical_and_setno_cookie(client, make_account):
    await make_account("guest", "g1", "pw-123456")
    a = await client.post("/api/auth/login",
                          json={"username": "g1", "password": "bad"})
    b = await client.post("/api/auth/login",
                          json={"username": "ghost", "password": "pw-123456"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()
    assert "set-cookie" not in a.headers


async def test_patch_me_changes_password(client, make_account, login):
    await make_account("guest", "g2", "old-123456", "Gee")
    await login("g2", "old-123456")
    r = await client.patch("/api/auth/me", json={
        "display_name": "Gee Two",
        "current_password": "old-123456", "new_password": "new-123456"})
    assert r.status_code == 200 and r.json()["display_name"] == "Gee Two"
    await client.post("/api/auth/logout")
    bad = await client.post("/api/auth/login",
                            json={"username": "g2", "password": "old-123456"})
    good = await client.post("/api/auth/login",
                             json={"username": "g2", "password": "new-123456"})
    assert bad.status_code == 401 and good.status_code == 200
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/api/test_auth.py -q`
Expected: FAIL — endpoints raise `NotImplementedError` / `/auth/me` missing.

- [ ] **Step 3: Implement the auth router**

Replace `conduit/public/api/auth.py`:

```python
"""Login / logout / me — cookie session (AD8)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, current_actor, db_session
from conduit.core.security import (
    clear_session_cookie,
    issue_token,
    set_session_cookie,
)
from conduit.public.schemas.auth import AuthUser, LoginIn, SelfUpdateIn
from conduit.public.services import auth as svc

router = APIRouter(prefix="/auth", tags=["public-auth"])


@router.post("/login", response_model=AuthUser)
async def login(body: LoginIn, response: Response,
                s: AsyncSession = Depends(db_session)) -> AuthUser:
    acc = await svc.authenticate(s, body.username, body.password)
    set_session_cookie(response, issue_token(subject=str(acc.id), role=acc.role))
    return AuthUser.model_validate(acc)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.get("/me", response_model=AuthUser)
async def me(actor: Actor = Depends(current_actor),
             s: AsyncSession = Depends(db_session)) -> AuthUser:
    return AuthUser.model_validate(await svc.current_account(s, actor.id))


@router.patch("/me", response_model=AuthUser)
async def patch_me(body: SelfUpdateIn, actor: Actor = Depends(current_actor),
                   s: AsyncSession = Depends(db_session)) -> AuthUser:
    acc = await svc.current_account(s, actor.id)
    acc = await svc.update_self(
        s, acc, status_change=None, display_name=body.display_name,
        current_password=body.current_password, new_password=body.new_password)
    await s.commit()
    return AuthUser.model_validate(acc)
```

> `public/api/__init__.py` already includes `auth_router`; `/me` lives on the same router, so no `__init__` change is needed. Confirm by reading it; if `auth_router` is included, skip.

- [ ] **Step 4: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/api/test_auth.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add conduit/public/api/auth.py tests/api/test_auth.py
git commit -m "feat(api): cookie-session login/logout/me + patch me"
```

### Task 12: Supervisor API — accounts CRUD (no delete)

**Files:**
- Create: `backend/conduit/supervisor/api/accounts.py`
- Modify: `backend/conduit/supervisor/api/__init__.py`
- Test: `backend/tests/api/test_accounts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_accounts.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio

ROUTES = [
    ("get", "/api/supervisor/accounts"),
    ("post", "/api/supervisor/accounts"),
]


async def test_role_gating_matrix(client, make_account, login):
    # no cookie → 401
    assert (await client.get("/api/supervisor/accounts")).status_code == 401
    for role in ("guest", "servicer"):
        await make_account(role, f"{role}1", "pw-123456")
        await login(f"{role}1", "pw-123456")
        assert (await client.get("/api/supervisor/accounts")).status_code == 403
        await client.post("/api/auth/logout")


async def test_supervisor_crud_no_delete(client, make_account, login):
    await make_account("supervisor", "sup1", "pw-123456")
    await make_account("supervisor", "sup2", "pw-123456")  # avoid last-supervisor guard
    await login("sup1", "pw-123456")

    c = await client.post("/api/supervisor/accounts", json={
        "role": "servicer", "username": "newsvc",
        "display_name": "New", "password": "pw-123456"})
    assert c.status_code == 201
    assert "secret_hash" not in c.json()
    new_id = c.json()["id"]

    dup = await client.post("/api/supervisor/accounts", json={
        "role": "servicer", "username": "NEWSVC",
        "display_name": "d", "password": "pw-123456"})
    assert dup.status_code == 409

    lst = await client.get("/api/supervisor/accounts?role=servicer")
    assert lst.status_code == 200 and any(a["id"] == new_id for a in lst.json())

    # created account can actually log in
    await client.post("/api/auth/logout")
    assert (await client.post("/api/auth/login", json={
        "username": "newsvc", "password": "pw-123456"})).status_code == 200

    # disable blocks login; re-enable restores
    await login("sup1", "pw-123456")
    d = await client.patch(f"/api/supervisor/accounts/{new_id}",
                           json={"status": "disabled"})
    assert d.status_code == 200
    await client.post("/api/auth/logout")
    assert (await client.post("/api/auth/login", json={
        "username": "newsvc", "password": "pw-123456"})).status_code == 401

    # no DELETE route exists (D29)
    await login("sup1", "pw-123456")
    assert (await client.delete(
        f"/api/supervisor/accounts/{new_id}")).status_code == 405
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/api/test_accounts.py -q`
Expected: FAIL — routes missing (404/405 mismatches, import error).

- [ ] **Step 3: Implement the accounts router**

Create `conduit/supervisor/api/accounts.py`:

```python
"""Supervisor account management API. No DELETE — D29 (disable, never delete)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.deps import Actor, db_session, require_roles
from conduit.supervisor.schemas.accounts import (
    AccountCreateIn,
    AccountOut,
    AccountUpdateIn,
)
from conduit.supervisor.services import accounts as svc

router = APIRouter(prefix="/accounts", tags=["supervisor-accounts"])
_sup = require_roles("supervisor", "duty_manager")


@router.get("", response_model=list[AccountOut])
async def list_accounts(role: str | None = None, status: str | None = None,
                        actor: Actor = Depends(_sup),
                        s: AsyncSession = Depends(db_session)):
    return [AccountOut.model_validate(a)
            for a in await svc.list_accounts(s, role=role, status=status)]


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(body: AccountCreateIn, actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    a = await svc.create_account(
        s, role=body.role, username=body.username,
        display_name=body.display_name, password=body.password)
    await s.commit()
    return AccountOut.model_validate(a)


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(account_id: uuid.UUID, body: AccountUpdateIn,
                         actor: Actor = Depends(_sup),
                         s: AsyncSession = Depends(db_session)):
    patch = body.model_dump(exclude_none=True)
    a = await svc.update_account(s, actor, account_id, patch)
    await s.commit()
    return AccountOut.model_validate(a)
```

- [ ] **Step 4: Wire the router**

In `conduit/supervisor/api/__init__.py` add the import and include:

```python
from conduit.supervisor.api.accounts import router as accounts_router
...
router.include_router(accounts_router)
```

- [ ] **Step 5: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/api/test_accounts.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add conduit/supervisor/api/accounts.py conduit/supervisor/api/__init__.py tests/api/test_accounts.py
git commit -m "feat(api): supervisor account CRUD (no delete, D29)"
```

### Task 13: Structural regression guards + middleware CORS

**Files:**
- Modify: `backend/conduit/core/middleware.py`
- Create: `backend/tests/api/test_security_guards.py`
- Create: `backend/tests/api/contract_snapshot.json` (generated in Step 4)

- [ ] **Step 1: Ensure credentialed CORS for the explicit origin**

In `conduit/core/middleware.py` confirm `CORSMiddleware` uses
`allow_origins=get_settings().cors_origin_list`, `allow_credentials=True`,
and not `["*"]`. If it sets `allow_origins=["*"]`, change it to the settings
list (cookies require an explicit origin). Keep the rest.

- [ ] **Step 2: Write the structural guard tests**

Create `tests/api/test_security_guards.py`:

```python
import json
import pathlib

import pytest

pytestmark = pytest.mark.asyncio

PUBLIC = {"/api/health", "/api/auth/login"}
SNAP = pathlib.Path(__file__).parent / "contract_snapshot.json"


def _routes():
    from conduit.main import app
    out = []
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if not path or not path.startswith("/api") or not methods:
            continue
        for m in sorted(methods):
            if m in ("HEAD", "OPTIONS"):
                continue
            out.append((m, path))
    return sorted(set(out))


async def test_no_endpoint_is_unauthenticated_by_accident(client):
    for method, path in _routes():
        if path in PUBLIC or "{" in path:
            continue
        resp = await client.request(method, path.replace("/api", "/api"))
        assert resp.status_code in (401, 403), f"{method} {path} -> {resp.status_code}"


def test_contract_snapshot_matches():
    current = _routes()
    if not SNAP.exists():
        SNAP.write_text(json.dumps(current, indent=2))
        pytest.skip("snapshot created; re-run to enforce")
    saved = json.loads(SNAP.read_text())
    assert [tuple(x) for x in saved] == current, (
        "API surface changed. If intentional, delete "
        f"{SNAP} and re-run to regenerate.")


async def test_secret_hash_never_serialized(client, make_account, login):
    await make_account("supervisor", "sup1", "pw-123456")
    await make_account("supervisor", "sup2", "pw-123456")
    await login("sup1", "pw-123456")
    bodies = []
    bodies.append((await client.get("/api/auth/me")).text)
    bodies.append((await client.get("/api/supervisor/accounts")).text)
    c = await client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": "g9", "display_name": "G",
        "password": "pw-123456"})
    bodies.append(c.text)
    for b in bodies:
        assert "secret_hash" not in b


async def test_jwt_tamper_and_alg_none_rejected(client, make_account, login):
    import jwt
    await make_account("guest", "g1", "pw-123456")
    await login("g1", "pw-123456")
    # tampered secret
    bad = jwt.encode({"sub": "x", "role": "supervisor"}, "not-the-secret",
                     algorithm="HS256")
    client.cookies.set("conduit_session", bad)
    assert (await client.get("/api/auth/me")).status_code == 401
    # alg none
    none_tok = jwt.encode({"sub": "x", "role": "guest"}, key=None,
                          algorithm="none")
    client.cookies.set("conduit_session", none_tok)
    assert (await client.get("/api/auth/me")).status_code == 401
```

- [ ] **Step 3: Run it, expect fail then snapshot-skip**

Run: `.venv/bin/python -m pytest tests/api/test_security_guards.py -q`
Expected: first run creates the snapshot (one skip), others pass.

- [ ] **Step 4: Re-run to enforce the snapshot**

Run: `.venv/bin/python -m pytest tests/api/test_security_guards.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add conduit/core/middleware.py tests/api/test_security_guards.py tests/api/contract_snapshot.json
git commit -m "test(guards): auth-coverage, contract snapshot, no-leak, jwt integrity"
```

### Task 14: Seed script + its test

**Files:**
- Create: `backend/conduit/seed.py`
- Test: `backend/tests/test_seed.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_seed.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_seed_is_idempotent_and_creates_supervisor(db, monkeypatch):
    from conduit import seed
    from conduit.public.dal import accounts as dal

    await seed.run(db, username="boss", password="pw-123456")
    await db.commit()
    await seed.run(db, username="boss", password="pw-123456")  # idempotent
    await db.commit()

    sups = await dal.list_accounts(db, role="supervisor")
    assert [s.username for s in sups] == ["boss"]


async def test_seed_missing_env_fails_fast(db):
    from conduit import seed
    with pytest.raises(SystemExit):
        await seed.run(db, username="", password="")
```

- [ ] **Step 2: Run it, expect fail**

Run: `.venv/bin/python -m pytest tests/test_seed.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `conduit/seed.py`:

```python
"""Idempotent bootstrap-supervisor seed: python -m conduit.seed.
Fail-fast on missing creds (never a silent no-op)."""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.config import get_settings
from conduit.public.dal import accounts as dal
from conduit.shared.db import SessionLocal
from conduit.supervisor.services import accounts as svc


async def run(s: AsyncSession, *, username: str, password: str) -> None:
    if not username or not password:
        print("seed: CONDUIT_SEED_SUPERVISOR_USERNAME/PASSWORD required",
              file=sys.stderr)
        raise SystemExit(2)
    if await dal.get_by_username(s, username) is not None:
        print(f"seed: supervisor '{username}' already exists; nothing to do")
        return
    await svc.create_account(s, role="supervisor", username=username,
                             display_name=username, password=password)
    print(f"seed: created supervisor '{username}'")


async def _main() -> None:
    st = get_settings()
    async with SessionLocal() as s:
        await run(s, username=st.seed_supervisor_username,
                  password=st.seed_supervisor_password)
        await s.commit()


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run it, expect pass**

Run: `.venv/bin/python -m pytest tests/test_seed.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add conduit/seed.py tests/test_seed.py
git commit -m "feat(seed): idempotent bootstrap supervisor (fail-fast)"
```

### Task 15: Full backend suite green + coverage gate

**Files:**
- Modify: `backend/pyproject.toml` (coverage fail-under)
- Modify: `docs/archi/code-structure.md` (one-line DAL note)

- [ ] **Step 1: Add the coverage gate scoped to auth modules**

In `pyproject.toml` `[tool.pytest.ini_options].addopts`, set:

```toml
addopts = "-ra --strict-markers --cov=conduit.public --cov=conduit.supervisor --cov=conduit.core --cov=conduit.shared.models --cov-fail-under=90 --cov-report=term-missing"
```

- [ ] **Step 2: Add the code-structure note**

In `docs/archi/code-structure.md`, under "Deltas", add one bullet:

```
- **Account persistence is owned by `public/dal/accounts.py`** and imported by
  `supervisor` services (one-directional public←supervisor) — single source of
  truth for the one IDENTITY table; no DAL duplicated across slices.
```

- [ ] **Step 3: Run the entire suite with the gate**

Run: `.venv/bin/python -m pytest -q`
Expected: ALL PASS; coverage ≥ 90% on the scoped modules. If a branch is uncovered, add the missing focused test before proceeding (the gate is the comfort mechanism).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml docs/archi/code-structure.md
git commit -m "test: coverage gate on auth modules + code-structure note"
```

---

# PHASE 2 — Frontend

> All commands run from `/workspace/Conduit-auth-slice/frontend`.

### Task 16: Install deps + shadcn components

**Files:** `frontend/package.json` (via CLI)

- [ ] **Step 1: Install npm deps**

```bash
cd /workspace/Conduit-auth-slice/frontend
npm install
npm install react-hook-form zod @hookform/resolvers sonner
```

- [ ] **Step 2: Add shadcn components (radix-nova style, deterministic)**

```bash
npx shadcn@latest add card form table dialog alert-dialog sonner badge select alert tabs --yes
```

Expected: files created under `src/components/ui/`. Use them as generated except where a later task specifies an edit.

- [ ] **Step 3: Verify build still typechecks**

```bash
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add package.json package-lock.json src/components/ui components.json
git commit -m "chore(ui): add shadcn card/form/table/dialog/etc + form deps"
```

### Task 17: Token cleanup — pure monochrome

**Files:** Modify `frontend/src/index.css`

- [ ] **Step 1: Remove the stray chromatic dark sidebar token**

In `src/index.css`, in the `.dark` block, change:

```
    --sidebar-primary: oklch(0.488 0.243 264.376);
```

to:

```
    --sidebar-primary: oklch(0.922 0 0);
```

(matches the monochrome `--primary` in `.dark`; status carries meaning via fill/weight, not hue — `destructive` stays).

- [ ] **Step 2: Visually confirm dev server renders**

```bash
npm run dev
```

Open the app; the dark sidebar active item is now neutral. Stop the dev server.

- [ ] **Step 3: Commit**

```bash
git add src/index.css
git commit -m "style: pure-monochrome (drop stray dark sidebar indigo)"
```

### Task 18: Shared primitives

**Files:** Create the six primitives.

- [ ] **Step 1: `page-header.tsx`**

Create `src/components/layout/page-header.tsx`:

```tsx
import type { ReactNode } from "react"

export function PageHeader({
  title, description, actions,
}: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 pb-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-1">
        <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="text-muted-foreground text-sm">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  )
}
```

- [ ] **Step 2: `empty-state.tsx` and `error-state.tsx`**

Create `src/components/common/empty-state.tsx`:

```tsx
import type { ReactNode } from "react"

export function EmptyState({
  title, hint, action,
}: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
      {action}
    </div>
  )
}
```

Create `src/components/common/error-state.tsx`:

```tsx
import { Button } from "@/components/ui/button"

export function ErrorState({
  title = "Something went wrong", onRetry,
}: { title?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
      )}
    </div>
  )
}
```

- [ ] **Step 3: `status-badge.tsx` + `role-badge.tsx`**

Create `src/components/common/status-badge.tsx`:

```tsx
import { Badge } from "@/components/ui/badge"

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={status === "active" ? "default" : "outline"}>
      {status}
    </Badge>
  )
}
```

Create `src/components/common/role-badge.tsx`:

```tsx
import { Badge } from "@/components/ui/badge"

export function RoleBadge({ role }: { role: string }) {
  return <Badge variant="secondary">{role.replace("_", " ")}</Badge>
}
```

- [ ] **Step 4: `confirm.tsx`**

Create `src/components/common/confirm.tsx`:

```tsx
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

export function Confirm({
  open, onOpenChange, title, description, confirmLabel = "Confirm", onConfirm,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description?: string
  confirmLabel?: string
  onConfirm: () => void
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description && (
            <AlertDialogDescription>{description}</AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
```

- [ ] **Step 5: `data-table-shell.tsx`**

Create `src/components/common/data-table-shell.tsx`:

```tsx
import type { ReactNode } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"

type State = "loading" | "error" | "empty" | "ready"

export function DataTableShell({
  state, toolbar, table, cards, onRetry, emptyTitle, emptyHint,
}: {
  state: State
  toolbar?: ReactNode
  table: ReactNode   // rendered >= md
  cards: ReactNode   // rendered < md
  onRetry?: () => void
  emptyTitle: string
  emptyHint?: string
}) {
  return (
    <div className="space-y-4">
      {toolbar && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          {toolbar}
        </div>
      )}
      {state === "loading" && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      )}
      {state === "error" && <ErrorState onRetry={onRetry} />}
      {state === "empty" && (
        <EmptyState title={emptyTitle} hint={emptyHint} />
      )}
      {state === "ready" && (
        <>
          <div className="hidden md:block">{table}</div>
          <div className="space-y-2 md:hidden">{cards}</div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 6: Typecheck + commit**

```bash
npm run build
git add src/components/layout/page-header.tsx src/components/common
git commit -m "feat(ui): shared primitives (header/empty/error/badges/confirm/table-shell)"
```

### Task 19: Real auth provider + api-client 401 + boot splash

**Files:**
- Modify: `src/auth/use-auth.ts`, `src/auth/auth-provider.tsx`, `src/lib/api-client.ts`
- Create: `src/components/app-boot-splash.tsx`
- Modify: `src/main.tsx`

- [ ] **Step 1: Extend the auth contract**

In `src/auth/use-auth.ts`, change `AuthState` to add `loading` and
`refreshUser`, and drop `email` from `User` (use `username`):

```ts
export type User = { id: string; name: string; username: string; role: Role }

export type AuthState = {
  user: User | null
  isAuthenticated: boolean
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
}
```

- [ ] **Step 2: Centralized 401 in api-client**

In `src/lib/api-client.ts`, add an unauthorized hook and fire it on 401:

```ts
let onUnauthorized: (() => void) | null = null
export function setOnUnauthorized(fn: () => void) { onUnauthorized = fn }
```

In `request`, immediately after `if (!res.ok)` and before throwing:

```ts
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized) onUnauthorized()
    throw new ApiError(res.status, await res.text())
  }
```

- [ ] **Step 3: Real AuthProvider**

Replace `src/auth/auth-provider.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from "react"
import { api, setOnUnauthorized } from "@/lib/api-client"
import { AuthContext, type User } from "@/auth/use-auth"

type Me = { id: string; role: User["role"]; username: string; display_name: string }
const toUser = (m: Me): User =>
  ({ id: m.id, role: m.role, username: m.username, name: m.display_name })

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    try {
      setUser(toUser(await api.get<Me>("/auth/me")))
    } catch {
      setUser(null)
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const m = await api.post<Me>("/auth/login", { username, password })
    setUser(toUser(m))
  }, [])

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout", {}) } finally { setUser(null) }
  }, [])

  useEffect(() => {
    setOnUnauthorized(() => setUser(null))
    refreshUser().finally(() => setLoading(false))
  }, [refreshUser])

  const value = useMemo(
    () => ({ user, isAuthenticated: user !== null, loading,
             login, logout, refreshUser }),
    [user, loading, login, logout, refreshUser])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
```

- [ ] **Step 4: Boot splash gating**

Create `src/components/app-boot-splash.tsx`:

```tsx
import { useAuth } from "@/auth/use-auth"

export function AppBootSplash({ children }: { children: React.ReactNode }) {
  const { loading } = useAuth()
  if (loading)
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-muted-foreground animate-pulse text-sm">
          Conduit
        </span>
      </div>
    )
  return <>{children}</>
}
```

In `src/main.tsx`, wrap the router subtree: place `<AppBootSplash>` inside
`<AuthProvider>` and around `<App/>` (so the splash shows while `/auth/me`
resolves, before any route renders).

- [ ] **Step 5: Typecheck + commit**

```bash
npm run build
git add src/auth/use-auth.ts src/auth/auth-provider.tsx src/lib/api-client.ts src/components/app-boot-splash.tsx src/main.tsx
git commit -m "feat(auth): real cookie-session provider + 401 logout + boot splash"
```

### Task 20: Login page

**Files:** Modify `src/auth/login-form.tsx`, `src/auth/login-page.tsx`

- [ ] **Step 1: Replace `login-form.tsx`**

```tsx
import { useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert } from "@/components/ui/alert"
import { useAuth } from "@/auth/use-auth"
import { roleHome } from "@/lib/role-routing"

const schema = z.object({ username: z.string().min(1), password: z.string().min(1) })
type Form = z.infer<typeof schema>

export function LoginForm() {
  const { login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation() as { state?: { from?: { pathname: string } } }
  const [err, setErr] = useState<string | null>(null)
  const { register, handleSubmit, formState: { isSubmitting } } =
    useForm<Form>({ resolver: zodResolver(schema) })

  async function onSubmit(v: Form) {
    setErr(null)
    try {
      await login(v.username, v.password)
      const me = await (await fetch("")).text  // placeholder removed below
      nav(loc.state?.from?.pathname ?? "/", { replace: true })
    } catch {
      setErr("Incorrect username or password")
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {err && (
        <Alert variant="destructive" className="text-sm">{err}</Alert>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="username">Username</Label>
        <Input id="username" autoFocus {...register("username")} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="password">Password</Label>
        <Input id="password" type="password" {...register("password")} />
      </div>
      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
      <p className="text-muted-foreground text-center text-xs">
        Accounts are created by your administrator.
      </p>
    </form>
  )
}
```

> Fix the redirect line: replace the two lines in `onSubmit` after
> `await login(...)` with just:
> `nav(roleHome((await import("@/auth/use-auth")) && (loc.state?.from?.pathname ? loc.state.from.pathname : "/")) as string, { replace: true })`
> — simpler: use `nav("/", { replace: true })` and let the role router send
> them onward. Final `onSubmit` body:
> ```ts
> setErr(null)
> try { await login(v.username, v.password); nav("/", { replace: true }) }
> catch { setErr("Incorrect username or password") }
> ```

- [ ] **Step 2: Replace `login-page.tsx`**

```tsx
import { Card } from "@/components/ui/card"
import { LoginForm } from "@/auth/login-form"

export function LoginPage() {
  return (
    <div className="bg-background flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-[380px] p-6">
        <div className="mb-6 text-center">
          <div className="text-lg font-semibold tracking-tight">Conduit</div>
        </div>
        <LoginForm />
      </Card>
    </div>
  )
}
```

- [ ] **Step 3: Typecheck**

```bash
npm run build
```

Expected: build succeeds (ensure the `onSubmit` final body from Step 1's fix is applied — no stray `fetch`).

- [ ] **Step 4: Commit**

```bash
git add src/auth/login-form.tsx src/auth/login-page.tsx
git commit -m "feat(login): tight monochrome cookie-session login"
```

### Task 21: Account hooks + shared account dialog

**Files:**
- Create: `src/shell/supervisor/hooks/use-accounts.ts`, `src/auth/use-update-self.ts`, `src/components/common/account-form-dialog.tsx`

- [ ] **Step 1: `use-accounts.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

export type Account = {
  id: string; role: string; username: string
  display_name: string; status: string; created_at: string
}

export function useAccounts(role?: string, status?: string) {
  const qs = new URLSearchParams()
  if (role) qs.set("role", role)
  if (status) qs.set("status", status)
  return useQuery({
    queryKey: ["accounts", role ?? null, status ?? null],
    queryFn: () => api.get<Account[]>(`/supervisor/accounts?${qs}`),
  })
}

export function useCreateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (b: { role: string; username: string;
      display_name: string; password: string }) =>
      api.post<Account>("/supervisor/accounts", b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  })
}

export function useUpdateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...b }: { id: string; display_name?: string;
      status?: string; password?: string }) =>
      api.patch<Account>(`/supervisor/accounts/${id}`, b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  })
}
```

- [ ] **Step 2: `use-update-self.ts`**

```ts
import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { useAuth } from "@/auth/use-auth"

export function useUpdateSelf() {
  const { refreshUser } = useAuth()
  return useMutation({
    mutationFn: (b: { display_name?: string; current_password?: string;
      new_password?: string }) => api.patch("/auth/me", b),
    onSuccess: () => refreshUser(),
  })
}
```

- [ ] **Step 3: `account-form-dialog.tsx`** (shared create dialog)

```tsx
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { useCreateAccount } from "@/shell/supervisor/hooks/use-accounts"

const schema = z.object({
  username: z.string().min(1),
  display_name: z.string().min(1),
  password: z.string().min(6),
})
type Form = z.infer<typeof schema>

export function AccountFormDialog({ role, label }: { role: string; label: string }) {
  const [open, setOpen] = useState(false)
  const create = useCreateAccount()
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<Form>({ resolver: zodResolver(schema) })

  async function onSubmit(v: Form) {
    try {
      await create.mutateAsync({ role, ...v })
      toast.success(`${label} created`)
      reset(); setOpen(false)
    } catch (e: any) {
      toast.error(e?.status === 409 ? "Username already exists"
        : "Could not create account")
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm">Add {label}</Button></DialogTrigger>
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader><DialogTitle>Add {label}</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          {(["username", "display_name", "password"] as const).map((f) => (
            <div key={f} className="space-y-1.5">
              <Label htmlFor={f}>{f.replace("_", " ")}</Label>
              <Input id={f} type={f === "password" ? "password" : "text"}
                     {...register(f)} />
              {errors[f] && (
                <p className="text-destructive text-xs">{errors[f]?.message}</p>
              )}
            </div>
          ))}
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Adding…" : `Add ${label}`}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 4: Typecheck + commit**

```bash
npm run build
git add src/shell/supervisor/hooks/use-accounts.ts src/auth/use-update-self.ts src/components/common/account-form-dialog.tsx
git commit -m "feat(hooks): use-accounts + use-update-self + account dialog"
```

### Task 22: Manage Servicers / Guests pages (one component, role-swapped)

**Files:**
- Create: `src/shell/supervisor/pages/manage-accounts.tsx`, `manage-servicers.tsx`, `manage-guests.tsx`

- [ ] **Step 1: Shared `manage-accounts.tsx`**

```tsx
import { useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { MoreHorizontalIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { StatusBadge } from "@/components/common/status-badge"
import { Confirm } from "@/components/common/confirm"
import { AccountFormDialog } from "@/components/common/account-form-dialog"
import {
  useAccounts, useUpdateAccount, type Account,
} from "@/shell/supervisor/hooks/use-accounts"

export function ManageAccounts({ role, label }: { role: string; label: string }) {
  const q = useAccounts(role)
  const upd = useUpdateAccount()
  const [confirm, setConfirm] = useState<Account | null>(null)

  const state = q.isLoading ? "loading" : q.isError ? "error"
    : (q.data?.length ?? 0) === 0 ? "empty" : "ready"

  async function toggle(a: Account) {
    const next = a.status === "active" ? "disabled" : "active"
    try {
      await upd.mutateAsync({ id: a.id, status: next })
      toast.success(`${a.display_name} ${next}`)
    } catch (e: any) {
      toast.error(e?.status === 409
        ? "Cannot disable the last supervisor or yourself"
        : "Update failed")
    }
  }

  const rows = (a: Account) => (
    <DropdownMenu key={a.id}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 sm:size-9">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setConfirm(a)}>
          {a.status === "active" ? "Disable" : "Enable"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div>
      <PageHeader
        title={`${label}s`}
        description={`${q.data?.length ?? 0} account(s)`}
        actions={<AccountFormDialog role={role} label={label} />}
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle={`No ${label.toLowerCase()}s yet`}
        emptyHint={`Add the first ${label.toLowerCase()}.`}
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead><TableHead>Username</TableHead>
                <TableHead>Status</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data?.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">{a.display_name}</TableCell>
                  <TableCell className="text-muted-foreground">{a.username}</TableCell>
                  <TableCell><StatusBadge status={a.status} /></TableCell>
                  <TableCell className="text-right">{rows(a)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={q.data?.map((a) => (
          <div key={a.id}
               className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <div className="text-sm font-medium">{a.display_name}</div>
              <div className="text-muted-foreground text-xs">{a.username}</div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={a.status} />{rows(a)}
            </div>
          </div>
        ))}
      />
      <Confirm
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm?.status === "active" ? "Disable account?" : "Enable account?"}
        description={confirm?.display_name}
        confirmLabel={confirm?.status === "active" ? "Disable" : "Enable"}
        onConfirm={() => { if (confirm) toggle(confirm); setConfirm(null) }}
      />
    </div>
  )
}
```

- [ ] **Step 2: Role-bound wrappers**

Create `src/shell/supervisor/pages/manage-servicers.tsx`:

```tsx
import { ManageAccounts } from "@/shell/supervisor/pages/manage-accounts"
export function ManageServicers() {
  return <ManageAccounts role="servicer" label="Servicer" />
}
```

Create `src/shell/supervisor/pages/manage-guests.tsx`:

```tsx
import { ManageAccounts } from "@/shell/supervisor/pages/manage-accounts"
export function ManageGuests() {
  return <ManageAccounts role="guest" label="Guest" />
}
```

- [ ] **Step 3: Typecheck + commit**

```bash
npm run build
git add src/shell/supervisor/pages
git commit -m "feat(supervisor): manage servicers/guests (one component, role-swapped)"
```

### Task 23: Settings pages (all portals) + nav-user entry + routes

**Files:**
- Create: `src/components/common/settings-view.tsx`, `src/shell/supervisor/pages/settings.tsx`, `src/shell/guest/settings.tsx`, `src/shell/servicer/settings.tsx`
- Modify: `src/components/layout/nav-user.tsx`, `src/shell/supervisor/nav.tsx`, `src/App.tsx`

- [ ] **Step 1: Shared `settings-view.tsx` (Profile + Password, optional Team)**

```tsx
import type { ReactNode } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { useAuth } from "@/auth/use-auth"
import { useUpdateSelf } from "@/auth/use-update-self"

const pwSchema = z.object({
  current_password: z.string().min(1),
  new_password: z.string().min(6),
}).refine((d) => d.current_password !== d.new_password, {
  message: "New password must differ", path: ["new_password"],
})

export function SettingsView({ team }: { team?: ReactNode }) {
  const { user } = useAuth()
  const save = useUpdateSelf()
  const name = useForm<{ display_name: string }>({
    defaultValues: { display_name: user?.name ?? "" },
  })
  const pw = useForm<z.infer<typeof pwSchema>>({ resolver: zodResolver(pwSchema) })

  return (
    <div>
      <PageHeader title="Settings" />
      <Tabs defaultValue="profile" className="max-w-2xl">
        <TabsList className="overflow-x-auto">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="password">Password</TabsTrigger>
          {team && <TabsTrigger value="team">Team</TabsTrigger>}
        </TabsList>

        <TabsContent value="profile" className="space-y-3 pt-4">
          <form
            onSubmit={name.handleSubmit(async (v) => {
              try { await save.mutateAsync(v); toast.success("Profile updated") }
              catch { toast.error("Update failed") }
            })}
            className="space-y-3">
            <div className="space-y-1.5">
              <Label>Display name</Label>
              <Input {...name.register("display_name", { required: true })} />
            </div>
            <div className="space-y-1.5">
              <Label>Username</Label>
              <Input value={user?.username ?? ""} disabled />
            </div>
            <Button type="submit" disabled={name.formState.isSubmitting}>
              Save
            </Button>
          </form>
        </TabsContent>

        <TabsContent value="password" className="space-y-3 pt-4">
          <form
            onSubmit={pw.handleSubmit(async (v) => {
              try {
                await save.mutateAsync(v); pw.reset()
                toast.success("Password changed")
              } catch { toast.error("Current password incorrect") }
            })}
            className="space-y-3">
            <div className="space-y-1.5">
              <Label>Current password</Label>
              <Input type="password" {...pw.register("current_password")} />
            </div>
            <div className="space-y-1.5">
              <Label>New password</Label>
              <Input type="password" {...pw.register("new_password")} />
              {pw.formState.errors.new_password && (
                <p className="text-destructive text-xs">
                  {pw.formState.errors.new_password.message}
                </p>
              )}
            </div>
            <Button type="submit" disabled={pw.formState.isSubmitting}>
              Change password
            </Button>
          </form>
        </TabsContent>

        {team && (
          <TabsContent value="team" className="pt-4">{team}</TabsContent>
        )}
      </Tabs>
    </div>
  )
}
```

- [ ] **Step 2: Per-portal settings pages**

`src/shell/guest/settings.tsx`:

```tsx
import { SettingsView } from "@/components/common/settings-view"
export function GuestSettings() { return <SettingsView /> }
```

`src/shell/servicer/settings.tsx`:

```tsx
import { SettingsView } from "@/components/common/settings-view"
export function ServicerSettings() { return <SettingsView /> }
```

`src/shell/supervisor/pages/settings.tsx` (adds the Team tab = supervisor-portal users):

```tsx
import { SettingsView } from "@/components/common/settings-view"
import { ManageAccounts } from "@/shell/supervisor/pages/manage-accounts"

export function SupervisorSettings() {
  return (
    <SettingsView team={<ManageAccounts role="supervisor" label="Supervisor" />} />
  )
}
```

- [ ] **Step 3: nav-user Settings item**

In `src/components/layout/nav-user.tsx`, import `Link` from
`react-router-dom`, `SettingsIcon` from `lucide-react`, and add — directly
above the `DropdownMenuItem onClick={logout}` — and adjust `logout` to be
awaited:

```tsx
            <DropdownMenuItem asChild>
              <Link to="settings"><SettingsIcon />Settings</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => { void logout() }}>
              <LogOutIcon />
              Log out
            </DropdownMenuItem>
```

(Relative `to="settings"` resolves under the current portal route.)

- [ ] **Step 4: Routes + nav**

In `src/shell/supervisor/nav.tsx`, add to `items` after "Guest Provisioning":

```tsx
    { title: "Settings", url: "/supervisor/settings", icon: <Settings2Icon /> },
```

In `src/App.tsx`, add child routes (import the page components at the top):

- under `/guest`: `<Route path="settings" element={<GuestSettings />} />`
- under `/servicer`: `<Route path="settings" element={<ServicerSettings />} />`
- under `/supervisor`, replace the catch-all area with explicit routes:
  `<Route path="settings" element={<SupervisorSettings />} />`,
  `<Route path="accounts/servicers" element={<ManageServicers />} />`,
  `<Route path="accounts/guests" element={<ManageGuests />} />`
  (keep the existing `index` and a final `<Route path="*" element={<SupervisorHome />} />`).

Add nav items for the two manage pages in `supervisor/nav.tsx` under a
"Provisioning" grouping or as top-level items:

```tsx
    { title: "Servicers", url: "/supervisor/accounts/servicers", icon: <UsersIcon /> },
    { title: "Guests", url: "/supervisor/accounts/guests", icon: <UsersIcon /> },
```

- [ ] **Step 5: Typecheck + commit**

```bash
npm run build
git add src/components/common/settings-view.tsx src/shell/guest/settings.tsx src/shell/servicer/settings.tsx src/shell/supervisor/pages/settings.tsx src/components/layout/nav-user.tsx src/shell/supervisor/nav.tsx src/App.tsx
git commit -m "feat(settings): per-portal settings + team tab + nav/routes"
```

### Task 24: Retrofit placeholder shells + mount Toaster

**Files:** Modify `src/shell/supervisor/index.tsx`, `src/shell/guest/index.tsx`, `src/shell/servicer/index.tsx`, `src/main.tsx`

- [ ] **Step 1: Mount the Toaster once**

In `src/main.tsx`, add `import { Toaster } from "@/components/ui/sonner"` and
render `<Toaster />` once inside the provider tree (sibling of `<App/>`).

- [ ] **Step 2: Retrofit the three placeholder shells to `PageHeader`**

In each of `src/shell/{supervisor/index,guest/index,servicer/index}.tsx`,
replace the hand-rolled `<h1 className="text-xl font-semibold">…</h1>` with
`<PageHeader title="…"/>` (import it) and replace ad-hoc placeholder cards
with `<EmptyState title="…" hint="…"/>`. Keep existing data hooks
(`useDecisionQueue` etc.) intact.

- [ ] **Step 3: Typecheck + commit**

```bash
npm run build
git add src/main.tsx src/shell/supervisor/index.tsx src/shell/guest/index.tsx src/shell/servicer/index.tsx
git commit -m "refactor(ui): retrofit shells to shared primitives + mount Toaster"
```

---

# PHASE 3 — Integration, verification, PR

### Task 25: Backend suite + frontend build, both green

- [ ] **Step 1: Full backend suite + coverage gate**

```bash
cd /workspace/Conduit-auth-slice/backend
.venv/bin/python -m pytest -q
```

Expected: ALL PASS, coverage ≥ 90% on the scoped modules, contract snapshot enforced, leak sentinel quiet.

- [ ] **Step 2: Frontend production build**

```bash
cd /workspace/Conduit-auth-slice/frontend
npm run build
```

Expected: typecheck + build succeed.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Start backend (`.venv/bin/python -m uvicorn apps.api_main:app --port 8000`),
seed (`CONDUIT_SEED_SUPERVISOR_USERNAME=boss CONDUIT_SEED_SUPERVISOR_PASSWORD=pw-123456 .venv/bin/python -m conduit.seed`),
`npm run dev`, log in as `boss` → lands on `/supervisor`; create a servicer;
log out; log in as the servicer → lands on `/servicer`. Stop both servers.

### Task 26: Push branch + open PR

- [ ] **Step 1: Confirm clean tree on the feature branch**

```bash
cd /workspace/Conduit-auth-slice
git status --short   # expect empty
git log --oneline auth-slice-design..HEAD   # the slice commits
```

- [ ] **Step 2: Push the branch**

```bash
git push -u origin feat/auth-slice
```

- [ ] **Step 3: Open the PR**

```bash
gh pr create --base main --head feat/auth-slice \
  --title "Auth slice: account model + cookie-session + provisioning" \
  --body "$(cat <<'EOF'
First buildable vertical. Implements the approved spec
(docs/superpowers/specs/2026-05-16-auth-slice-design.md):

- `account` model + first Alembic migration (D29 disable-not-delete; Q1 unified)
- bcrypt/passlib; httpOnly cookie session; ConflictError(409)
- DAL (public-owned) / services / API: login, logout, me, patch-me,
  supervisor account CRUD (no delete)
- idempotent bootstrap-supervisor seed
- regression-proof test bench: throwaway DB, model-delete teardown,
  auth-coverage + contract-snapshot + no-leak + jwt-integrity guards,
  coverage gate
- frontend: real cookie-session provider, boot splash, monochrome cleanup,
  shared primitives, login, manage servicers/guests, per-portal settings

Test bench requires a Postgres server (CONDUIT_TEST_ADMIN_URL).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed. Report it to the user.

- [ ] **Step 4: Report**

Surface the PR URL and the final `pytest` summary to the user.

---

## Self-review notes (author checklist applied)

- **Spec coverage:** model/migration (T4–5), session/security (T1,3,6), errors
  (T2), DAL (T7), services (T8–9), API (T11–12), seed (T14), structural guards
  + CORS (T13), coverage gate (T15), hooks (T19,21), components/primitives
  (T18,22–24), responsive (data-table-shell card/table split T18, responsive
  Dialog T21, single-column forms T20/23), async/skeleton (T18 shell, boot
  splash T19), worktree/venv/PR (T0,26). Every spec §3 ledger row maps to a task.
- **Placeholder scan:** the only risk was the login `onSubmit` stray `fetch`;
  Task 20 Step 1 includes the explicit corrected final body — apply it.
- **Type consistency:** `AuthUser`(be)/`User`(fe), `Account` (fe hook) and
  `AccountOut` (be) field names align; `current_actor`, `require_roles`,
  `db_session`, `issue_token`, `hash_password`/`verify_password`,
  `set/clear_session_cookie`, `svc.create_account`/`update_account`/
  `authenticate`/`current_account`/`update_self`, `useAccounts`/
  `useCreateAccount`/`useUpdateAccount`/`useUpdateSelf` are referenced
  consistently across tasks.
