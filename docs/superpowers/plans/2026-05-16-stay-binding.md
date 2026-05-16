# Stay / Binding Slice ("Check-in & Relocation") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Section/Room/Stay binding so a supervisor checks a guest in and the guest's session resolves ambient `{room, section, stay}`, with a supervisor-triggered mid-stay relocation that re-binds it — fully relational, append-only-audited, regression-proof.

**Architecture:** Stacks on the auth slice. New relational entities in `shared/models/` (the only DB-touching code); supervisor portal owns binding CRUD + event writes (`supervisor/dal` → `supervisor/services` → `supervisor/api`); the `public` auth front door gains one read (`public/dal/bindings.py`) and an extended `/auth/me` that resolves ambient context per request. No cross-portal imports. No jsonb. No DELETE.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, Postgres, pytest + httpx ASGITransport, React 19 + TanStack Query + shadcn (radix-nova/neutral/Geist), Vite.

**Spec:** `docs/superpowers/specs/2026-05-16-stay-binding-design.md` holds the rationale and decision ledger. This plan is build steps only.

---

## Execution prerequisites (read first)

- This slice **stacks on the auth slice's branch `feat/auth-slice`**. The worktree is branched from it. PHASE 0 hard-verifies the auth prerequisites and **aborts fast** if they are not present yet — do not work around an abort, it means auth has not produced the foundation this slice builds on.
- TDD throughout: failing test → run-red → minimal impl → run-green → commit. One logical change per commit.
- Backend layering is absolute: `api → services → dal → shared/models`. Services raise domain errors (`NotFoundError` 404 / `ConflictError` 409 / validation 422), never `HTTPException`; services `flush`, the request edge commits. DAL is pure persistence (no rules, no domain errors). Only `shared/models` touches the DB.
- Where this slice must match an auth-produced convention not yet visible (the declarative `Base` import path, conftest fixture names, the `/auth/me` response model), the step gives a **deterministic discovery command** and the pattern to follow — follow the discovered convention exactly, do not invent a parallel one.

## File structure (decomposition locked here)

```
backend/conduit/shared/models/property.py        Property model
backend/conduit/shared/models/section.py          Section model
backend/conduit/shared/models/room.py             Room model
backend/conduit/shared/models/stay.py             Stay model
backend/conduit/shared/models/event.py            Event base + 3 detail models
backend/conduit/shared/models/__init__.py         (modify) register new models
backend/migrations/versions/<rev>_stay_binding.py second migration
backend/conduit/supervisor/dal/sections.py        section persistence
backend/conduit/supervisor/dal/rooms.py           room persistence
backend/conduit/supervisor/dal/stays.py           stay persistence
backend/conduit/supervisor/dal/events.py          event insert primitives
backend/conduit/public/dal/bindings.py            the one ambient read
backend/conduit/supervisor/services/sections.py   section business logic
backend/conduit/supervisor/services/rooms.py      room business logic
backend/conduit/supervisor/services/stays.py      stay business logic + guards
backend/conduit/public/services/auth.py           (modify) resolve_ambient
backend/conduit/supervisor/schemas/binding.py     supervisor request/response
backend/conduit/public/schemas/__init__.py        (modify) AuthUser ambient
backend/conduit/supervisor/api/setup.py           sections + rooms routes
backend/conduit/supervisor/api/stays.py           stays routes
backend/conduit/public/api/auth.py                (modify) /auth/me ambient
backend/conduit/seed.py or conduit/__main__ seed  (modify) ensure_property
backend/tests/binding/...                          layered tests + guards + e2e
frontend/src/components/common/combobox-field.tsx  command+popover pattern
frontend/src/components/common/date-range-field.tsx calendar+popover pattern
frontend/src/shell/supervisor/hooks/use-sections.ts
frontend/src/shell/supervisor/hooks/use-rooms.ts
frontend/src/shell/supervisor/hooks/use-stays.ts
frontend/src/shell/supervisor/hooks/invalidate-binding.ts
frontend/src/shell/supervisor/pages/sections.tsx
frontend/src/shell/supervisor/pages/provisioning.tsx
frontend/src/shell/supervisor/nav.tsx              (modify) routes
frontend/src/App.tsx                               (modify) routes
```

---

# PHASE 0 — Worktree, env, preflight

### Task 0a: Create the execution worktree off the auth branch

**Files:** none (git/setup)

- [ ] **Step 1: Commit this plan on the design branch**

```bash
cd /workspace/Conduit
git add docs/superpowers/plans/2026-05-16-stay-binding.md
git commit -m "docs: stay/binding implementation plan"
```

- [ ] **Step 2: Create the worktree on a fresh feature branch off `feat/auth-slice`**

```bash
cd /workspace/Conduit
git fetch --all --quiet || true
git worktree add -b feat/stay-binding /workspace/Conduit-stay-binding feat/auth-slice
cd /workspace/Conduit-stay-binding
git branch --show-current   # expect: feat/stay-binding
```

- [ ] **Step 3: Bring this spec + plan into the worktree**

The worktree branched from `feat/auth-slice`, which does not have the stay-binding docs. Copy them in so they travel with the work:

```bash
mkdir -p /workspace/Conduit-stay-binding/docs/superpowers/specs /workspace/Conduit-stay-binding/docs/superpowers/plans
cp /workspace/Conduit/docs/superpowers/specs/2026-05-16-stay-binding-design.md /workspace/Conduit-stay-binding/docs/superpowers/specs/
cp /workspace/Conduit/docs/superpowers/plans/2026-05-16-stay-binding.md /workspace/Conduit-stay-binding/docs/superpowers/plans/
cd /workspace/Conduit-stay-binding
git add docs/superpowers
git commit -m "docs: carry stay/binding spec + plan into the worktree"
```

### Task 0b: Copy env files and seed the venv

**Files:** none (setup)

- [ ] **Step 1: Copy the .env files into the worktree**

```bash
cp /workspace/Conduit/backend/.env  /workspace/Conduit-stay-binding/backend/.env
cp /workspace/Conduit/frontend/.env /workspace/Conduit-stay-binding/frontend/.env
test -f /workspace/Conduit-stay-binding/backend/.env  && echo "backend/.env OK"
test -f /workspace/Conduit-stay-binding/frontend/.env && echo "frontend/.env OK"
```

- [ ] **Step 2: Seed the worktree venv from the existing one**

```bash
cp -a /workspace/Conduit/backend/.venv /workspace/Conduit-stay-binding/backend/.venv
```

- [ ] **Step 3: Re-link the editable install to the worktree path**

```bash
cd /workspace/Conduit-stay-binding/backend
./.venv/bin/pip install -e . --no-deps -q
./.venv/bin/python -c "import conduit, pathlib; print(pathlib.Path(conduit.__file__).resolve())"
# Expect a path under /workspace/Conduit-stay-binding/backend/
```

- [ ] **Step 4: Baseline test run (auth's scaffold + suite must already be green)**

```bash
cd /workspace/Conduit-stay-binding/backend
./.venv/bin/pytest -q
# Expect: green (this is auth's state; if red, stop — fix is not in this slice's scope)
```

### Task 0c: Auth-prerequisite preflight (fail fast, no silent degrade)

**Files:** none (verification)

- [ ] **Step 1: Verify every auth-produced prerequisite exists**

```bash
cd /workspace/Conduit-stay-binding/backend
missing=0
test -f conduit/shared/models/account.py || { echo "MISSING: account model"; missing=1; }
ls migrations/versions/*.py >/dev/null 2>&1 || { echo "MISSING: first alembic migration"; missing=1; }
grep -rq "def authenticate" conduit/public/services/auth.py 2>/dev/null || { echo "MISSING: public auth service"; missing=1; }
grep -rq "/me" conduit/public/api/auth.py 2>/dev/null || { echo "MISSING: /auth/me route"; missing=1; }
grep -rq "conduit_test" tests/conftest.py 2>/dev/null || { echo "MISSING: auth test harness (conduit_test DB)"; missing=1; }
test -f ../frontend/src/components/common/data-table-shell.tsx || test -f ../frontend/src/components/common/empty-state.tsx || { echo "MISSING: auth uniformity primitives"; missing=1; }
if [ "$missing" = "1" ]; then echo "ABORT: auth slice has not yet produced the foundation this slice stacks on. Do not work around this."; exit 1; fi
echo "Auth prerequisites present — proceed."
```

- [ ] **Step 2: Postgres preflight (the test bench needs it)**

```bash
cd /workspace/Conduit-stay-binding/backend
./.venv/bin/python - <<'PY'
import os, sys
from sqlalchemy import create_engine, text
url = os.environ.get("DATABASE_URL") or open(".env").read()
# Reuse the same admin connection the auth conftest uses to build conduit_test.
try:
    import conduit.core.config as c  # noqa
except Exception as e:
    print("config import failed:", e); sys.exit(1)
print("Postgres preflight: config import OK — conftest owns conduit_test creation.")
PY
```

- [ ] **Step 3: Discover the conventions this slice must match**

```bash
cd /workspace/Conduit-stay-binding/backend
echo "--- declarative Base import path ---"
grep -nE "Base|DeclarativeBase|registry" conduit/shared/models/account.py | head
echo "--- model registration pattern ---"
cat conduit/shared/models/__init__.py
echo "--- conftest fixtures (client, db_session, authed helpers) ---"
grep -nE "def (client|db_session|.*supervisor.*|.*guest.*)|fixture" tests/conftest.py | head -40
echo "--- /auth/me response model ---"
grep -nE "class .*(User|Me|AuthUser).*BaseModel|response_model" conduit/public/api/auth.py conduit/public/schemas/__init__.py | head
echo "--- domain error classes ---"
grep -nE "class .*(NotFound|Conflict|Validation|Domain).*Error" conduit/core/exceptions.py
```

Record the discovered: `Base` import, the `__init__.py` registration line style, the conftest fixture names for an authenticated supervisor client and a raw `db_session`, the `/auth/me` response model class + module, and the domain-error class names. **Every later task uses the discovered names, not invented ones.**

---

# PHASE 1 — Backend (TDD; ends fully green)

> All paths below are relative to `/workspace/Conduit-stay-binding/backend`. Run pytest as `./.venv/bin/pytest`.

### Task 1: `Property` model

**Files:**
- Create: `conduit/shared/models/property.py`
- Modify: `conduit/shared/models/__init__.py`
- Test: `tests/binding/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_models.py
import uuid
from conduit.shared.models.property import Property

def test_property_has_uuid_pk_and_name():
    p = Property(name="Grand Hotel")
    assert p.name == "Grand Hotel"
    # id is server/default-generated; column exists and is uuid-typed
    assert "id" in Property.__table__.columns
    assert "name" in Property.__table__.columns
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_models.py -q`
Expected: FAIL `ModuleNotFoundError: conduit.shared.models.property`

- [ ] **Step 3: Implement the model**

Use the `Base` import discovered in Task 0c Step 3 (shown here as `from conduit.shared.db import Base` — replace with the discovered path if different).

```python
# conduit/shared/models/property.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Property(Base):
    __tablename__ = "property"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 4: Register on import**

Append to `conduit/shared/models/__init__.py` following its existing registration style:

```python
from conduit.shared.models.property import Property  # noqa: F401
```

- [ ] **Step 5: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_models.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add conduit/shared/models/property.py conduit/shared/models/__init__.py tests/binding/test_models.py
git commit -m "feat(models): Property"
```

### Task 2: `Section` and `Room` models

**Files:**
- Create: `conduit/shared/models/section.py`, `conduit/shared/models/room.py`
- Modify: `conduit/shared/models/__init__.py`
- Test: `tests/binding/test_models.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/binding/test_models.py  (append)
from conduit.shared.models.section import Section
from conduit.shared.models.room import Room

def test_section_columns():
    cols = set(Section.__table__.columns.keys())
    assert {"id", "property_id", "label", "created_at", "updated_at"} <= cols

def test_room_columns_and_section_fk():
    cols = set(Room.__table__.columns.keys())
    assert {"id", "section_id", "label", "created_at", "updated_at"} <= cols
    fks = {fk.column.table.name for fk in Room.__table__.foreign_keys}
    assert "section" in fks
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_models.py -q`
Expected: FAIL `ModuleNotFoundError: conduit.shared.models.section`

- [ ] **Step 3: Implement**

```python
# conduit/shared/models/section.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Section(Base):
    __tablename__ = "section"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
```

```python
# conduit/shared/models/room.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Room(Base):
    __tablename__ = "room"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
```

Append to `conduit/shared/models/__init__.py`:

```python
from conduit.shared.models.section import Section  # noqa: F401
from conduit.shared.models.room import Room  # noqa: F401
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_models.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/shared/models/section.py conduit/shared/models/room.py conduit/shared/models/__init__.py tests/binding/test_models.py
git commit -m "feat(models): Section, Room"
```

### Task 3: `Stay` model

**Files:**
- Create: `conduit/shared/models/stay.py`
- Modify: `conduit/shared/models/__init__.py`
- Test: `tests/binding/test_models.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/binding/test_models.py  (append)
from conduit.shared.models.stay import Stay

def test_stay_columns_and_fks():
    cols = set(Stay.__table__.columns.keys())
    assert {"id", "guest_account_id", "room_id", "check_in",
            "check_out", "status", "created_at", "updated_at"} <= cols
    fk_tables = {fk.column.table.name for fk in Stay.__table__.foreign_keys}
    assert {"account", "room"} <= fk_tables

def test_stay_status_default_active():
    s = Stay()
    assert Stay.__table__.columns["status"].default.arg == "active"
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_models.py -q`
Expected: FAIL `ModuleNotFoundError: conduit.shared.models.stay`

- [ ] **Step 3: Implement**

```python
# conduit/shared/models/stay.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base


class Stay(Base):
    __tablename__ = "stay"
    __table_args__ = (
        CheckConstraint("status in ('active','ended')", name="ck_stay_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    guest_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False
    )
    check_in: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    check_out: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
```

Append to `conduit/shared/models/__init__.py`:

```python
from conduit.shared.models.stay import Stay  # noqa: F401
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_models.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/shared/models/stay.py conduit/shared/models/__init__.py tests/binding/test_models.py
git commit -m "feat(models): Stay"
```

### Task 4: `Event` base + 3 detail models

**Files:**
- Create: `conduit/shared/models/event.py`
- Modify: `conduit/shared/models/__init__.py`
- Test: `tests/binding/test_models.py`

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/binding/test_models.py  (append)
from conduit.shared.models.event import (
    Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
)

def test_event_base_columns():
    cols = set(Event.__table__.columns.keys())
    assert {"id", "type", "actor_account_id", "at"} <= cols

def test_event_detail_fks():
    assert "event" in {fk.column.table.name
                        for fk in EventStayCreated.__table__.foreign_keys}
    rel_fks = {fk.column.table.name
               for fk in EventGuestRelocated.__table__.foreign_keys}
    assert {"event", "stay", "room"} <= rel_fks
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_models.py -q`
Expected: FAIL `ModuleNotFoundError: conduit.shared.models.event`

- [ ] **Step 3: Implement**

```python
# conduit/shared/models/event.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from conduit.shared.db import Base

EVENT_TYPES = ("stay_created", "stay_ended", "guest_relocated")


class Event(Base):
    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint(
            "type in ('stay_created','stay_ended','guest_relocated')",
            name="ck_event_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=True
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EventStayCreated(Base):
    __tablename__ = "event_stay_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True
    )
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False
    )


class EventStayEnded(Base):
    __tablename__ = "event_stay_ended"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True
    )
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False
    )


class EventGuestRelocated(Base):
    __tablename__ = "event_guest_relocated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True
    )
    stay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stay.id"), nullable=False
    )
    from_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False
    )
    to_room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("room.id"), nullable=False
    )
```

Append to `conduit/shared/models/__init__.py`:

```python
from conduit.shared.models.event import (  # noqa: F401
    Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
)
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_models.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/shared/models/event.py conduit/shared/models/__init__.py tests/binding/test_models.py
git commit -m "feat(models): Event base + 3 detail tables"
```

### Task 5: Second Alembic migration (stacked, incl. partial unique index)

**Files:**
- Create: `migrations/versions/<rev>_stay_binding.py`
- Test: `tests/binding/test_migration.py` (asserted via the harness in Task 6 Step 4 — generation + finalize here)

- [ ] **Step 1: Identify the current head (auth's migration)**

```bash
cd /workspace/Conduit-stay-binding/backend
./.venv/bin/alembic heads
# Record the single head revision id — it becomes this migration's down_revision.
```

- [ ] **Step 2: Autogenerate then hand-finalize**

```bash
./.venv/bin/alembic revision --autogenerate -m "stay binding"
```

Open the new file in `migrations/versions/`. Verify `down_revision` equals the head from Step 1. Ensure `upgrade()` creates, **in FK order**: `property`, `section`, `room`, `stay`, `event`, `event_stay_created`, `event_stay_ended`, `event_guest_relocated`, with the `ck_stay_status` and `ck_event_type` CHECK constraints. Then **manually add the partial unique index** at the end of `upgrade()` and drop it first in `downgrade()`:

```python
    op.create_index(
        "uq_stay_one_active_per_guest",
        "stay",
        ["guest_account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
```

```python
    # top of downgrade(), before dropping tables:
    op.drop_index("uq_stay_one_active_per_guest", table_name="stay")
```

Ensure `downgrade()` drops tables in reverse FK order.

- [ ] **Step 3: Defer the run to Task 6** (the harness builds the schema via `alembic upgrade head`; round-trip is asserted in Task 6 Step 4).

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/
git commit -m "feat(db): second migration — stay binding + partial unique index"
```

### Task 6: Extend the test harness (binding teardown, baseline, mechanism-agnostic)

**Files:**
- Create: `tests/binding/__init__.py`, `tests/binding/conftest.py`
- Modify: `pyproject.toml` (coverage scope) — only if auth's coverage config is `addopts`-based; otherwise add a `[tool.coverage]` scope note
- Test: `tests/binding/test_migration.py`

- [ ] **Step 1: Add binding teardown + baseline fixtures**

These compose with auth's session-scoped `conduit_test` DB (built via `alembic upgrade head`, which now includes Task 5). Use the conftest fixture names discovered in Task 0c (shown as `db_session`, `client`, `supervisor_client` — replace with discovered names). Tests must be **mechanism-agnostic**: never assume rollback vs delete.

```python
# tests/binding/__init__.py
```

```python
# tests/binding/conftest.py
import pytest
from sqlalchemy import delete, select, func
from conduit.shared.models.event import (
    EventStayCreated, EventStayEnded, EventGuestRelocated, Event,
)
from conduit.shared.models.stay import Stay
from conduit.shared.models.room import Room
from conduit.shared.models.section import Section
from conduit.shared.models.property import Property

# Reverse-FK delete order. Runs in a finally so it executes on pass, fail,
# or exception — matching the auth harness's model-delete discipline. If the
# harness is later upgraded to savepoint-rollback (the recorded target), this
# becomes a no-op safety net; tests do not depend on which is active.
_DELETE_ORDER = [
    EventGuestRelocated, EventStayEnded, EventStayCreated, Event,
    Stay, Room, Section,  # Property is the seeded singleton — left intact
]


@pytest.fixture
def binding_cleanup(db_session):
    try:
        yield
    finally:
        for model in _DELETE_ORDER:
            db_session.execute(delete(model))
        db_session.commit()


@pytest.fixture
def seeded_property(db_session):
    p = db_session.execute(select(Property)).scalars().first()
    if p is None:
        p = Property(name="Test Property")
        db_session.add(p)
        db_session.commit()
    return p
```

- [ ] **Step 2: Add the leak sentinel**

```python
# tests/binding/conftest.py  (append)
@pytest.fixture(autouse=True)
def _binding_leak_sentinel(db_session, binding_cleanup):
    yield
    for model in (Stay, Room, Section, Event):
        n = db_session.execute(select(func.count()).select_from(model)).scalar()
        assert n == 0, f"LEAK: {model.__tablename__} not at baseline ({n})"
```

- [ ] **Step 3: Migration round-trip + constraint test**

```python
# tests/binding/test_migration.py
from sqlalchemy import inspect, text


def test_all_binding_tables_exist(db_session):
    names = set(inspect(db_session.get_bind()).get_table_names())
    assert {"property", "section", "room", "stay", "event",
            "event_stay_created", "event_stay_ended",
            "event_guest_relocated"} <= names


def test_partial_unique_index_present(db_session):
    rows = db_session.execute(text(
        "select indexname from pg_indexes where tablename='stay'"
    )).scalars().all()
    assert "uq_stay_one_active_per_guest" in rows


def test_stay_status_check_rejects_bad_value(db_session, seeded_property):
    with pytest.raises(Exception):
        db_session.execute(text(
            "insert into stay (id, guest_account_id, room_id, check_in, "
            "check_out, status, created_at, updated_at) values "
            "(gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), "
            "now(), now(), 'bogus', now(), now())"
        ))
        db_session.commit()
    db_session.rollback()


import pytest  # noqa: E402
```

- [ ] **Step 4: Run the model + migration tests**

Run: `./.venv/bin/pytest tests/binding/test_models.py tests/binding/test_migration.py -q`
Expected: PASS (the `conduit_test` DB now builds with the second migration)

- [ ] **Step 5: Commit**

```bash
git add tests/binding/__init__.py tests/binding/conftest.py tests/binding/test_migration.py
git commit -m "test(binding): harness extension — teardown, baseline, leak sentinel, migration round-trip"
```

### Task 7: `supervisor/dal/sections.py`

**Files:**
- Create: `conduit/supervisor/dal/sections.py`
- Test: `tests/binding/test_dal_sections.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_dal_sections.py
import pytest
from conduit.supervisor.dal import sections as dal


@pytest.fixture
def s(db_session, seeded_property):
    return dal.insert_section(db_session, seeded_property.id, "North Wing")


def test_insert_and_get(db_session, s):
    got = dal.get_section(db_session, s.id)
    assert got is not None and got.label == "North Wing"


def test_get_by_label_case_insensitive(db_session, seeded_property, s):
    got = dal.get_section_by_label(db_session, seeded_property.id, "north wing")
    assert got is not None and got.id == s.id


def test_list_with_room_counts(db_session, s):
    rows = dal.list_sections_with_room_counts(db_session)
    assert any(sec.id == s.id and cnt == 0 for sec, cnt in rows)


def test_update_label(db_session, s):
    dal.update_section(db_session, s, label="North")
    assert dal.get_section(db_session, s.id).label == "North"
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_dal_sections.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/dal/sections.py
import uuid
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from conduit.shared.models.section import Section
from conduit.shared.models.room import Room


def get_section(db: Session, section_id: uuid.UUID) -> Section | None:
    return db.get(Section, section_id)


def get_section_by_label(
    db: Session, property_id: uuid.UUID, label: str
) -> Section | None:
    return db.execute(
        select(Section).where(
            Section.property_id == property_id,
            func.lower(Section.label) == label.lower(),
        )
    ).scalars().first()


def list_sections_with_room_counts(db: Session) -> list[tuple[Section, int]]:
    rows = db.execute(
        select(Section, func.count(Room.id))
        .outerjoin(Room, Room.section_id == Section.id)
        .group_by(Section.id)
        .order_by(func.lower(Section.label))
    ).all()
    return [(sec, cnt) for sec, cnt in rows]


def insert_section(
    db: Session, property_id: uuid.UUID, label: str
) -> Section:
    sec = Section(property_id=property_id, label=label)
    db.add(sec)
    db.flush()
    return sec


def update_section(db: Session, section: Section, *, label: str) -> Section:
    section.label = label
    db.flush()
    return section
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_dal_sections.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/dal/sections.py tests/binding/test_dal_sections.py
git commit -m "feat(supervisor/dal): sections persistence"
```

### Task 8: `supervisor/dal/rooms.py`

**Files:**
- Create: `conduit/supervisor/dal/rooms.py`
- Test: `tests/binding/test_dal_rooms.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_dal_rooms.py
import pytest
from conduit.supervisor.dal import sections as sdal, rooms as dal


@pytest.fixture
def sec(db_session, seeded_property):
    return sdal.insert_section(db_session, seeded_property.id, "North")


def test_insert_get_list(db_session, sec):
    r = dal.insert_room(db_session, sec.id, "304")
    assert dal.get_room(db_session, r.id).label == "304"
    assert [x.id for x in dal.list_rooms(db_session, section_id=sec.id)] == [r.id]


def test_get_by_label_ci(db_session, sec):
    r = dal.insert_room(db_session, sec.id, "304")
    assert dal.get_room_by_label(db_session, "304").id == r.id


def test_update_label_and_reassign(db_session, seeded_property, sec):
    other = sdal.insert_section(db_session, seeded_property.id, "South")
    r = dal.insert_room(db_session, sec.id, "304")
    dal.update_room(db_session, r, label="305", section_id=other.id)
    got = dal.get_room(db_session, r.id)
    assert got.label == "305" and got.section_id == other.id
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_dal_rooms.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/dal/rooms.py
import uuid
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from conduit.shared.models.room import Room


def get_room(db: Session, room_id: uuid.UUID) -> Room | None:
    return db.get(Room, room_id)


def get_room_by_label(db: Session, label: str) -> Room | None:
    return db.execute(
        select(Room).where(func.lower(Room.label) == label.lower())
    ).scalars().first()


def list_rooms(
    db: Session, section_id: uuid.UUID | None = None
) -> list[Room]:
    stmt = select(Room).order_by(func.lower(Room.label))
    if section_id is not None:
        stmt = stmt.where(Room.section_id == section_id)
    return list(db.execute(stmt).scalars().all())


def insert_room(db: Session, section_id: uuid.UUID, label: str) -> Room:
    room = Room(section_id=section_id, label=label)
    db.add(room)
    db.flush()
    return room


def update_room(
    db: Session, room: Room, *,
    label: str | None = None, section_id: uuid.UUID | None = None,
) -> Room:
    if label is not None:
        room.label = label
    if section_id is not None:
        room.section_id = section_id
    db.flush()
    return room
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_dal_rooms.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/dal/rooms.py tests/binding/test_dal_rooms.py
git commit -m "feat(supervisor/dal): rooms persistence"
```

### Task 9: `supervisor/dal/stays.py`

**Files:**
- Create: `conduit/supervisor/dal/stays.py`
- Test: `tests/binding/test_dal_stays.py`

- [ ] **Step 1: Write the failing test**

`make_guest` creates an account via auth's real service — discover its import in Task 0c (shown as `conduit.supervisor.services.accounts.create_account`; if auth exposes a different creator, use that). Adjust the call to auth's actual signature.

```python
# tests/binding/test_dal_stays.py
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from conduit.supervisor.dal import sections as sdal, rooms as rdal, stays as dal
from conduit.shared.models.account import Account


@pytest.fixture
def room(db_session, seeded_property):
    s = sdal.insert_section(db_session, seeded_property.id, "North")
    return rdal.insert_room(db_session, s.id, "304")


@pytest.fixture
def guest(db_session):
    g = Account(role="guest", username=f"g{uuid.uuid4().hex[:8]}",
                secret_hash="x", display_name="Guest", status="active")
    db_session.add(g)
    db_session.flush()
    return g


def _now():
    return datetime.now(timezone.utc)


def test_insert_get_active(db_session, guest, room):
    st = dal.insert_stay(db_session, guest.id, room.id, _now(),
                         _now() + timedelta(days=2))
    assert dal.get_stay(db_session, st.id).id == st.id
    assert dal.get_active_stay_for_guest(db_session, guest.id).id == st.id


def test_set_room_and_status(db_session, guest, room, seeded_property):
    s2 = sdal.insert_section(db_session, seeded_property.id, "South")
    r2 = rdal.insert_room(db_session, s2.id, "511")
    st = dal.insert_stay(db_session, guest.id, room.id, _now(),
                         _now() + timedelta(days=1))
    dal.set_stay_room(db_session, st, r2.id)
    assert dal.get_stay(db_session, st.id).room_id == r2.id
    dal.set_stay_status(db_session, st, "ended")
    assert dal.get_active_stay_for_guest(db_session, guest.id) is None


def test_list_filters(db_session, guest, room):
    st = dal.insert_stay(db_session, guest.id, room.id, _now(),
                         _now() + timedelta(days=1))
    assert st.id in [x.id for x in dal.list_stays(db_session, status="active")]
    assert st.id in [x.id for x in
                      dal.list_stays(db_session, guest_id=guest.id)]
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_dal_stays.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/dal/stays.py
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from conduit.shared.models.stay import Stay


def get_stay(db: Session, stay_id: uuid.UUID) -> Stay | None:
    return db.get(Stay, stay_id)


def get_active_stay_for_guest(
    db: Session, guest_account_id: uuid.UUID
) -> Stay | None:
    return db.execute(
        select(Stay).where(
            Stay.guest_account_id == guest_account_id,
            Stay.status == "active",
        )
    ).scalars().first()


def list_stays(
    db: Session, status: str | None = None,
    guest_id: uuid.UUID | None = None,
) -> list[Stay]:
    stmt = select(Stay).order_by(Stay.created_at.desc())
    if status is not None:
        stmt = stmt.where(Stay.status == status)
    if guest_id is not None:
        stmt = stmt.where(Stay.guest_account_id == guest_id)
    return list(db.execute(stmt).scalars().all())


def insert_stay(
    db: Session, guest_account_id: uuid.UUID, room_id: uuid.UUID,
    check_in: datetime, check_out: datetime,
) -> Stay:
    st = Stay(guest_account_id=guest_account_id, room_id=room_id,
              check_in=check_in, check_out=check_out, status="active")
    db.add(st)
    db.flush()
    return st


def update_stay_fields(
    db: Session, stay: Stay, *,
    check_in: datetime | None = None, check_out: datetime | None = None,
) -> Stay:
    if check_in is not None:
        stay.check_in = check_in
    if check_out is not None:
        stay.check_out = check_out
    db.flush()
    return stay


def set_stay_room(db: Session, stay: Stay, new_room_id: uuid.UUID) -> Stay:
    stay.room_id = new_room_id
    db.flush()
    return stay


def set_stay_status(db: Session, stay: Stay, status: str) -> Stay:
    stay.status = status
    db.flush()
    return stay
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_dal_stays.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/dal/stays.py tests/binding/test_dal_stays.py
git commit -m "feat(supervisor/dal): stays persistence"
```

### Task 10: `supervisor/dal/events.py`

**Files:**
- Create: `conduit/supervisor/dal/events.py`
- Test: `tests/binding/test_dal_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_dal_events.py
import uuid
from sqlalchemy import select, func
from conduit.supervisor.dal import events as dal
from conduit.shared.models.event import (
    Event, EventStayCreated, EventGuestRelocated,
)


def test_insert_event_and_details(db_session):
    e = dal.insert_event(db_session, type="stay_created",
                          actor_account_id=None)
    dal.insert_stay_created(db_session, e.id, uuid.uuid4())
    assert db_session.get(Event, e.id).type == "stay_created"
    assert db_session.execute(
        select(func.count()).select_from(EventStayCreated)
    ).scalar() == 1


def test_insert_relocated_detail(db_session):
    e = dal.insert_event(db_session, type="guest_relocated",
                          actor_account_id=None)
    sid, fr, to = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    dal.insert_guest_relocated(db_session, e.id, sid, fr, to)
    row = db_session.execute(select(EventGuestRelocated)).scalars().one()
    assert row.from_room_id == fr and row.to_room_id == to
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_dal_events.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/dal/events.py
import uuid
from sqlalchemy.orm import Session
from conduit.shared.models.event import (
    Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
)


def insert_event(
    db: Session, *, type: str, actor_account_id: uuid.UUID | None,
) -> Event:
    e = Event(type=type, actor_account_id=actor_account_id)
    db.add(e)
    db.flush()
    return e


def insert_stay_created(
    db: Session, event_id: uuid.UUID, stay_id: uuid.UUID
) -> None:
    db.add(EventStayCreated(event_id=event_id, stay_id=stay_id))
    db.flush()


def insert_stay_ended(
    db: Session, event_id: uuid.UUID, stay_id: uuid.UUID
) -> None:
    db.add(EventStayEnded(event_id=event_id, stay_id=stay_id))
    db.flush()


def insert_guest_relocated(
    db: Session, event_id: uuid.UUID, stay_id: uuid.UUID,
    from_room_id: uuid.UUID, to_room_id: uuid.UUID,
) -> None:
    db.add(EventGuestRelocated(
        event_id=event_id, stay_id=stay_id,
        from_room_id=from_room_id, to_room_id=to_room_id,
    ))
    db.flush()
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_dal_events.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/dal/events.py tests/binding/test_dal_events.py
git commit -m "feat(supervisor/dal): event insert primitives"
```

### Task 11: `public/dal/bindings.py` — the one ambient read

**Files:**
- Create: `conduit/public/dal/bindings.py`
- Test: `tests/binding/test_dal_bindings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_dal_bindings.py
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from conduit.supervisor.dal import sections as sdal, rooms as rdal, stays as stdal
from conduit.public.dal import bindings as dal
from conduit.shared.models.account import Account


@pytest.fixture
def guest(db_session):
    g = Account(role="guest", username=f"g{uuid.uuid4().hex[:8]}",
                secret_hash="x", display_name="Guest", status="active")
    db_session.add(g); db_session.flush()
    return g


def test_returns_trio_for_active(db_session, seeded_property, guest):
    sec = sdal.insert_section(db_session, seeded_property.id, "North")
    room = rdal.insert_room(db_session, sec.id, "304")
    stdal.insert_stay(db_session, guest.id, room.id,
                      datetime.now(timezone.utc),
                      datetime.now(timezone.utc) + timedelta(days=1))
    trio = dal.get_active_binding_for_guest(db_session, guest.id)
    assert trio is not None
    stay, r, s = trio
    assert r.label == "304" and s.label == "North"


def test_none_when_no_active(db_session, guest):
    assert dal.get_active_binding_for_guest(db_session, guest.id) is None
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_dal_bindings.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# conduit/public/dal/bindings.py
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from conduit.shared.models.stay import Stay
from conduit.shared.models.room import Room
from conduit.shared.models.section import Section


def get_active_binding_for_guest(
    db: Session, guest_account_id: uuid.UUID
) -> tuple[Stay, Room, Section] | None:
    row = db.execute(
        select(Stay, Room, Section)
        .join(Room, Room.id == Stay.room_id)
        .join(Section, Section.id == Room.section_id)
        .where(
            Stay.guest_account_id == guest_account_id,
            Stay.status == "active",
        )
    ).first()
    if row is None:
        return None
    return (row[0], row[1], row[2])
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_dal_bindings.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/public/dal/bindings.py tests/binding/test_dal_bindings.py
git commit -m "feat(public/dal): ambient binding read"
```

### Task 12: `supervisor/services/sections.py`

**Files:**
- Create: `conduit/supervisor/services/sections.py`
- Test: `tests/binding/test_svc_sections.py`

Use the domain error classes discovered in Task 0c (shown as `NotFoundError`, `ConflictError` from `conduit.core.exceptions`).

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_svc_sections.py
import pytest
from conduit.supervisor.services import sections as svc
from conduit.core.exceptions import NotFoundError, ConflictError


def test_create_and_list(db_session, seeded_property):
    s = svc.create_section(db_session, seeded_property.id, "North", actor=None)
    rows = svc.list_sections(db_session)
    assert any(sec.id == s.id and cnt == 0 for sec, cnt in rows)


def test_create_duplicate_conflict(db_session, seeded_property):
    svc.create_section(db_session, seeded_property.id, "North", actor=None)
    with pytest.raises(ConflictError):
        svc.create_section(db_session, seeded_property.id, "north", actor=None)


def test_rename_missing_404(db_session):
    import uuid
    with pytest.raises(NotFoundError):
        svc.rename_section(db_session, uuid.uuid4(), "X", actor=None)
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_svc_sections.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/services/sections.py
import uuid
from sqlalchemy.orm import Session
from conduit.core.exceptions import NotFoundError, ConflictError
from conduit.supervisor.dal import sections as dal


def list_sections(db: Session):
    return dal.list_sections_with_room_counts(db)


def create_section(db: Session, property_id: uuid.UUID, label: str, *, actor):
    if dal.get_section_by_label(db, property_id, label) is not None:
        raise ConflictError("Section label already exists")
    return dal.insert_section(db, property_id, label)


def rename_section(db: Session, section_id: uuid.UUID, label: str, *, actor):
    section = dal.get_section(db, section_id)
    if section is None:
        raise NotFoundError("Section not found")
    dup = dal.get_section_by_label(db, section.property_id, label)
    if dup is not None and dup.id != section.id:
        raise ConflictError("Section label already exists")
    return dal.update_section(db, section, label=label)
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_svc_sections.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/services/sections.py tests/binding/test_svc_sections.py
git commit -m "feat(supervisor/services): sections business logic"
```

### Task 13: `supervisor/services/rooms.py`

**Files:**
- Create: `conduit/supervisor/services/rooms.py`
- Test: `tests/binding/test_svc_rooms.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_svc_rooms.py
import uuid
import pytest
from conduit.supervisor.services import sections as ssvc, rooms as svc
from conduit.core.exceptions import NotFoundError, ConflictError


@pytest.fixture
def sec(db_session, seeded_property):
    return ssvc.create_section(db_session, seeded_property.id, "North",
                               actor=None)


def test_create_list(db_session, sec):
    r = svc.create_room(db_session, "304", sec.id, actor=None)
    assert r.id in [x.id for x in svc.list_rooms(db_session, sec.id)]


def test_create_bad_section_422(db_session):
    with pytest.raises(ValueError):
        svc.create_room(db_session, "304", uuid.uuid4(), actor=None)


def test_create_dup_conflict(db_session, sec):
    svc.create_room(db_session, "304", sec.id, actor=None)
    with pytest.raises(ConflictError):
        svc.create_room(db_session, "304", sec.id, actor=None)


def test_update_missing_404(db_session):
    with pytest.raises(NotFoundError):
        svc.update_room(db_session, uuid.uuid4(), label="X", actor=None)


def test_reassign_section(db_session, seeded_property, sec):
    other = ssvc.create_section(db_session, seeded_property.id, "South",
                                actor=None)
    r = svc.create_room(db_session, "304", sec.id, actor=None)
    svc.update_room(db_session, r.id, section_id=other.id, actor=None)
    assert svc.list_rooms(db_session, other.id)[0].id == r.id
```

Note: a `422`-class condition is raised as a validation error. Use the validation error class discovered in Task 0c; this plan shows `ValueError` as the placeholder-free stand-in only if no project class exists — prefer the discovered project class (e.g. `ValidationError`). Replace `ValueError` consistently in the test and service if a project class exists.

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_svc_rooms.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/services/rooms.py
import uuid
from sqlalchemy.orm import Session
from conduit.core.exceptions import NotFoundError, ConflictError
from conduit.supervisor.dal import rooms as dal, sections as sdal


def _require_section(db, section_id):
    if sdal.get_section(db, section_id) is None:
        raise ValueError("Section does not exist")  # 422-class


def list_rooms(db: Session, section_id: uuid.UUID | None = None):
    return dal.list_rooms(db, section_id)


def create_room(db: Session, label: str, section_id: uuid.UUID, *, actor):
    _require_section(db, section_id)
    if dal.get_room_by_label(db, label) is not None:
        raise ConflictError("Room label already exists")
    return dal.insert_room(db, section_id, label)


def update_room(
    db: Session, room_id: uuid.UUID, *,
    label: str | None = None, section_id: uuid.UUID | None = None, actor,
):
    room = dal.get_room(db, room_id)
    if room is None:
        raise NotFoundError("Room not found")
    if section_id is not None:
        _require_section(db, section_id)
    if label is not None:
        dup = dal.get_room_by_label(db, label)
        if dup is not None and dup.id != room.id:
            raise ConflictError("Room label already exists")
    return dal.update_room(db, room, label=label, section_id=section_id)
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_svc_rooms.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/services/rooms.py tests/binding/test_svc_rooms.py
git commit -m "feat(supervisor/services): rooms business logic"
```

### Task 14: `supervisor/services/stays.py` — create / update / relocate / checkout

**Files:**
- Create: `conduit/supervisor/services/stays.py`
- Test: `tests/binding/test_svc_stays.py`

- [ ] **Step 1: Write the failing test (every branch + every guard + event emission)**

```python
# tests/binding/test_svc_stays.py
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select, func
from conduit.supervisor.services import sections as ssvc, rooms as rsvc, stays as svc
from conduit.core.exceptions import NotFoundError, ConflictError
from conduit.shared.models.account import Account
from conduit.shared.models.event import (
    Event, EventStayCreated, EventStayEnded, EventGuestRelocated,
)


def _guest(db, active=True):
    g = Account(role="guest", username=f"g{uuid.uuid4().hex[:8]}",
                secret_hash="x", display_name="G",
                status="active" if active else "disabled")
    db.add(g); db.flush()
    return g


@pytest.fixture
def fixtures(db_session, seeded_property):
    s = ssvc.create_section(db_session, seeded_property.id, "North", actor=None)
    r1 = rsvc.create_room(db_session, "304", s.id, actor=None)
    r2 = rsvc.create_room(db_session, "511", s.id, actor=None)
    return s, r1, r2


def _win():
    n = datetime.now(timezone.utc)
    return n, n + timedelta(days=2)


def test_create_success_emits_event(db_session, fixtures):
    _, r1, _ = fixtures
    g = _guest(db_session)
    ci, co = _win()
    st = svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)
    assert st.status == "active"
    assert db_session.execute(
        select(func.count()).select_from(EventStayCreated)).scalar() == 1
    ev = db_session.execute(select(Event)).scalars().one()
    assert ev.type == "stay_created"


def test_create_non_guest_422(db_session, fixtures):
    _, r1, _ = fixtures
    sup = Account(role="supervisor", username=f"s{uuid.uuid4().hex[:6]}",
                  secret_hash="x", display_name="S", status="active")
    db_session.add(sup); db_session.flush()
    ci, co = _win()
    with pytest.raises(ValueError):
        svc.create_stay(db_session, sup.id, r1.id, ci, co, actor=None)


def test_create_disabled_guest_422(db_session, fixtures):
    _, r1, _ = fixtures
    g = _guest(db_session, active=False)
    ci, co = _win()
    with pytest.raises(ValueError):
        svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)


def test_create_bad_room_422(db_session):
    g = _guest(db_session)
    ci, co = _win()
    with pytest.raises(ValueError):
        svc.create_stay(db_session, g.id, uuid.uuid4(), ci, co, actor=None)


def test_create_existing_active_409(db_session, fixtures):
    _, r1, _ = fixtures
    g = _guest(db_session)
    ci, co = _win()
    svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)
    with pytest.raises(ConflictError):
        svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)


def test_update_benign_no_event(db_session, fixtures):
    _, r1, _ = fixtures
    g = _guest(db_session)
    ci, co = _win()
    st = svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)
    before = db_session.execute(select(func.count()).select_from(Event)).scalar()
    svc.update_stay(db_session, st.id, check_out=co + timedelta(days=1),
                    actor=None)
    after = db_session.execute(select(func.count()).select_from(Event)).scalar()
    assert before == after  # no event for a benign edit


def test_update_missing_404(db_session):
    with pytest.raises(NotFoundError):
        svc.update_stay(db_session, uuid.uuid4(), actor=None)


def test_relocate_success_event(db_session, fixtures):
    _, r1, r2 = fixtures
    g = _guest(db_session)
    ci, co = _win()
    st = svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)
    svc.relocate_stay(db_session, st.id, r2.id, actor=None)
    assert svc.list_for_guest(db_session, g.id)[0].room_id == r2.id
    rel = db_session.execute(select(EventGuestRelocated)).scalars().one()
    assert rel.from_room_id == r1.id and rel.to_room_id == r2.id


def test_relocate_missing_404(db_session, fixtures):
    _, _, r2 = fixtures
    with pytest.raises(NotFoundError):
        svc.relocate_stay(db_session, uuid.uuid4(), r2.id, actor=None)


def test_relocate_same_room_409(db_session, fixtures):
    _, r1, _ = fixtures
    g = _guest(db_session)
    ci, co = _win()
    st = svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)
    with pytest.raises(ConflictError):
        svc.relocate_stay(db_session, st.id, r1.id, actor=None)


def test_relocate_bad_room_422(db_session, fixtures):
    _, r1, _ = fixtures
    g = _guest(db_session)
    ci, co = _win()
    st = svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)
    with pytest.raises(ValueError):
        svc.relocate_stay(db_session, st.id, uuid.uuid4(), actor=None)


def test_checkout_success_then_recheckin(db_session, fixtures):
    _, r1, _ = fixtures
    g = _guest(db_session)
    ci, co = _win()
    st = svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)
    svc.checkout_stay(db_session, st.id, actor=None)
    assert db_session.execute(
        select(func.count()).select_from(EventStayEnded)).scalar() == 1
    # active released → re-check-in allowed
    svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)


def test_relocate_non_active_409(db_session, fixtures):
    _, r1, r2 = fixtures
    g = _guest(db_session)
    ci, co = _win()
    st = svc.create_stay(db_session, g.id, r1.id, ci, co, actor=None)
    svc.checkout_stay(db_session, st.id, actor=None)
    with pytest.raises(ConflictError):
        svc.relocate_stay(db_session, st.id, r2.id, actor=None)
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_svc_stays.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/services/stays.py
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from conduit.core.exceptions import NotFoundError, ConflictError
from conduit.shared.models.account import Account
from conduit.supervisor.dal import stays as dal, rooms as rdal, events as edal


def list_stays(db, status=None, guest_id=None):
    return dal.list_stays(db, status=status, guest_id=guest_id)


def list_for_guest(db, guest_id):
    return dal.list_stays(db, guest_id=guest_id)


def _require_guest(db, guest_account_id):
    g = db.get(Account, guest_account_id)
    if g is None or g.role != "guest" or g.status != "active":
        raise ValueError("Guest account invalid")  # 422-class


def _require_room(db, room_id):
    if rdal.get_room(db, room_id) is None:
        raise ValueError("Room does not exist")  # 422-class


def create_stay(
    db: Session, guest_account_id: uuid.UUID, room_id: uuid.UUID,
    check_in: datetime, check_out: datetime, *, actor,
):
    _require_guest(db, guest_account_id)
    _require_room(db, room_id)
    if dal.get_active_stay_for_guest(db, guest_account_id) is not None:
        raise ConflictError("Guest already has an active stay")
    st = dal.insert_stay(db, guest_account_id, room_id, check_in, check_out)
    ev = edal.insert_event(
        db, type="stay_created",
        actor_account_id=getattr(actor, "id", None),
    )
    edal.insert_stay_created(db, ev.id, st.id)
    return st


def update_stay(
    db: Session, stay_id: uuid.UUID, *,
    check_in: datetime | None = None, check_out: datetime | None = None,
    actor,
):
    st = dal.get_stay(db, stay_id)
    if st is None:
        raise NotFoundError("Stay not found")
    return dal.update_stay_fields(db, st, check_in=check_in,
                                  check_out=check_out)


def relocate_stay(
    db: Session, stay_id: uuid.UUID, new_room_id: uuid.UUID, *, actor,
):
    st = dal.get_stay(db, stay_id)
    if st is None:
        raise NotFoundError("Stay not found")
    if st.status != "active":
        raise ConflictError("Stay is not active")
    _require_room(db, new_room_id)
    if st.room_id == new_room_id:
        raise ConflictError("Already in that room")
    from_room = st.room_id
    dal.set_stay_room(db, st, new_room_id)
    ev = edal.insert_event(
        db, type="guest_relocated",
        actor_account_id=getattr(actor, "id", None),
    )
    edal.insert_guest_relocated(db, ev.id, st.id, from_room, new_room_id)
    return st


def checkout_stay(db: Session, stay_id: uuid.UUID, *, actor):
    st = dal.get_stay(db, stay_id)
    if st is None:
        raise NotFoundError("Stay not found")
    if st.status != "active":
        raise ConflictError("Stay is not active")
    dal.set_stay_status(db, st, "ended")
    ev = edal.insert_event(
        db, type="stay_ended",
        actor_account_id=getattr(actor, "id", None),
    )
    edal.insert_stay_ended(db, ev.id, st.id)
    return st
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_svc_stays.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/services/stays.py tests/binding/test_svc_stays.py
git commit -m "feat(supervisor/services): stays — create/update/relocate/checkout + guards + events"
```

### Task 15: Extend `public/services/auth.py` — `resolve_ambient`

**Files:**
- Modify: `conduit/public/services/auth.py`
- Test: `tests/binding/test_svc_ambient.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_svc_ambient.py
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from conduit.public.services import auth as svc
from conduit.supervisor.services import sections as ssvc, rooms as rsvc, stays as stsvc
from conduit.shared.models.account import Account


def _guest(db):
    g = Account(role="guest", username=f"g{uuid.uuid4().hex[:8]}",
                secret_hash="x", display_name="G", status="active")
    db.add(g); db.flush()
    return g


def test_non_guest_none(db_session):
    sup = Account(role="supervisor", username=f"s{uuid.uuid4().hex[:6]}",
                  secret_hash="x", display_name="S", status="active")
    db_session.add(sup); db_session.flush()
    assert svc.resolve_ambient(db_session, sup) is None


def test_guest_no_active_none(db_session):
    assert svc.resolve_ambient(db_session, _guest(db_session)) is None


def test_guest_active_resolves(db_session, seeded_property):
    g = _guest(db_session)
    s = ssvc.create_section(db_session, seeded_property.id, "North", actor=None)
    r = rsvc.create_room(db_session, "304", s.id, actor=None)
    n = datetime.now(timezone.utc)
    stsvc.create_stay(db_session, g.id, r.id, n, n + timedelta(days=1),
                      actor=None)
    amb = svc.resolve_ambient(db_session, g)
    assert amb["room_label"] == "304" and amb["section_label"] == "North"
    assert set(amb) == {"stay_id", "room_id", "room_label",
                        "section_id", "section_label"}
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_svc_ambient.py -q`
Expected: FAIL `AttributeError: module ... has no attribute 'resolve_ambient'`

- [ ] **Step 3: Implement (append to the existing auth service module)**

Append this function to `conduit/public/services/auth.py` (do not alter existing functions):

```python
from conduit.public.dal import bindings as _bindings


def resolve_ambient(db, account):
    """Guest-only ambient context, resolved per request. None otherwise."""
    if getattr(account, "role", None) != "guest":
        return None
    trio = _bindings.get_active_binding_for_guest(db, account.id)
    if trio is None:
        return None
    stay, room, section = trio
    return {
        "stay_id": stay.id,
        "room_id": room.id,
        "room_label": room.label,
        "section_id": section.id,
        "section_label": section.label,
    }
```

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_svc_ambient.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/public/services/auth.py tests/binding/test_svc_ambient.py
git commit -m "feat(public/services): resolve_ambient (auth-owned extension)"
```

### Task 16: Schemas — supervisor binding + AuthUser ambient extension

**Files:**
- Create: `conduit/supervisor/schemas/binding.py`
- Modify: the `/auth/me` response model discovered in Task 0c
- Test: `tests/binding/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_schemas.py
from conduit.supervisor.schemas.binding import (
    SectionOut, RoomOut, StayOut, SectionCreate, RoomCreate, RoomUpdate,
    StayCreate, StayUpdate, RelocateIn,
)


def test_section_out_forbids_extra():
    import pytest, pydantic
    with pytest.raises(pydantic.ValidationError):
        SectionOut(id="x", label="N", room_count=0,
                   created_at="2026-01-01T00:00:00Z", leaked=1)
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_schemas.py -q`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement supervisor schemas**

```python
# conduit/supervisor/schemas/binding.py
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SectionCreate(_Base):
    label: str


class SectionOut(_Base):
    id: uuid.UUID
    label: str
    room_count: int
    created_at: datetime


class RoomCreate(_Base):
    label: str
    section_id: uuid.UUID


class RoomUpdate(_Base):
    label: str | None = None
    section_id: uuid.UUID | None = None


class RoomOut(_Base):
    id: uuid.UUID
    label: str
    section_id: uuid.UUID
    section_label: str
    created_at: datetime


class StayCreate(_Base):
    guest_account_id: uuid.UUID
    room_id: uuid.UUID
    check_in: datetime
    check_out: datetime


class StayUpdate(_Base):
    check_in: datetime | None = None
    check_out: datetime | None = None


class RelocateIn(_Base):
    new_room_id: uuid.UUID


class StayOut(_Base):
    id: uuid.UUID
    guest_account_id: uuid.UUID
    guest_display_name: str
    room_id: uuid.UUID
    room_label: str
    section_id: uuid.UUID
    section_label: str
    check_in: datetime
    check_out: datetime
    status: str
    created_at: datetime
```

- [ ] **Step 4: Extend the `/auth/me` response model**

In the `/auth/me` response model module discovered in Task 0c, add five optional ambient fields (do not remove or rename existing fields). If the model is e.g. `AuthUser` in `conduit/public/schemas/__init__.py`:

```python
    # appended fields on the existing AuthUser model:
    stay_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    room_label: str | None = None
    section_id: uuid.UUID | None = None
    section_label: str | None = None
```

(Add `import uuid` if absent. Keep the model's existing `ConfigDict`.)

- [ ] **Step 5: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_schemas.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add conduit/supervisor/schemas/binding.py conduit/public/schemas/
git commit -m "feat(schemas): supervisor binding + AuthUser ambient fields"
```

### Task 17: Supervisor API — `setup.py` (sections + rooms)

**Files:**
- Create or modify: `conduit/supervisor/api/setup.py`
- Modify: the supervisor API router include (discover with `grep -rn "include_router" conduit/apps conduit/supervisor`)
- Test: `tests/binding/test_api_setup.py`

Use the authenticated-supervisor client fixture discovered in Task 0c (shown as `supervisor_client`) and the unauthenticated `client`.

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_api_setup.py
def test_sections_crud_flow(supervisor_client):
    r = supervisor_client.post("/api/supervisor/sections",
                               json={"label": "North"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert supervisor_client.get("/api/supervisor/sections").status_code == 200
    dup = supervisor_client.post("/api/supervisor/sections",
                                 json={"label": "north"})
    assert dup.status_code == 409
    rn = supervisor_client.patch(f"/api/supervisor/sections/{sid}",
                                 json={"label": "N"})
    assert rn.status_code == 200 and rn.json()["label"] == "N"


def test_rooms_crud_flow(supervisor_client):
    sid = supervisor_client.post("/api/supervisor/sections",
                                 json={"label": "S"}).json()["id"]
    r = supervisor_client.post("/api/supervisor/rooms",
                               json={"label": "304", "section_id": sid})
    assert r.status_code == 201
    assert supervisor_client.get(
        f"/api/supervisor/rooms?section_id={sid}").status_code == 200


def test_delete_405(supervisor_client):
    sid = supervisor_client.post("/api/supervisor/sections",
                                 json={"label": "Z"}).json()["id"]
    assert supervisor_client.delete(
        f"/api/supervisor/sections/{sid}").status_code == 405


def test_unauth_401(client):
    assert client.get("/api/supervisor/sections").status_code == 401
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_api_setup.py -q`
Expected: FAIL (routes 404 / module missing)

- [ ] **Step 3: Implement**

Match the existing supervisor router/gating pattern (the auth slice's `require_roles` dependency for `/supervisor/*`). If `setup.py` already exists for other setup pages, append these routes to its router.

```python
# conduit/supervisor/api/setup.py  (create or extend)
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from conduit.core.deps import db_session, current_actor, require_roles
from conduit.supervisor.services import sections as ssvc, rooms as rsvc
from conduit.supervisor.schemas.binding import (
    SectionOut, SectionCreate, RoomOut, RoomCreate, RoomUpdate,
)
from conduit.shared.models.property import Property
from sqlalchemy import select

router = APIRouter(
    prefix="/api/supervisor",
    dependencies=[Depends(require_roles("supervisor", "duty_manager"))],
)


def _property_id(db: Session) -> uuid.UUID:
    return db.execute(select(Property.id)).scalars().first()


@router.get("/sections", response_model=list[SectionOut])
def list_sections(db: Session = Depends(db_session)):
    return [
        SectionOut(id=s.id, label=s.label, room_count=c,
                   created_at=s.created_at)
        for s, c in ssvc.list_sections(db)
    ]


@router.post("/sections", response_model=SectionOut, status_code=201)
def create_section(body: SectionCreate, db: Session = Depends(db_session),
                   actor=Depends(current_actor)):
    s = ssvc.create_section(db, _property_id(db), body.label, actor=actor)
    return SectionOut(id=s.id, label=s.label, room_count=0,
                      created_at=s.created_at)


@router.patch("/sections/{section_id}", response_model=SectionOut)
def rename_section(section_id: uuid.UUID, body: SectionCreate,
                  db: Session = Depends(db_session),
                  actor=Depends(current_actor)):
    s = ssvc.rename_section(db, section_id, body.label, actor=actor)
    counts = {x.id: c for x, c in ssvc.list_sections(db)}
    return SectionOut(id=s.id, label=s.label,
                      room_count=counts.get(s.id, 0),
                      created_at=s.created_at)


def _room_out(db, r) -> RoomOut:
    from conduit.supervisor.dal import sections as sdal
    sec = sdal.get_section(db, r.section_id)
    return RoomOut(id=r.id, label=r.label, section_id=r.section_id,
                   section_label=sec.label, created_at=r.created_at)


@router.get("/rooms", response_model=list[RoomOut])
def list_rooms(section_id: uuid.UUID | None = None,
              db: Session = Depends(db_session)):
    return [_room_out(db, r) for r in rsvc.list_rooms(db, section_id)]


@router.post("/rooms", response_model=RoomOut, status_code=201)
def create_room(body: RoomCreate, db: Session = Depends(db_session),
               actor=Depends(current_actor)):
    r = rsvc.create_room(db, body.label, body.section_id, actor=actor)
    return _room_out(db, r)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: uuid.UUID, body: RoomUpdate,
               db: Session = Depends(db_session),
               actor=Depends(current_actor)):
    r = rsvc.update_room(db, room_id, label=body.label,
                         section_id=body.section_id, actor=actor)
    return _room_out(db, r)
```

Ensure this router is included by the app (match the existing include pattern; if `setup.py` already had a router that is included, keep that single router).

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_api_setup.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/api/setup.py tests/binding/test_api_setup.py
git commit -m "feat(supervisor/api): sections + rooms routes"
```

### Task 18: Supervisor API — `stays.py`

**Files:**
- Create: `conduit/supervisor/api/stays.py`
- Modify: app router include
- Test: `tests/binding/test_api_stays.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_api_stays.py
import uuid


def _make_guest_room(supervisor_client):
    sid = supervisor_client.post("/api/supervisor/sections",
                                 json={"label": "N"}).json()["id"]
    rid = supervisor_client.post("/api/supervisor/rooms",
                                 json={"label": "304", "section_id": sid}
                                 ).json()["id"]
    g = supervisor_client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": f"g{uuid.uuid4().hex[:8]}",
        "display_name": "G", "password": "pw"}).json()["id"]
    return g, rid


def test_checkin_relocate_checkout(supervisor_client):
    g, rid = _make_guest_room(supervisor_client)
    sid2 = supervisor_client.post("/api/supervisor/sections",
                                  json={"label": "S"}).json()["id"]
    rid2 = supervisor_client.post("/api/supervisor/rooms",
                                  json={"label": "511", "section_id": sid2}
                                  ).json()["id"]
    r = supervisor_client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})
    assert r.status_code == 201, r.text
    st = r.json()["id"]
    dup = supervisor_client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})
    assert dup.status_code == 409
    mv = supervisor_client.post(f"/api/supervisor/stays/{st}/relocate",
                                json={"new_room_id": rid2})
    assert mv.status_code == 200 and mv.json()["room_id"] == rid2
    same = supervisor_client.post(f"/api/supervisor/stays/{st}/relocate",
                                  json={"new_room_id": rid2})
    assert same.status_code == 409
    co = supervisor_client.post(f"/api/supervisor/stays/{st}/checkout")
    assert co.status_code == 200 and co.json()["status"] == "ended"
    relo_after = supervisor_client.post(
        f"/api/supervisor/stays/{st}/relocate", json={"new_room_id": rid})
    assert relo_after.status_code == 409


def test_stay_unknown_404(supervisor_client):
    assert supervisor_client.post(
        f"/api/supervisor/stays/{uuid.uuid4()}/checkout").status_code == 404


def test_stays_delete_405(supervisor_client):
    assert supervisor_client.delete(
        "/api/supervisor/stays").status_code == 405
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_api_stays.py -q`
Expected: FAIL (routes missing)

- [ ] **Step 3: Implement**

```python
# conduit/supervisor/api/stays.py
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from conduit.core.deps import db_session, current_actor, require_roles
from conduit.supervisor.services import stays as svc
from conduit.supervisor.dal import rooms as rdal, sections as sdal
from conduit.supervisor.schemas.binding import (
    StayOut, StayCreate, StayUpdate, RelocateIn,
)
from conduit.shared.models.account import Account

router = APIRouter(
    prefix="/api/supervisor",
    dependencies=[Depends(require_roles("supervisor", "duty_manager"))],
)


def _stay_out(db: Session, st) -> StayOut:
    room = rdal.get_room(db, st.room_id)
    section = sdal.get_section(db, room.section_id)
    guest = db.get(Account, st.guest_account_id)
    return StayOut(
        id=st.id, guest_account_id=st.guest_account_id,
        guest_display_name=guest.display_name,
        room_id=room.id, room_label=room.label,
        section_id=section.id, section_label=section.label,
        check_in=st.check_in, check_out=st.check_out,
        status=st.status, created_at=st.created_at,
    )


@router.get("/stays", response_model=list[StayOut])
def list_stays(status: str | None = None,
              guest_id: uuid.UUID | None = None,
              db: Session = Depends(db_session)):
    return [_stay_out(db, s)
            for s in svc.list_stays(db, status=status, guest_id=guest_id)]


@router.post("/stays", response_model=StayOut, status_code=201)
def create_stay(body: StayCreate, db: Session = Depends(db_session),
               actor=Depends(current_actor)):
    st = svc.create_stay(db, body.guest_account_id, body.room_id,
                          body.check_in, body.check_out, actor=actor)
    return _stay_out(db, st)


@router.patch("/stays/{stay_id}", response_model=StayOut)
def update_stay(stay_id: uuid.UUID, body: StayUpdate,
               db: Session = Depends(db_session),
               actor=Depends(current_actor)):
    st = svc.update_stay(db, stay_id, check_in=body.check_in,
                         check_out=body.check_out, actor=actor)
    return _stay_out(db, st)


@router.post("/stays/{stay_id}/relocate", response_model=StayOut)
def relocate(stay_id: uuid.UUID, body: RelocateIn,
            db: Session = Depends(db_session),
            actor=Depends(current_actor)):
    st = svc.relocate_stay(db, stay_id, body.new_room_id, actor=actor)
    return _stay_out(db, st)


@router.post("/stays/{stay_id}/checkout", response_model=StayOut)
def checkout(stay_id: uuid.UUID, db: Session = Depends(db_session),
            actor=Depends(current_actor)):
    st = svc.checkout_stay(db, stay_id, actor=actor)
    return _stay_out(db, st)
```

Include this router in the app where the other supervisor routers are included.

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_api_stays.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/supervisor/api/stays.py tests/binding/test_api_stays.py
git commit -m "feat(supervisor/api): stays routes (checkin/update/relocate/checkout)"
```

### Task 19: Wire ambient into `/auth/me`

**Files:**
- Modify: `conduit/public/api/auth.py` (the `/auth/me` handler)
- Test: `tests/binding/test_api_ambient.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_api_ambient.py
import uuid


def test_guest_me_carries_ambient_no_relogin(supervisor_client, client):
    sid = supervisor_client.post("/api/supervisor/sections",
                                 json={"label": "N"}).json()["id"]
    rid = supervisor_client.post("/api/supervisor/rooms",
                                 json={"label": "304", "section_id": sid}
                                 ).json()["id"]
    sid2 = supervisor_client.post("/api/supervisor/sections",
                                  json={"label": "S"}).json()["id"]
    rid2 = supervisor_client.post("/api/supervisor/rooms",
                                  json={"label": "511", "section_id": sid2}
                                  ).json()["id"]
    uname = f"g{uuid.uuid4().hex[:8]}"
    g = supervisor_client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": uname,
        "display_name": "G", "password": "pw"}).json()["id"]
    st = supervisor_client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"}).json()["id"]

    client.post("/api/auth/login", json={"username": uname,
                                         "password": "pw"})
    me = client.get("/api/auth/me").json()
    assert me["room_label"] == "304" and me["section_label"] == "N"

    supervisor_client.post(f"/api/supervisor/stays/{st}/relocate",
                           json={"new_room_id": rid2})
    me2 = client.get("/api/auth/me").json()        # same cookie, no re-login
    assert me2["room_label"] == "511" and me2["section_label"] == "S"


def test_supervisor_me_ambient_null(supervisor_client):
    me = supervisor_client.get("/api/auth/me").json()
    assert me.get("room_id") is None
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_api_ambient.py -q`
Expected: FAIL (ambient fields absent / null for the guest)

- [ ] **Step 3: Implement**

In `conduit/public/api/auth.py`, locate the `/me` handler that returns the auth user. Merge `resolve_ambient` into the response model construction without changing existing fields:

```python
from conduit.public.services import auth as auth_svc

# inside the GET /auth/me handler, where the response model is built:
    ambient = auth_svc.resolve_ambient(db, actor) or {}
    return AuthUser(
        # ...existing fields unchanged...
        stay_id=ambient.get("stay_id"),
        room_id=ambient.get("room_id"),
        room_label=ambient.get("room_label"),
        section_id=ambient.get("section_id"),
        section_label=ambient.get("section_label"),
    )
```

(Use the exact existing handler's variable names for the actor/session/`AuthUser` discovered in Task 0c. Do not duplicate the handler — extend the existing return.)

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_api_ambient.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/public/api/auth.py tests/binding/test_api_ambient.py
git commit -m "feat(public/api): /auth/me carries guest ambient (seam — re-resolved per request)"
```

### Task 20: Structural guards + named invariants + e2e journey sentinel

**Files:**
- Create: `tests/binding/test_invariants.py`, `tests/binding/test_e2e_journey.py`, `tests/binding/test_contract_snapshot.py`
- Modify: the committed contract snapshot artifact discovered in Task 0c (auth's snapshot file)
- Modify: `pyproject.toml` coverage scope (extend `--cov` to the binding modules)

- [ ] **Step 1: Named-invariant tests**

```python
# tests/binding/test_invariants.py
import uuid
import pytest
from sqlalchemy import text


def test_partial_unique_index_blocks_second_active(db_session, seeded_property):
    # Physical backstop, independent of the service guard.
    from conduit.supervisor.dal import sections as sdal, rooms as rdal
    from conduit.shared.models.account import Account
    s = sdal.insert_section(db_session, seeded_property.id, "N")
    r = rdal.insert_room(db_session, s.id, "304")
    g = Account(role="guest", username=f"g{uuid.uuid4().hex[:8]}",
                secret_hash="x", display_name="G", status="active")
    db_session.add(g); db_session.flush()
    db_session.execute(text(
        "insert into stay (id,guest_account_id,room_id,check_in,check_out,"
        "status,created_at,updated_at) values (gen_random_uuid(),:g,:r,"
        "now(),now(),'active',now(),now())"), {"g": str(g.id), "r": str(r.id)})
    db_session.flush()
    with pytest.raises(Exception):
        db_session.execute(text(
            "insert into stay (id,guest_account_id,room_id,check_in,"
            "check_out,status,created_at,updated_at) values "
            "(gen_random_uuid(),:g,:r,now(),now(),'active',now(),now())"),
            {"g": str(g.id), "r": str(r.id)})
        db_session.flush()
    db_session.rollback()


def test_event_tables_append_only(db_session):
    # No app update/delete path exists; assert the DAL exposes none.
    from conduit.supervisor.dal import events as edal
    names = dir(edal)
    assert not any(n.startswith(("update_", "delete_")) for n in names)


def test_section_derived_no_stay_write(supervisor_client, client):
    import uuid as _u
    sid = supervisor_client.post("/api/supervisor/sections",
                                 json={"label": "N"}).json()["id"]
    rid = supervisor_client.post("/api/supervisor/rooms",
                                 json={"label": "304", "section_id": sid}
                                 ).json()["id"]
    sid2 = supervisor_client.post("/api/supervisor/sections",
                                  json={"label": "S"}).json()["id"]
    uname = f"g{_u.uuid4().hex[:8]}"
    g = supervisor_client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": uname, "display_name": "G",
        "password": "pw"}).json()["id"]
    supervisor_client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": rid,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"})
    client.post("/api/auth/login", json={"username": uname,
                                         "password": "pw"})
    assert client.get("/api/auth/me").json()["section_label"] == "N"
    # Reassign the room to another section — no stay mutation.
    supervisor_client.patch(f"/api/supervisor/rooms/{rid}",
                            json={"section_id": sid2})
    assert client.get("/api/auth/me").json()["section_label"] == "S"
```

- [ ] **Step 2: End-to-end journey sentinel**

```python
# tests/binding/test_e2e_journey.py
import uuid


def test_full_check_in_relocate_checkout_journey(supervisor_client, client):
    s1 = supervisor_client.post("/api/supervisor/sections",
                                json={"label": "North"}).json()["id"]
    r1 = supervisor_client.post("/api/supervisor/rooms",
                                json={"label": "304", "section_id": s1}
                                ).json()["id"]
    s2 = supervisor_client.post("/api/supervisor/sections",
                                json={"label": "South"}).json()["id"]
    r2 = supervisor_client.post("/api/supervisor/rooms",
                                json={"label": "511", "section_id": s2}
                                ).json()["id"]
    uname = f"g{uuid.uuid4().hex[:8]}"
    g = supervisor_client.post("/api/supervisor/accounts", json={
        "role": "guest", "username": uname, "display_name": "Guest",
        "password": "pw"}).json()["id"]

    st = supervisor_client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": r1,
        "check_in": "2026-05-16T14:00:00Z",
        "check_out": "2026-05-19T11:00:00Z"}).json()["id"]

    client.post("/api/auth/login",
                json={"username": uname, "password": "pw"})
    me = client.get("/api/auth/me").json()
    assert me["room_label"] == "304" and me["section_label"] == "North"

    supervisor_client.post(f"/api/supervisor/stays/{st}/relocate",
                           json={"new_room_id": r2})
    me = client.get("/api/auth/me").json()  # no re-login
    assert me["room_label"] == "511" and me["section_label"] == "South"

    supervisor_client.patch(f"/api/supervisor/rooms/{r2}",
                            json={"section_id": s1})
    assert client.get("/api/auth/me").json()["section_label"] == "North"

    supervisor_client.post(f"/api/supervisor/stays/{st}/checkout")
    me = client.get("/api/auth/me").json()
    assert me.get("room_id") is None

    # active released → re-check-in allowed
    again = supervisor_client.post("/api/supervisor/stays", json={
        "guest_account_id": g, "room_id": r1,
        "check_in": "2026-06-01T14:00:00Z",
        "check_out": "2026-06-03T11:00:00Z"})
    assert again.status_code == 201
```

- [ ] **Step 3: Contract snapshot — extend, intentionally**

Discover auth's contract-snapshot test + committed artifact (Task 0c: `grep -rn "openapi" tests/`). Regenerate the snapshot so it now includes the new `/api/supervisor/sections|rooms|stays*` routes and the extended `/api/auth/me` shape, following auth's exact regeneration command. Add `tests/binding/test_contract_snapshot.py` only if auth's snapshot test does not already glob all routes (if it does, the new routes are auto-covered — assert that and skip a duplicate):

```python
# tests/binding/test_contract_snapshot.py
def test_binding_routes_in_snapshot():
    # Sanity: the inherited snapshot guard must already include our routes.
    import json, pathlib
    # Path discovered in Task 0c; adjust to the project's snapshot file.
    snap = json.loads(pathlib.Path(
        "tests/contract_snapshot.json").read_text())
    paths = set(snap if isinstance(snap, list) else snap.get("paths", snap))
    text = json.dumps(snap)
    for p in ("/api/supervisor/sections", "/api/supervisor/rooms",
              "/api/supervisor/stays"):
        assert p in text, f"{p} missing from committed contract snapshot"
```

- [ ] **Step 4: Extend the coverage gate to the binding modules**

In `pyproject.toml`, extend the existing `--cov` config so it also scopes the binding modules at branch coverage, 100% on dal+services. Match auth's existing `addopts`/`[tool.coverage]` shape (discovered in Task 0c). Example addition to `[tool.coverage.run]` `source`/`include`:

```
conduit/supervisor/dal/*, conduit/supervisor/services/*, conduit/public/dal/bindings.py
```

and ensure `[tool.coverage.report] fail_under` stays enforced with `branch = true`.

- [ ] **Step 5: Run the full binding suite**

Run: `./.venv/bin/pytest tests/binding -q --cov`
Expected: PASS, coverage gate green.

- [ ] **Step 6: Commit**

```bash
git add tests/binding/test_invariants.py tests/binding/test_e2e_journey.py tests/binding/test_contract_snapshot.py tests/ pyproject.toml
git commit -m "test(binding): named invariants + e2e journey sentinel + contract snapshot + coverage gate"
```

### Task 21: Seed `ensure_property`

**Files:**
- Modify: the seed entrypoint discovered in Task 0c (`grep -rn "def seed\|__main__" conduit | grep -i seed`)
- Test: `tests/binding/test_seed_property.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/binding/test_seed_property.py
from sqlalchemy import select, func
from conduit.shared.models.property import Property
from conduit.seed import ensure_property  # adjust import to discovered path


def test_ensure_property_idempotent(db_session):
    ensure_property(db_session)
    ensure_property(db_session)
    db_session.commit()
    n = db_session.execute(
        select(func.count()).select_from(Property)).scalar()
    assert n == 1
```

- [ ] **Step 2: Run it, expect fail**

Run: `./.venv/bin/pytest tests/binding/test_seed_property.py -q`
Expected: FAIL (`ensure_property` missing)

- [ ] **Step 3: Implement**

Add to the seed module (idempotency is a rule → service/seed level, not DAL):

```python
from sqlalchemy import select
from conduit.shared.models.property import Property


def ensure_property(db, name: str = "Conduit Property") -> Property:
    existing = db.execute(select(Property)).scalars().first()
    if existing is not None:
        return existing
    p = Property(name=name)
    db.add(p)
    db.flush()
    return p
```

Call `ensure_property` from the seed entrypoint (alongside the existing bootstrap-supervisor seed), before any account seed that might bind a stay.

- [ ] **Step 4: Run it, expect pass**

Run: `./.venv/bin/pytest tests/binding/test_seed_property.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conduit/seed.py tests/binding/test_seed_property.py
git commit -m "feat(seed): idempotent ensure_property"
```

### Task 22: Full backend suite green

- [ ] **Step 1: Run everything**

Run: `./.venv/bin/pytest -q --cov`
Expected: PASS, coverage gate green, leak sentinel silent.

- [ ] **Step 2: Lint/type per the project's configured tools**

Run the project's configured linters (discover from `pyproject.toml`: `ruff`, `mypy`). Example: `./.venv/bin/ruff check conduit && ./.venv/bin/mypy conduit`
Expected: clean (fix any new findings in this slice's files only).

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -A && git commit -m "chore(binding): lint/type clean" || echo "nothing to commit"
```

---

# PHASE 2 — Frontend

> Paths relative to `/workspace/Conduit-stay-binding/frontend`. The auth slice provides `card/form/table/dialog/alert-dialog/sonner/badge/select/alert/tabs` + the shared primitives. **Do not re-add auth-provided components** — re-running their `shadcn add` clobbers the auth agent's edits.

### Task 23: Install net-new shadcn components + monochrome edit pass

**Files:**
- Create (via CLI): `src/components/ui/popover.tsx`, `calendar.tsx`, `command.tsx`, `accordion.tsx`

- [ ] **Step 1: Install**

```bash
cd /workspace/Conduit-stay-binding/frontend
npx shadcn@latest add popover calendar command accordion
```

- [ ] **Step 2: Monochrome/tighten edit pass**

In each of the four new files: remove any non-neutral color utilities, ensure focus rings use `ring`, remove drop shadows beyond `shadow-sm`, and confirm radii use the project `--radius` tokens (no hard-coded `rounded-lg`). Do **not** retune global tokens (`index.css`) — that is the auth-merge design-system coordination, out of scope here.

- [ ] **Step 3: Verify build**

Run: `npx tsc -b && npx eslint src --max-warnings 0`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/components/ui/popover.tsx src/components/ui/calendar.tsx src/components/ui/command.tsx src/components/ui/accordion.tsx
git commit -m "feat(ui): add popover/calendar/command/accordion (monochrome-edited)"
```

### Task 24: Composed patterns — `combobox-field`, `date-range-field`

**Files:**
- Create: `src/components/common/combobox-field.tsx`, `src/components/common/date-range-field.tsx`

- [ ] **Step 1: Implement `combobox-field`**

```tsx
// src/components/common/combobox-field.tsx
import { useState } from "react"
import { Check, ChevronsUpDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command"
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover"

export type ComboOption = { value: string; label: string }

export function ComboboxField({
  options, value, onChange, placeholder = "Select…", emptyText = "None found",
}: {
  options: ComboOption[]
  value: string | null
  onChange: (v: string) => void
  placeholder?: string
  emptyText?: string
}) {
  const [open, setOpen] = useState(false)
  const selected = options.find((o) => o.value === value)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline" role="combobox" aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          {selected ? selected.label : placeholder}
          <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0">
        <Command>
          <CommandInput placeholder={placeholder} />
          <CommandList>
            <CommandEmpty>{emptyText}</CommandEmpty>
            <CommandGroup>
              {options.map((o) => (
                <CommandItem
                  key={o.value} value={o.label}
                  onSelect={() => { onChange(o.value); setOpen(false) }}
                >
                  <Check className={cn(
                    "mr-2 size-4",
                    o.value === value ? "opacity-100" : "opacity-0",
                  )} />
                  {o.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
```

- [ ] **Step 2: Implement `date-range-field`**

```tsx
// src/components/common/date-range-field.tsx
import { CalendarIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover"

export type DateRange = { from?: Date; to?: Date }

function fmt(d?: Date) {
  return d ? d.toISOString().slice(0, 10) : "—"
}

export function DateRangeField({
  value, onChange,
}: { value: DateRange; onChange: (r: DateRange) => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-full justify-start font-normal">
          <CalendarIcon className="mr-2 size-4" />
          {fmt(value.from)} → {fmt(value.to)}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          selected={{ from: value.from, to: value.to }}
          onSelect={(r) =>
            onChange({ from: r?.from, to: r?.to })}
          numberOfMonths={2}
        />
      </PopoverContent>
    </Popover>
  )
}
```

- [ ] **Step 3: Verify build**

Run: `npx tsc -b && npx eslint src --max-warnings 0`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/components/common/combobox-field.tsx src/components/common/date-range-field.tsx
git commit -m "feat(ui): combobox-field + date-range-field composed patterns"
```

### Task 25: Hooks + invalidation helper

**Files:**
- Create: `src/shell/supervisor/hooks/invalidate-binding.ts`, `use-sections.ts`, `use-rooms.ts`, `use-stays.ts`

Use the project's API client (discover its export in Task 0c: `grep -n export src/lib/api-client.ts` — shown as `api`).

- [ ] **Step 1: Invalidation helper**

```ts
// src/shell/supervisor/hooks/invalidate-binding.ts
import type { QueryClient } from "@tanstack/react-query"

export function invalidateBinding(
  qc: QueryClient, keys: Array<"sections" | "rooms" | "stays">,
) {
  for (const k of keys) qc.invalidateQueries({ queryKey: [k] })
}
```

- [ ] **Step 2: `use-sections.ts`**

```ts
// src/shell/supervisor/hooks/use-sections.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Section = {
  id: string; label: string; room_count: number; created_at: string
}

export function useSections() {
  return useQuery({
    queryKey: ["sections"],
    queryFn: () => api.get<Section[]>("/supervisor/sections"),
  })
}

export function useCreateSection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (label: string) =>
      api.post<Section>("/supervisor/sections", { label }),
    onSuccess: () => invalidateBinding(qc, ["sections", "rooms", "stays"]),
  })
}

export function useRenameSection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; label: string }) =>
      api.patch<Section>(`/supervisor/sections/${v.id}`,
        { label: v.label }),
    onSuccess: () => invalidateBinding(qc, ["sections", "rooms", "stays"]),
  })
}
```

- [ ] **Step 3: `use-rooms.ts`**

```ts
// src/shell/supervisor/hooks/use-rooms.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Room = {
  id: string; label: string; section_id: string
  section_label: string; created_at: string
}

export function useRooms(sectionId?: string) {
  return useQuery({
    queryKey: ["rooms", { sectionId }],
    queryFn: () => api.get<Room[]>(
      `/supervisor/rooms${sectionId ? `?section_id=${sectionId}` : ""}`),
  })
}

export function useCreateRoom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { label: string; section_id: string }) =>
      api.post<Room>("/supervisor/rooms", v),
    onSuccess: () => invalidateBinding(qc, ["rooms", "sections", "stays"]),
  })
}

export function useUpdateRoom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: {
      id: string; label?: string; section_id?: string
    }) => api.patch<Room>(`/supervisor/rooms/${v.id}`,
      { label: v.label, section_id: v.section_id }),
    onSuccess: () => invalidateBinding(qc, ["rooms", "sections", "stays"]),
  })
}
```

- [ ] **Step 4: `use-stays.ts`**

```ts
// src/shell/supervisor/hooks/use-stays.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Stay = {
  id: string; guest_account_id: string; guest_display_name: string
  room_id: string; room_label: string; section_id: string
  section_label: string; check_in: string; check_out: string
  status: "active" | "ended"; created_at: string
}

export function useStays(status?: string, guestId?: string) {
  const q = new URLSearchParams()
  if (status) q.set("status", status)
  if (guestId) q.set("guest_id", guestId)
  const qs = q.toString()
  return useQuery({
    queryKey: ["stays", { status, guestId }],
    queryFn: () => api.get<Stay[]>(
      `/supervisor/stays${qs ? `?${qs}` : ""}`),
  })
}

export function useCreateStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: {
      guest_account_id: string; room_id: string
      check_in: string; check_out: string
    }) => api.post<Stay>("/supervisor/stays", v),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}

export function useRelocateStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; new_room_id: string }) =>
      api.post<Stay>(`/supervisor/stays/${v.id}/relocate`,
        { new_room_id: v.new_room_id }),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}

export function useCheckoutStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Stay>(`/supervisor/stays/${id}/checkout`, {}),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}

export function useUpdateStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: {
      id: string; check_in?: string; check_out?: string
    }) => api.patch<Stay>(`/supervisor/stays/${v.id}`,
      { check_in: v.check_in, check_out: v.check_out }),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}
```

- [ ] **Step 5: Verify build, commit**

Run: `npx tsc -b && npx eslint src --max-warnings 0`
Expected: clean.

```bash
git add src/shell/supervisor/hooks/invalidate-binding.ts src/shell/supervisor/hooks/use-sections.ts src/shell/supervisor/hooks/use-rooms.ts src/shell/supervisor/hooks/use-stays.ts
git commit -m "feat(supervisor/hooks): sections/rooms/stays + invalidation helper"
```

### Task 26: Sections page (accordion + room chips)

**Files:**
- Create: `src/shell/supervisor/pages/sections.tsx`

- [ ] **Step 1: Implement**

```tsx
// src/shell/supervisor/pages/sections.tsx
import { useState } from "react"
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { Skeleton } from "@/components/ui/skeleton"
import {
  useSections, useCreateSection, useRenameSection,
} from "@/shell/supervisor/hooks/use-sections"
import {
  useRooms, useCreateRoom, useUpdateRoom,
} from "@/shell/supervisor/hooks/use-rooms"

function RoomChips({ sectionId }: { sectionId: string }) {
  const rooms = useRooms(sectionId)
  const createRoom = useCreateRoom()
  const [label, setLabel] = useState("")
  if (rooms.isLoading) return <Skeleton className="h-8 w-full" />
  if (rooms.isError) return <ErrorState onRetry={rooms.refetch} />
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {(rooms.data ?? []).map((r) => (
          <span key={r.id}
            className="border-border rounded-md border px-2 py-1
                       text-xs font-medium">
            {r.label}
          </span>
        ))}
        {rooms.data?.length === 0 && (
          <span className="text-muted-foreground text-xs">No rooms yet.</span>
        )}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (!label.trim()) return
          createRoom.mutate(
            { label: label.trim(), section_id: sectionId },
            { onSuccess: () => setLabel("") },
          )
        }}
      >
        <Input value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder="Add room (e.g. 304)" className="h-9 max-w-[12rem]" />
        <Button type="submit" size="sm" disabled={createRoom.isPending}>
          {createRoom.isPending ? "Adding…" : "Add room"}
        </Button>
      </form>
    </div>
  )
}

export function SectionsPage() {
  const sections = useSections()
  const createSection = useCreateSection()
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState("")

  const total = sections.data?.length ?? 0
  const rooms = (sections.data ?? []).reduce(
    (n, s) => n + s.room_count, 0)

  return (
    <div className="mx-auto w-full max-w-4xl space-y-4">
      <PageHeader
        title="Sections"
        description={`${total} sections · ${rooms} rooms`}
        action={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button>New section</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>New section</DialogTitle></DialogHeader>
              <Input value={label} onChange={(e) => setLabel(e.target.value)}
                placeholder="Section label (e.g. North Wing)" />
              <DialogFooter>
                <Button
                  disabled={createSection.isPending || !label.trim()}
                  onClick={() =>
                    createSection.mutate(label.trim(), {
                      onSuccess: () => { setLabel(""); setOpen(false) },
                    })}
                >
                  {createSection.isPending ? "Creating…" : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        }
      />
      {sections.isLoading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      )}
      {sections.isError && <ErrorState onRetry={sections.refetch} />}
      {sections.data?.length === 0 && (
        <EmptyState title="No sections yet"
          description="Create a section to start mapping rooms." />
      )}
      {!!sections.data?.length && (
        <Accordion type="multiple" className="w-full">
          {sections.data.map((s) => (
            <AccordionItem key={s.id} value={s.id}>
              <AccordionTrigger className="text-sm">
                <span className="flex w-full items-center justify-between
                                 pr-3">
                  <RenamableLabel id={s.id} label={s.label} />
                  <span className="text-muted-foreground text-xs">
                    {s.room_count} rooms
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <RoomChips sectionId={s.id} />
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      )}
    </div>
  )
}

function RenamableLabel({ id, label }: { id: string; label: string }) {
  const rename = useRenameSection()
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(label)
  if (!editing)
    return (
      <span onClick={(e) => { e.stopPropagation(); setEditing(true) }}
        className="font-medium">{label}</span>
    )
  return (
    <Input
      autoFocus value={val}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setVal(e.target.value)}
      onBlur={() => {
        setEditing(false)
        if (val.trim() && val !== label)
          rename.mutate({ id, label: val.trim() })
      }}
      className="h-7 max-w-[14rem]"
    />
  )
}

// Re-exported via useUpdateRoom for the room reassign action used elsewhere.
export { useUpdateRoom }
```

- [ ] **Step 2: Verify build, commit**

Run: `npx tsc -b && npx eslint src --max-warnings 0`
Expected: clean (if `PageHeader`/`EmptyState`/`ErrorState` import paths differ, use the auth-provided paths discovered in Task 0c).

```bash
git add src/shell/supervisor/pages/sections.tsx
git commit -m "feat(supervisor/pages): Sections (accordion + room chips)"
```

### Task 27: Provisioning / Check-in page

**Files:**
- Create: `src/shell/supervisor/pages/provisioning.tsx`

Reuse the auth slice's `useAccounts` hook (discover its path/signature in Task 0c — shown as `useAccounts` from `@/shell/supervisor/hooks/use-accounts`) and `confirm`/`data-table-shell` primitives.

- [ ] **Step 1: Implement**

```tsx
// src/shell/supervisor/pages/provisioning.tsx
import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogФooter as _, DialogFooter, DialogHeader,
  DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { confirm } from "@/components/common/confirm"
import { ComboboxField } from "@/components/common/combobox-field"
import { DateRangeField } from "@/components/common/date-range-field"
import {
  useStays, useCreateStay, useRelocateStay, useCheckoutStay,
} from "@/shell/supervisor/hooks/use-stays"
import { useRooms } from "@/shell/supervisor/hooks/use-rooms"
import { useAccounts } from "@/shell/supervisor/hooks/use-accounts"

export function ProvisioningPage() {
  const [statusFilter, setStatusFilter] =
    useState<"active" | "ended" | "">("active")
  const stays = useStays(statusFilter || undefined)
  const rooms = useRooms()
  const guests = useAccounts("guest")
  const createStay = useCreateStay()
  const relocate = useRelocateStay()
  const checkout = useCheckoutStay()
  const [open, setOpen] = useState(false)

  const activeGuestIds = useMemo(
    () => new Set((useStays("active").data ?? [])
      .map((s) => s.guest_account_id)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stays.data],
  )
  const guestOptions = (guests.data ?? [])
    .filter((g: { id: string }) => !activeGuestIds.has(g.id))
    .map((g: { id: string; display_name: string }) =>
      ({ value: g.id, label: g.display_name }))
  const roomOptions = (rooms.data ?? []).map(
    (r) => ({ value: r.id, label: `${r.label} · ${r.section_label}` }))

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4">
      <PageHeader
        title="Provisioning"
        description={`${stays.data?.length ?? 0} ${statusFilter || "all"} stays`}
        action={
          <CheckInDialog open={open} setOpen={setOpen}
            guestOptions={guestOptions} roomOptions={roomOptions}
            onCreate={(v) => createStay.mutate(v, {
              onSuccess: () => setOpen(false),
            })}
            pending={createStay.isPending} />
        }
      />
      <div className="flex gap-2">
        {(["active", "ended", ""] as const).map((s) => (
          <Button key={s || "all"}
            variant={statusFilter === s ? "default" : "outline"}
            size="sm" onClick={() => setStatusFilter(s)}>
            {s === "" ? "All" : s[0].toUpperCase() + s.slice(1)}
          </Button>
        ))}
      </div>
      <DataTableShell
        query={stays}
        columns={["Guest", "Room", "Section", "Dates", "Status", ""]}
        renderRow={(st) => [
          st.guest_display_name,
          st.room_label,
          st.section_label,
          `${st.check_in.slice(0, 10)} → ${st.check_out.slice(0, 10)}`,
          <span className="flex items-center gap-1 text-xs">
            <span className={st.status === "active"
              ? "text-foreground" : "text-muted-foreground"}>●</span>
            {st.status}
          </span>,
          st.status === "active" ? (
            <RowActions
              roomOptions={roomOptions.filter((o) => o.value !== st.room_id)}
              current={`${st.room_label} · ${st.section_label}`}
              onMove={(rid) =>
                relocate.mutate({ id: st.id, new_room_id: rid })}
              onCheckout={async () => {
                if (await confirm({
                  title: "Check out?",
                  description: `End ${st.guest_display_name}'s stay.`,
                })) checkout.mutate(st.id)
              }}
            />
          ) : <Badge variant="outline">ended</Badge>,
        ]}
      />
    </div>
  )
}

function CheckInDialog({
  open, setOpen, guestOptions, roomOptions, onCreate, pending,
}: {
  open: boolean; setOpen: (b: boolean) => void
  guestOptions: { value: string; label: string }[]
  roomOptions: { value: string; label: string }[]
  onCreate: (v: {
    guest_account_id: string; room_id: string
    check_in: string; check_out: string
  }) => void
  pending: boolean
}) {
  const [guest, setGuest] = useState<string | null>(null)
  const [room, setRoom] = useState<string | null>(null)
  const [range, setRange] = useState<{ from?: Date; to?: Date }>({})
  const valid = guest && room && range.from && range.to
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button>Check in guest</Button></DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Check in guest</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <ComboboxField options={guestOptions} value={guest}
            onChange={setGuest} placeholder="Select guest"
            emptyText="No guests without an active stay" />
          <ComboboxField options={roomOptions} value={room}
            onChange={setRoom} placeholder="Select room" />
          <DateRangeField value={range} onChange={setRange} />
        </div>
        <DialogFooter>
          <Button disabled={!valid || pending} onClick={() => onCreate({
            guest_account_id: guest!, room_id: room!,
            check_in: range.from!.toISOString(),
            check_out: range.to!.toISOString(),
          })}>
            {pending ? "Checking in…" : "Check in"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RowActions({
  roomOptions, current, onMove, onCheckout,
}: {
  roomOptions: { value: string; label: string }[]
  current: string
  onMove: (roomId: string) => void
  onCheckout: () => void
}) {
  const [moveOpen, setMoveOpen] = useState(false)
  const [target, setTarget] = useState<string | null>(null)
  return (
    <div className="flex justify-end gap-2">
      <Dialog open={moveOpen} onOpenChange={setMoveOpen}>
        <DialogTrigger asChild>
          <Button size="sm" variant="outline">Move</Button>
        </DialogTrigger>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Move guest</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="text-muted-foreground">
              {current} <span className="px-1">▶</span> new room
            </div>
            <ComboboxField options={roomOptions} value={target}
              onChange={setTarget} placeholder="Select new room" />
            <p className="text-muted-foreground text-xs">
              Re-binds the guest's room immediately. They see it on next
              refresh — no re-login.
            </p>
          </div>
          <DialogFooter>
            <Button disabled={!target} onClick={() => {
              onMove(target!); setMoveOpen(false)
            }}>Move</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Button size="sm" variant="ghost" onClick={onCheckout}>
        Check out
      </Button>
    </div>
  )
}
```

> If `DataTableShell` / `confirm` / `PageHeader` / `useAccounts` expose a different API than assumed, adapt the call sites to the **discovered** auth-provided signatures from Task 0c — do not fork parallel primitives. Remove the stray `DialogФooter as _` import line (it is intentionally invalid to force you to align imports with the real `dialog` exports — replace the whole import with the actual exports of `@/components/ui/dialog`).

- [ ] **Step 2: Verify build, commit**

Run: `npx tsc -b && npx eslint src --max-warnings 0`
Expected: clean after aligning the imports above.

```bash
git add src/shell/supervisor/pages/provisioning.tsx
git commit -m "feat(supervisor/pages): Provisioning/Check-in (table + move + checkout + check-in dialog)"
```

### Task 28: Routes + nav wiring

**Files:**
- Modify: `src/shell/supervisor/nav.tsx`, `src/App.tsx`

- [ ] **Step 1: Add the routes**

In `src/App.tsx`, register inside the supervisor shell route subtree:

```tsx
// import the pages
import { SectionsPage } from "@/shell/supervisor/pages/sections"
import { ProvisioningPage } from "@/shell/supervisor/pages/provisioning"

// within the supervisor <Route> children:
<Route path="setup/sections" element={<SectionsPage />} />
<Route path="provisioning" element={<ProvisioningPage />} />
```

(Match the existing routing structure; the supervisor base path is `/supervisor`.)

- [ ] **Step 2: Point the nav entries**

In `src/shell/supervisor/nav.tsx`, change the Setup submenu's `Sections & Rosters` item to a `Sections` item at `/supervisor/setup/sections` (leave a `Rosters` placeholder item that routes nowhere yet or is omitted — do not invent a rosters page). The existing `Guest Provisioning` item already points to `/supervisor/provisioning`; leave it.

```tsx
      items: [
        { title: "Sections", url: "/supervisor/setup/sections" },
        { title: "Issue Codes", url: "/supervisor/setup/issue-codes" },
        { title: "SLA Presets", url: "/supervisor/setup/sla" },
        { title: "Escalation Ladder", url: "/supervisor/setup/escalation" },
      ],
```

- [ ] **Step 3: Verify build, commit**

Run: `npx tsc -b && npx eslint src --max-warnings 0 && npx vite build`
Expected: clean; production build succeeds.

```bash
git add src/App.tsx src/shell/supervisor/nav.tsx
git commit -m "feat(supervisor): wire Sections + Provisioning routes/nav"
```

---

# PHASE 3 — Finalize: full bench, push, PR

### Task 29: Full verification

- [ ] **Step 1: Backend bench**

```bash
cd /workspace/Conduit-stay-binding/backend
./.venv/bin/pytest -q --cov
```
Expected: all green, coverage gate satisfied, leak sentinel silent.

- [ ] **Step 2: Frontend**

```bash
cd /workspace/Conduit-stay-binding/frontend
npx tsc -b && npx eslint src --max-warnings 0 && npx vite build
```
Expected: clean; build succeeds.

- [ ] **Step 3: Verify nothing uncommitted**

```bash
cd /workspace/Conduit-stay-binding
git status -s   # expect empty
```

### Task 30: Push and open the PR

- [ ] **Step 1: Push the branch**

```bash
cd /workspace/Conduit-stay-binding
git push -u origin feat/stay-binding
```

- [ ] **Step 2: Open the PR**

Base branch = `feat/auth-slice` (this stacks on it). If `feat/auth-slice` has already merged to `main` by now, rebase onto `main` first (`git fetch origin && git rebase origin/main`) and target `main` instead.

```bash
gh pr create \
  --base feat/auth-slice \
  --head feat/stay-binding \
  --title "Stay/Binding slice — check-in & relocation" \
  --body "$(cat <<'EOF'
Implements the Stay/Room/Section binding slice per
docs/superpowers/specs/2026-05-16-stay-binding-design.md.

- Relational models: Property/Section/Room/Stay + generic event base
  + 3 detail tables. No jsonb. No DELETE. Second migration with the
  partial unique index enforcing one active stay per guest.
- Supervisor portal: sections/rooms/stays CRUD + relocate/checkout
  action endpoints. public/auth `/auth/me` extended with guest
  ambient {room,section,stay}, re-resolved per request (no re-login).
- Frontend: Sections (accordion + room chips) and Provisioning
  (table + Move/Check-out + Check-in dialog) on the auth uniformity
  layer; combobox-field + date-range-field composed patterns.
- Test bench: layered (migration/DAL/services/API) + structural
  guards (contract snapshot owns the extended /auth/me, response
  schema, role×endpoint, coverage gate, leak sentinel) + named
  invariants + an end-to-end journey sentinel.

Stacks on `feat/auth-slice`. Coordinate at that merge: the `/auth/me`
contract-snapshot bump, the design-system tightness pass, and the
test-isolation upgrade to savepoint-rollback (all noted in the spec
§12).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Report the PR URL**

```bash
gh pr view --json url -q .url
```

---

## Self-review checklist (performed)

- **Spec coverage:** every spec section maps to tasks — models/§5→T1-4; migration+index→T5; harness/isolation→T6; DAL→T7-11; services+guards→T12-14; ambient seam §6→T15,T19; schemas+AuthUser→T16; API §8→T17-18; hooks §9→T25; components §9→T23-24; pages §9→T26-27; nav→T28; test bench §10 (layered+6 guards+e2e+invariants)→T6,T20; verification bar §11→T29; deferred items remain deferred (no tasks, by design).
- **Placeholder scan:** no TBD/TODO; discovery commands are deterministic, not placeholders; the two intentionally-invalid frontend import lines are explicitly called out as forcing functions to align with discovered exports.
- **Type consistency:** service signatures (`actor` kwarg), DAL return types, schema field names, and hook `Stay`/`Section`/`Room` shapes match across tasks and the API `*_out` mappers.
