# Staffing & Availability Slice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the routing-precondition slice — the supervisor declares the operational staffing structure (staff class/skills + time-bounded rosters with section owner/backup) and the servicer declares presence; the system exposes a pure, derived effective-availability predicate that the next slice's routing consumes.

**Architecture:** Async `api → services → dal → shared/models`; CONFIG entities in the merged `issue_code.py` idiom (uuid pk, `text+CHECK`, no jsonb, disable-not-delete); the effective-availability rule is a **pure, no-DB** `shared/domain/availability.py` module (the substrate this slice exists to create); config-mutation events are appended via the merged `shared/events` writer directly (not the child state machine); supervisor owns staff/roster, servicer owns its own reads + presence (self-scoped DAL, no cross-portal import). Stacks on the merged auth + stay/binding + no-dispatch state with zero auth-owned changes.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, Postgres, pytest/pytest-asyncio/httpx, freezegun, React + TanStack Query + shadcn/Tailwind.

**Source of truth:** `docs/superpowers/specs/2026-05-16-staffing-availability-design.md` (read it fully before starting). Decision IDs (D-series / AD-series) referenced here are defined in `docs/datamodels/` and `docs/archi/` inside this repo. Do **not** look for any product-spec folder outside this repository — everything needed is in `docs/` here.

---

## Preconditions (read before Task 0)

- This plan **executes after the no-dispatch slice is merged to `main`**. Do not start until `git -C /workspace/Conduit log --oneline main` shows the no-dispatch merge: the `0003_nodispatch` migration, `backend/conduit/shared/events/` writer, `backend/conduit/shared/models/issue_code.py`, `backend/tests/spine/conftest.py`, and the frontend `src/shell/supervisor/pages/issue-codes.tsx` all present on `main`.
- All work happens in an **isolated worktree** created in Task 0. Never edit `/workspace/Conduit` directly.
- Postgres + the test DB tooling are as configured in the merged `tests/spine/conftest.py`.

## Subagent rules (if dispatched)

- **Every subagent MUST be an Opus subagent** (`model: "opus"`). Never sonnet or haiku for any task in this plan — no exceptions.
- Every dispatch MUST copy the task's **Files** block verbatim into the dispatch prompt and instruct the subagent to create/modify/test **only** those files and touch nothing else.
- Every dispatch MUST tell the subagent the worktree path is `/workspace/Conduit-staffing` and that **all** commands run from there using that worktree's `.venv`.
- Every dispatch MUST instruct the subagent to read the spec section named in the task before coding, and to read the named merged exemplar file(s) before cloning their pattern.
- Subagents must never reference or search for any directory outside `/workspace/Conduit-staffing`; all decision context is in `docs/` inside the worktree.

---

## File Structure (decomposition lock-in)

```
backend/conduit/shared/models/   staff_profile.py staff_skill.py roster.py
                                  roster_assignment.py
                                  event.py (modify) __init__.py (modify)
backend/conduit/shared/domain/   availability.py (new — pure, no DB)
backend/conduit/core/            clock.py (new — the single Python now() call site)
backend/conduit/supervisor/dal/  staff.py rosters.py
backend/conduit/supervisor/services/ staff.py rosters.py
backend/conduit/supervisor/schemas/  staff.py roster.py
backend/conduit/supervisor/api/  staff.py rosters.py __init__.py (modify)
backend/conduit/servicer/dal/    self.py
backend/conduit/servicer/services/ home.py presence.py
backend/conduit/servicer/schemas/ home.py
backend/conduit/servicer/api/    self.py __init__.py (modify or create)
backend/migrations/versions/     0004_staffing.py
backend/tests/spine/             test_staffing_models.py test_availability.py
                                  test_staffing_dal.py test_staffing_services.py
                                  test_staffing_api.py test_staffing_structural.py
                                  test_e2e_staffing.py
frontend/src/components/ui/      toggle-group.tsx toggle.tsx (shadcn add)
frontend/src/components/common/  staff-profile-form-dialog.tsx skills-field.tsx
                                  roster-window-form-dialog.tsx assignment-editor.tsx
                                  presence-control.tsx shift-card.tsx
                                  staff-presence-cell.tsx
frontend/src/shell/supervisor/   pages/staff.tsx pages/rosters.tsx
                                  hooks/use-staff.ts hooks/use-rosters.ts
frontend/src/shell/servicer/     index.tsx (replace) nav.tsx (replace)
                                  hooks/use-servicer.ts (replace)
frontend/src/components/layout/nav-config.ts (verify shape only)
frontend/src/shell/supervisor/nav.tsx (modify — add Staff + Rosters)
frontend/src/App.tsx             (modify — routes)
```

---

## Task 0: Worker setup — worktree, venv, env files

**Files:**
- Create: worktree at `/workspace/Conduit-staffing` (branch `feat/staffing-availability`)
- Copy: `/workspace/Conduit/backend/.env`, `/workspace/Conduit/frontend/.env`

- [ ] **Step 1: Confirm no-dispatch is merged**

Run:
```bash
git -C /workspace/Conduit fetch origin
git -C /workspace/Conduit log --oneline -8 origin/main
test -f /workspace/Conduit/backend/migrations/versions/0003_nodispatch.py && echo OK_0003
test -f /workspace/Conduit/backend/conduit/shared/models/issue_code.py && echo OK_ISSUECODE
test -d /workspace/Conduit/backend/conduit/shared/events && echo OK_EVENTS
test -f /workspace/Conduit/backend/tests/spine/conftest.py && echo OK_CONFTEST
test -f /workspace/Conduit/frontend/src/shell/supervisor/pages/issue-codes.tsx && echo OK_ISSUECODESPAGE
```
Expected: `OK_0003`, `OK_ISSUECODE`, `OK_EVENTS`, `OK_CONFTEST`, `OK_ISSUECODESPAGE` all printed. If any is missing, STOP — the precondition is unmet.

- [ ] **Step 2: Create the isolated worktree off latest main**

Run:
```bash
git -C /workspace/Conduit worktree add -b feat/staffing-availability /workspace/Conduit-staffing origin/main
git -C /workspace/Conduit-staffing branch --show-current
```
Expected: `feat/staffing-availability`.

- [ ] **Step 3: Copy env files into the worktree**

Run:
```bash
cp /workspace/Conduit/backend/.env /workspace/Conduit-staffing/backend/.env
cp /workspace/Conduit/frontend/.env /workspace/Conduit-staffing/frontend/.env
ls -1 /workspace/Conduit-staffing/backend/.env /workspace/Conduit-staffing/frontend/.env
```
Expected: both paths listed.

- [ ] **Step 4: Create the worktree venv using the existing interpreter as source**

The source interpreter is `/workspace/Conduit/backend/.venv`. Create a fresh venv in the worktree from it, then install the project editable plus `freezegun`:
```bash
cd /workspace/Conduit-staffing/backend
/workspace/Conduit/backend/.venv/bin/python -m venv .venv
.venv/bin/python -m pip install -q -e ".[dev]"
.venv/bin/python -m pip install -q freezegun
.venv/bin/python -c "import conduit, fastapi, sqlalchemy, alembic, httpx, freezegun; print('env OK')"
```
Expected: `env OK`.

- [ ] **Step 5: Add `freezegun` to dev dependencies**

In `/workspace/Conduit-staffing/backend/pyproject.toml`, add `"freezegun"` to the `[project.optional-dependencies] dev` list (alphabetically, matching the existing formatting). This makes the new dependency reproducible — do not rely only on the manual pip install.

- [ ] **Step 6: Baseline the suite (must be green before any change)**

Run:
```bash
cd /workspace/Conduit-staffing/backend && .venv/bin/pytest -q
```
Expected: PASS (the merged auth + stay/binding + no-dispatch suite). If red, STOP and report — do not build on a red baseline.

- [ ] **Step 7: Commit the dependency addition only**

```bash
cd /workspace/Conduit-staffing
git add backend/pyproject.toml
git commit -m "chore: add freezegun dev dependency (staffing time-control)"
```

---

## Task 1: Supervisor tightening micro-sweep (isolated drift-only commit — spec §10/§13)

**Files:**
- Modify (drift-only, zero behaviour change): any older `frontend/src/shell/supervisor/pages/*.tsx` that uses `rounded-xl` on a card/row container or hand-rolled `<p>Loading…</p>`/`<p className="text-destructive">` state strings instead of `DataTableShell`/`EmptyState`/`ErrorState`.
- Verify: `frontend` build.

Read spec §10 "Cleanup" first. This commit ONLY tightens visual/state drift so the new Staff/Rosters pages do not sit next to inconsistent siblings. No data, prop, or behaviour change.

- [ ] **Step 1: Find drift**

Run:
```bash
cd /workspace/Conduit-staffing/frontend
grep -rn "rounded-xl" src/shell/supervisor/pages || echo "no rounded-xl"
grep -rn "Loading…\|Loading\.\.\.\|text-destructive text-sm" src/shell/supervisor/pages || echo "no hand-rolled states"
```
Record the matches. If both print the "no …" lines, there is no drift — skip to Step 4 and do not create an empty commit.

- [ ] **Step 2: Tighten each match**

For each matched container: replace `rounded-xl` with `rounded-lg` (the `data-table-shell` idiom). For each hand-rolled loading/error/empty block in a list page: replace with the `DataTableShell` `state` prop pattern exactly as `src/shell/supervisor/pages/issue-codes.tsx` uses it (read that file first; mirror its `state = q.isLoading ? "loading" : q.isError ? "error" : (q.data?.length ?? 0) === 0 ? "empty" : "ready"` shape). Change nothing else — no columns, no copy, no data flow.

- [ ] **Step 3: Verify build**

Run:
```bash
cd /workspace/Conduit-staffing/frontend && npm install && npm run build
```
Expected: typecheck + build succeed.

- [ ] **Step 4: Commit (only if Step 1 found drift)**

```bash
cd /workspace/Conduit-staffing
git add frontend/src/shell/supervisor/pages
git commit -m "style(ui): tighten supervisor page drift (rounded-lg, uniform states)"
```

---

## Task 2: Models + migration `0004`

**Files:**
- Create: `backend/conduit/shared/models/staff_profile.py`, `staff_skill.py`, `roster.py`, `roster_assignment.py`
- Modify: `backend/conduit/shared/models/event.py` (extend CHECK + 8 detail classes), `backend/conduit/shared/models/__init__.py`
- Create: `backend/migrations/versions/0004_staffing.py`
- Test: `backend/tests/spine/test_staffing_models.py`

Read spec §6 first. Read the merged `backend/conduit/shared/models/issue_code.py` and `backend/conduit/shared/models/event.py` and copy their exact idiom (`UUID(as_uuid=True)`, `DateTime(timezone=True)`, `String`, `CheckConstraint`, `func.now()`, `server_default`).

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/spine/test_staffing_models.py`:
```python
from conduit.shared.models import (
    StaffProfile, StaffSkill, Roster, RosterAssignment, Event,
    EventStaffProfileCreated, EventStaffProfileUpdated, EventStaffSkillsSet,
    EventRosterCreated, EventRosterUpdated,
    EventAssignmentCreated, EventAssignmentUpdated, EventPresenceChanged,
)


def test_staffing_models_registered():
    assert StaffProfile.__tablename__ == "staff_profile"
    assert StaffSkill.__tablename__ == "staff_skill"
    assert Roster.__tablename__ == "roster"
    assert RosterAssignment.__tablename__ == "roster_assignment"
    assert EventPresenceChanged.__tablename__ == "event_presence_changed"
    assert EventAssignmentCreated.__tablename__ == "event_assignment_created"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_models.py -q`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Create `staff_profile.py`**

```python
# conduit/shared/models/staff_profile.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, String, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class StaffProfile(Base):
    __tablename__ = "staff_profile"
    __table_args__ = (
        CheckConstraint(
            "staff_class in "
            "('housekeeping','engineering','room_service','concierge','runner')",
            name="ck_staff_profile_class",
        ),
        CheckConstraint(
            "presence in ('working','on_break','off')",
            name="ck_staff_profile_presence",
        ),
        CheckConstraint(
            "status in ('active','disabled')",
            name="ck_staff_profile_status",
        ),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), primary_key=True,
    )
    staff_class: Mapped[str] = mapped_column(String, nullable=False)
    presence: Mapped[str] = mapped_column(
        String, nullable=False, server_default="working",
    )
    presence_set_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="active",
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
```

- [ ] **Step 4: Create `staff_skill.py`**

```python
# conduit/shared/models/staff_skill.py
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class StaffSkill(Base):
    __tablename__ = "staff_skill"
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), primary_key=True,
    )
    skill: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
```

- [ ] **Step 5: Create `roster.py`**

```python
# conduit/shared/models/roster.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class Roster(Base):
    __tablename__ = "roster"
    __table_args__ = (
        CheckConstraint("shift_end > shift_start", name="ck_roster_window"),
        CheckConstraint(
            "status in ('active','disabled')", name="ck_roster_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id"), nullable=False,
    )
    shift_start: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    shift_end: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="active",
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
```

- [ ] **Step 6: Create `roster_assignment.py`**

```python
# conduit/shared/models/roster_assignment.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, String, func, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from conduit.shared.db import Base


class RosterAssignment(Base):
    __tablename__ = "roster_assignment"
    __table_args__ = (
        CheckConstraint(
            "assignment in ('owner','backup','member')",
            name="ck_assignment_role",
        ),
        CheckConstraint(
            "status in ('active','disabled')", name="ck_assignment_status",
        ),
        CheckConstraint(
            "assignment not in ('owner','backup') OR section_id IS NOT NULL",
            name="ck_assignment_owner_needs_section",
        ),
        Index(
            "uq_active_owner_per_section",
            "roster_id", "section_id",
            unique=True,
            postgresql_where=text("assignment = 'owner' AND status = 'active'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    roster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster.id"), nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("section.id"), nullable=True,
    )
    assignment: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="active",
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
```

- [ ] **Step 7: Extend `event.py`**

Open `backend/conduit/shared/models/event.py`. Find the `CheckConstraint` enumerating `event.type` values. Append these 8 to the allowed list (keep existing values, comma-separated, same formatting): `staff_profile_created`, `staff_profile_updated`, `staff_skills_set`, `roster_created`, `roster_updated`, `assignment_created`, `assignment_updated`, `presence_changed`.

Then append 8 thin detail classes following the exact shape of the existing `EventStayCreated` class in that file (one `event_id` uuid pk fk→`event.id`, plus the typed fk shown):

```python
class EventStaffProfileCreated(Base):
    __tablename__ = "event_staff_profile_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )


class EventStaffProfileUpdated(Base):
    __tablename__ = "event_staff_profile_updated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )


class EventStaffSkillsSet(Base):
    __tablename__ = "event_staff_skills_set"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )


class EventRosterCreated(Base):
    __tablename__ = "event_roster_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    roster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster.id"), nullable=False,
    )


class EventRosterUpdated(Base):
    __tablename__ = "event_roster_updated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    roster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster.id"), nullable=False,
    )


class EventAssignmentCreated(Base):
    __tablename__ = "event_assignment_created"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_assignment.id"), nullable=False,
    )


class EventAssignmentUpdated(Base):
    __tablename__ = "event_assignment_updated"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roster_assignment.id"), nullable=False,
    )


class EventPresenceChanged(Base):
    __tablename__ = "event_presence_changed"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event.id"), primary_key=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id"), nullable=False,
    )
```

Confirm `uuid`, `Mapped`, `mapped_column`, `UUID`, `ForeignKey`, `Base` are imported at the top of `event.py` (they already are for the existing detail classes — add nothing new).

- [ ] **Step 8: Register in `__init__.py`**

In `backend/conduit/shared/models/__init__.py`, add imports for the 4 entities + 8 event detail classes and add every new name to `__all__`. Keep the firm import order the file documents: `event` first, then `staff_profile`, `staff_skill`, `roster`, `roster_assignment`.

- [ ] **Step 9: Run the model test (passes)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_models.py -q`
Expected: PASS.

- [ ] **Step 10: Generate the migration**

Run:
```bash
cd /workspace/Conduit-staffing/backend
.venv/bin/alembic revision --autogenerate -m "staffing" --rev-id 0004_staffing
```
Open the generated `backend/migrations/versions/0004_staffing.py`. Verify: `down_revision = "0003_nodispatch"`; `upgrade()` creates the 4 tables, the 8 event detail tables, and the partial unique index `uq_active_owner_per_section` (with the `postgresql_where`); the `event` type CHECK is altered to include the 8 new values (autogenerate may not diff a CHECK string — if the `event` CHECK is not altered, add an explicit `op.drop_constraint`/`op.create_constraint` for the `event` type check mirroring how `0003_nodispatch.py` did it; read `0003_nodispatch.py` for the exact pattern). Ensure `downgrade()` reverses everything (drop in FK-safe order, restore the prior `event` CHECK).

- [ ] **Step 11: Write the migration round-trip + invariant test**

Append to `backend/tests/spine/test_staffing_models.py`:
```python
import subprocess

def test_migration_round_trip():
    # up to head, then one step down, then back up — must not error
    base = "/workspace/Conduit-staffing/backend"
    env = {"PATH": "/usr/bin:/bin"}
    for args in (["upgrade", "head"], ["downgrade", "-1"], ["upgrade", "head"]):
        r = subprocess.run(
            [f"{base}/.venv/bin/alembic", *args],
            cwd=base, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
```
(Physical-invariant rejection — 2nd profile, dup skill, 2nd active owner, owner-without-section — is exercised at the DAL/service layer in Task 6's tests against the live schema; this step only guards the migration applies and reverses.)

- [ ] **Step 12: Run it**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_models.py -q`
Expected: PASS.

- [ ] **Step 13: Commit**

```bash
cd /workspace/Conduit-staffing
git add backend/conduit/shared/models backend/migrations/versions/0004_staffing.py backend/tests/spine/test_staffing_models.py
git commit -m "feat(models): staffing entities + migration 0004"
```

---

## Task 3: The pure availability predicate (`shared/domain/availability.py`)

**Files:**
- Create: `backend/conduit/shared/domain/availability.py`
- Test: `backend/tests/spine/test_availability.py`

Read spec §7 first. This module is **pure — no DB, no imports from `conduit.shared.db` or any DAL**. It takes already-fetched ORM rows and an explicit `now`.

- [ ] **Step 1: Write the exhaustive failing test**

Create `backend/tests/spine/test_availability.py`:
```python
import datetime as dt
import uuid
import pytest

from conduit.shared.domain.availability import (
    current_window, on_shift, effective_available,
)


class _Roster:
    def __init__(self, start, end, status="active"):
        self.id = uuid.uuid4()
        self.shift_start, self.shift_end, self.status = start, end, status


class _Assignment:
    def __init__(self, roster, status="active"):
        self.roster = roster
        self.status = status


class _Profile:
    def __init__(self, presence="working", set_at=None, status="active"):
        self.presence, self.presence_set_at, self.status = (
            presence, set_at, status,
        )


UTC = dt.timezone.utc
START = dt.datetime(2026, 5, 16, 8, 0, tzinfo=UTC)
END = dt.datetime(2026, 5, 16, 16, 0, tzinfo=UTC)
MID = dt.datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
BEFORE = dt.datetime(2026, 5, 16, 6, 0, tzinfo=UTC)


def _assignments(status="active", rstatus="active"):
    return [_Assignment(_Roster(START, END, rstatus), status)]


@pytest.mark.parametrize(
    "now,presence,set_at,prof_status,asg_status,expected",
    [
        # off-shift → never available
        (BEFORE, "working", None, "active", "active", False),
        # on-shift, never toggled → working default (D39-literal)
        (MID, "working", None, "active", "active", True),
        # on-shift, on_break set this window → unavailable
        (MID, "on_break", MID, "active", "active", False),
        (MID, "off", MID, "active", "active", False),
        # on-shift, on_break but set BEFORE this window → ignored ⇒ available
        (MID, "on_break", BEFORE, "active", "active", True),
        # on-shift, working, disabled profile → unavailable
        (MID, "working", None, "disabled", "active", False),
        # on-shift but assignment disabled → not on shift ⇒ unavailable
        (MID, "working", None, "active", "disabled", False),
        # boundary: exactly shift_start → on shift (half-open [start,end))
        (START, "working", None, "active", "active", True),
        # boundary: exactly shift_end → NOT on shift
        (END, "working", None, "active", "active", False),
        # boundary: presence_set_at == shift_start (in window) → counts
        (MID, "off", START, "active", "active", False),
        # boundary: presence_set_at == shift_end (NOT in [start,end)) → ignored
        (MID, "off", END, "active", "active", True),
    ],
)
def test_effective_available(
    now, presence, set_at, prof_status, asg_status, expected
):
    asgs = _assignments(asg_status)
    prof = _Profile(presence, set_at, prof_status)
    assert effective_available(prof, asgs, now) is expected


def test_current_window_and_on_shift():
    asgs = _assignments()
    assert on_shift(asgs, MID) is True
    assert on_shift(asgs, BEFORE) is False
    assert current_window(asgs, MID) is asgs[0].roster
    assert current_window(asgs, BEFORE) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_availability.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `availability.py`**

```python
# conduit/shared/domain/availability.py
"""Pure derived availability — no DB. The substrate routing consumes.

current_window/on_shift/effective_available take already-fetched rows
(assignments each carrying `.roster`, a profile) plus an explicit `now`.
The window is half-open: now in [shift_start, shift_end).
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional, Protocol


class _Roster(Protocol):
    shift_start: dt.datetime
    shift_end: dt.datetime
    status: str


class _Assignment(Protocol):
    roster: _Roster
    status: str


class _Profile(Protocol):
    presence: str
    presence_set_at: Optional[dt.datetime]
    status: str


def current_window(
    assignments: Iterable[_Assignment], now: dt.datetime
) -> Optional[_Roster]:
    for a in assignments:
        if a.status != "active":
            continue
        r = a.roster
        if r.status == "active" and r.shift_start <= now < r.shift_end:
            return r
    return None


def on_shift(assignments: Iterable[_Assignment], now: dt.datetime) -> bool:
    return current_window(assignments, now) is not None


def effective_available(
    profile: _Profile,
    assignments: Iterable[_Assignment],
    now: dt.datetime,
) -> bool:
    w = current_window(assignments, now)
    if w is None or profile.status != "active":
        return False
    if (
        profile.presence in ("on_break", "off")
        and profile.presence_set_at is not None
        and w.shift_start <= profile.presence_set_at < w.shift_end
    ):
        return False
    return True  # Working default (D39-literal)
```

- [ ] **Step 4: Run it (passes)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_availability.py -q`
Expected: PASS (all parametrized rows + the window test).

- [ ] **Step 5: Commit**

```bash
cd /workspace/Conduit-staffing
git add backend/conduit/shared/domain/availability.py backend/tests/spine/test_availability.py
git commit -m "feat(domain): pure effective-availability predicate + exhaustive table"
```

---

## Task 4: The single Python clock call site (`core/clock.py`)

**Files:**
- Create: `backend/conduit/core/clock.py`
- Test: `backend/tests/spine/test_availability.py` (append)

Read spec §4 "Time source" + §11 "Time control". Business-meaningful `now` must come from one freezegun-controllable Python call site.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/spine/test_availability.py`:
```python
from freezegun import freeze_time
from conduit.core.clock import now as clock_now


def test_clock_now_is_freezable_and_utc():
    with freeze_time("2026-05-16T12:00:00Z"):
        n = clock_now()
    assert n.tzinfo is not None
    assert n.year == 2026 and n.hour == 12
```

- [ ] **Step 2: Run it (fails)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_availability.py::test_clock_now_is_freezable_and_utc -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `clock.py`**

```python
# conduit/core/clock.py
"""The single business-time call site (freezegun-controllable).

Audit columns use DB func.now(); everything business-meaningful
(presence_set_at, the on-shift reference) flows through here.
"""
from __future__ import annotations

import datetime as dt


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
```

- [ ] **Step 4: Run it (passes)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_availability.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /workspace/Conduit-staffing
git add backend/conduit/core/clock.py backend/tests/spine/test_availability.py
git commit -m "feat(core): single freezegun-controllable business-time call site"
```

---

## Task 5: Supervisor Staff — dal + service + schema + api

**Files:**
- Create: `backend/conduit/supervisor/dal/staff.py`, `backend/conduit/supervisor/services/staff.py`, `backend/conduit/supervisor/schemas/staff.py`, `backend/conduit/supervisor/api/staff.py`
- Modify: `backend/conduit/supervisor/api/__init__.py` (register the sub-router)
- Test: `backend/tests/spine/test_staffing_dal.py`, `backend/tests/spine/test_staffing_api.py`

Read spec §8 (Supervisor — Staff) + §4 (profile verb shape, skills named exception). Read the merged `backend/conduit/supervisor/dal/sections.py`, `backend/conduit/supervisor/services/sections.py`, `backend/conduit/supervisor/api/accounts.py`, and the no-dispatch `supervisor/api/issue_codes.py` for the exact layering/gating idiom (`_sup = require_roles("supervisor","duty_manager")`, `actor = Depends(_sup)`, edge `await s.commit()` in the mutating handler, reads never commit). Read `backend/conduit/shared/events/` for the writer call signature and use it for every mutation event.

- [ ] **Step 1: Write failing API tests**

Create `backend/tests/spine/test_staffing_api.py`. Use the existing httpx/cookie helpers from `tests/spine/conftest.py` (read it; mirror how `test_e2e_journey.py` logs in per role). Cover:
```
- GET  /api/supervisor/staff as supervisor → 200, returns servicer accounts,
       profile == None for an un-profiled servicer, no `secret_hash` key anywhere
- POST /api/supervisor/staff/{servicer_id}/profile {staff_class:"housekeeping"} → 201
- POST same again → 409
- POST profile for a guest account id → 422
- POST profile for a random uuid → 404
- PATCH /api/supervisor/staff/{servicer_id}/profile {status:"disabled"} → 200
- PUT  /api/supervisor/staff/{servicer_id}/skills {skills:["electrical","hvac"]} → 200
- PUT  skills for an account with no profile → 404
- GET  /api/supervisor/staff as servicer → 403
- DELETE /api/supervisor/staff/{id} → 405
```
Write each as an explicit `async def test_...` with the assertion shown.

- [ ] **Step 2: Run them (fail)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_api.py -q`
Expected: FAIL (routes not registered → 404/all fail).

- [ ] **Step 3: Implement `dal/staff.py`** (add-only/no-flush; the one `replace_skills` hard-delete)

```python
# conduit/supervisor/dal/staff.py
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from conduit.shared.models import Account, StaffProfile, StaffSkill


async def get_account(s: AsyncSession, account_id: uuid.UUID) -> Account | None:
    return await s.get(Account, account_id)


async def list_servicer_accounts(s: AsyncSession) -> list[Account]:
    r = await s.execute(
        select(Account).where(Account.role == "servicer").order_by(
            Account.display_name
        )
    )
    return list(r.scalars().all())


async def get_profile(
    s: AsyncSession, account_id: uuid.UUID
) -> StaffProfile | None:
    return await s.get(StaffProfile, account_id)


async def get_skills(s: AsyncSession, account_id: uuid.UUID) -> list[str]:
    r = await s.execute(
        select(StaffSkill.skill).where(StaffSkill.account_id == account_id)
    )
    return sorted(r.scalars().all())


def add_profile(
    s: AsyncSession, account_id: uuid.UUID, staff_class: str
) -> StaffProfile:
    p = StaffProfile(account_id=account_id, staff_class=staff_class)
    s.add(p)
    return p


async def replace_skills(
    s: AsyncSession, account_id: uuid.UUID, skills: list[str]
) -> None:
    """The ONE sanctioned hard-replace in the codebase (spec §4).

    Not an HTTP DELETE — the 405 invariant is untouched. Skill rows are
    pure routing config, not FK-referenced by spine/provenance/read-model.
    """
    await s.execute(
        delete(StaffSkill).where(StaffSkill.account_id == account_id)
    )
    for sk in sorted(set(skills)):
        s.add(StaffSkill(account_id=account_id, skill=sk))
```

- [ ] **Step 4: Implement `schemas/staff.py`** (`extra="forbid"`, no account internals)

```python
# conduit/supervisor/schemas/staff.py
from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class ProfileOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_class: str
    presence: str
    status: str


class StaffOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    display_name: str
    profile: ProfileOut | None
    skills: list[str]


class CreateProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_class: str


class PatchProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_class: str | None = None
    status: str | None = None


class SetSkillsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skills: list[str]
```

- [ ] **Step 5: Implement `services/staff.py`** (guards + events + flush; reads compose DAL)

```python
# conduit/supervisor/services/staff.py
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from conduit.core.exceptions import ConflictError, NotFoundError, ValidationError
from conduit.shared.events import record_event  # confirm exact name from shared/events
from conduit.supervisor.dal import staff as dal


async def list_staff(s: AsyncSession) -> list[dict]:
    out = []
    for acc in await dal.list_servicer_accounts(s):
        p = await dal.get_profile(s, acc.id)
        out.append(
            {
                "account_id": acc.id,
                "display_name": acc.display_name,
                "profile": (
                    None if p is None
                    else {
                        "staff_class": p.staff_class,
                        "presence": p.presence,
                        "status": p.status,
                    }
                ),
                "skills": await dal.get_skills(s, acc.id),
            }
        )
    return out


async def create_profile(
    s: AsyncSession, actor_id: uuid.UUID,
    account_id: uuid.UUID, staff_class: str,
):
    acc = await dal.get_account(s, account_id)
    if acc is None:
        raise NotFoundError("account not found")
    if acc.role != "servicer":
        raise ValidationError("account is not a servicer")
    if await dal.get_profile(s, account_id) is not None:
        raise ConflictError("profile already exists")
    p = dal.add_profile(s, account_id, staff_class)
    await record_event(
        s, type="staff_profile_created", actor_account_id=actor_id,
        detail={"account_id": account_id},
    )
    await s.flush()
    return p


async def patch_profile(
    s: AsyncSession, actor_id: uuid.UUID,
    account_id: uuid.UUID, staff_class: str | None, status: str | None,
):
    p = await dal.get_profile(s, account_id)
    if p is None:
        raise NotFoundError("no profile")
    if staff_class is not None:
        p.staff_class = staff_class
    if status is not None:
        p.status = status
    await record_event(
        s, type="staff_profile_updated", actor_account_id=actor_id,
        detail={"account_id": account_id},
    )
    await s.flush()
    return p


async def set_skills(
    s: AsyncSession, actor_id: uuid.UUID,
    account_id: uuid.UUID, skills: list[str],
):
    if await dal.get_profile(s, account_id) is None:
        raise NotFoundError("no profile")
    await dal.replace_skills(s, account_id, skills)
    await record_event(
        s, type="staff_skills_set", actor_account_id=actor_id,
        detail={"account_id": account_id},
    )
    await s.flush()
```
NOTE: `record_event`'s exact name/signature comes from the merged `backend/conduit/shared/events/` — read that module first and adapt the call (the no-dispatch services use it for `child_*` events; mirror that call shape, mapping `detail` to whatever per-type detail row the writer expects). Do not invent a new writer.

- [ ] **Step 6: Implement `api/staff.py`** (per-handler `_sup`, edge commit on mutations)

Mirror `supervisor/api/issue_codes.py` exactly for router prefix, `_sup` dependency, and the `await s.commit()` placement in mutating handlers. Endpoints per spec §8: `GET /staff`, `GET /staff/{account_id}`, `POST /staff/{account_id}/profile`, `PATCH /staff/{account_id}/profile`, `PUT /staff/{account_id}/skills`. Map service dicts/ORM → `StaffOut`/`ProfileOut` at the API layer only. Register the router in `supervisor/api/__init__.py` the same way `issue_codes` is registered.

- [ ] **Step 7: Run the API tests (pass)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_api.py -q`
Expected: PASS (all Step-1 cases). Iterate implementation until green; change no files outside this task's Files block.

- [ ] **Step 8: Commit**

```bash
cd /workspace/Conduit-staffing
git add backend/conduit/supervisor/dal/staff.py backend/conduit/supervisor/services/staff.py backend/conduit/supervisor/schemas/staff.py backend/conduit/supervisor/api/staff.py backend/conduit/supervisor/api/__init__.py backend/tests/spine/test_staffing_api.py
git commit -m "feat(supervisor): staff profile + skills CRUD"
```

---

## Task 6: Supervisor Rosters — dal + service + schema + api (+ physical-invariant tests)

**Files:**
- Create: `backend/conduit/supervisor/dal/rosters.py`, `backend/conduit/supervisor/services/rosters.py`, `backend/conduit/supervisor/schemas/roster.py`, `backend/conduit/supervisor/api/rosters.py`
- Modify: `backend/conduit/supervisor/api/__init__.py` (register)
- Test: `backend/tests/spine/test_staffing_dal.py`, `backend/tests/spine/test_staffing_api.py` (append)

Read spec §6 (constraints), §8 (Rosters), §4 (assignment cardinality + D12/D18 split). Reuse the layering idiom from Task 5's exemplars.

- [ ] **Step 1: Write failing tests (API + physical invariants)**

Append to `backend/tests/spine/test_staffing_api.py`:
```
- POST /api/supervisor/rosters {shift_start, shift_end} (end>start) → 201
- POST /api/supervisor/rosters with shift_end <= shift_start → 422
- POST /api/supervisor/rosters/{rid}/assignments
       {account_id:<housekeeping servicer>, section_id:<sec>, assignment:"owner"} → 201
- POST same owner for same (roster, section) again → 409
- POST assignment {assignment:"owner", section_id:null} → 422
- POST assignment for an engineering-class servicer WITH section_id → 422
- POST assignment for an engineering-class servicer with section_id:null,
       assignment:"member" → 201
- POST assignment for a non-servicer account → 422
- PATCH /api/supervisor/rosters/{rid} {status:"disabled"} → 200
- DELETE /api/supervisor/rosters/{rid} → 405
```
Create `backend/tests/spine/test_staffing_dal.py` asserting the **physical** invariants against the live schema via the test session: inserting a 2nd `StaffProfile` for one account raises `IntegrityError`; inserting a dup `StaffSkill (account_id, skill)` raises; inserting a 2nd `assignment='owner', status='active'` for the same `(roster_id, section_id)` raises; inserting `assignment='owner', section_id=None` raises the CHECK; **and the allowed cases do NOT raise**: a `disabled` owner duplicate is allowed, and the same `account_id` as `owner` of a different `section_id` is allowed.

- [ ] **Step 2: Run them (fail)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_dal.py tests/spine/test_staffing_api.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement `dal/rosters.py`**

Add-only/no-flush CRUD: `create_roster`, `get_roster`, `list_rosters(status, active_at)`, `update_roster`, `list_assignments(roster_id)`, `get_assignment`, `add_assignment`, `update_assignment`, plus `get_profile(account_id)` (re-export or import from `dal.staff`) for the D18 guard. Use `select`/`s.add` only; never `flush`/`commit`.

- [ ] **Step 4: Implement `schemas/roster.py`** (`extra="forbid"`: `RosterOut`, `CreateRosterIn`, `PatchRosterIn`, `AssignmentOut`, `CreateAssignmentIn`, `PatchAssignmentIn`).

- [ ] **Step 5: Implement `services/rosters.py`**

`create_roster` (validate `shift_end > shift_start` → `ValidationError`; emit `roster_created`); `update_roster` (`roster_updated`); `create_assignment`:
```
- load account; not servicer → ValidationError
- load its StaffProfile; if staff_class == "engineering" and section_id is not None
      → ValidationError("engineering is skill-matched, not section-pooled")  # D18
- if assignment in ("owner","backup") and section_id is None
      → ValidationError(...)  # D12 (DB CHECK also enforces; service gives clean 422)
- dal.add_assignment; flush  → catch IntegrityError from the partial-unique
      owner index → ConflictError("section already has an active owner")
- emit assignment_created
```
`update_assignment` (`assignment_updated`). All mutations `await s.flush()`; the API handler commits.

- [ ] **Step 6: Implement `api/rosters.py`** + register in `supervisor/api/__init__.py` (mirror Task 5 idiom). Endpoints per spec §8.

- [ ] **Step 7: Run tests (pass)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_dal.py tests/spine/test_staffing_api.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd /workspace/Conduit-staffing
git add backend/conduit/supervisor/dal/rosters.py backend/conduit/supervisor/services/rosters.py backend/conduit/supervisor/schemas/roster.py backend/conduit/supervisor/api/rosters.py backend/conduit/supervisor/api/__init__.py backend/tests/spine/test_staffing_dal.py backend/tests/spine/test_staffing_api.py
git commit -m "feat(supervisor): roster windows + assignments (D12/D18 + cardinality)"
```

---

## Task 7: Servicer self — dal + services (home + presence) + schema + api

**Files:**
- Create: `backend/conduit/servicer/dal/self.py`, `backend/conduit/servicer/services/home.py`, `backend/conduit/servicer/services/presence.py`, `backend/conduit/servicer/schemas/home.py`, `backend/conduit/servicer/api/self.py`
- Modify/Create: `backend/conduit/servicer/api/__init__.py` (register; create if absent — mirror `supervisor/api/__init__.py`)
- Test: `backend/tests/spine/test_staffing_api.py` (append)

Read spec §7 (servicer flow), §8 (Servicer — self), §4 (off-shift lock, predicate home, time source). The servicer DAL is **self-scoped** (every query filtered by the authenticated `account_id`) and must **not** import `supervisor/dal` (Resolution E). Use `conduit.core.clock.now()` for business time and `conduit.shared.domain.availability` for the derivation.

- [ ] **Step 1: Write failing API tests (freezegun-pinned)**

Append to `backend/tests/spine/test_staffing_api.py` (import `from freezegun import freeze_time`):
```
- with freeze_time inside a roster window for the logged-in servicer:
    GET /api/servicer/home → 200, profile present, current_shift not null,
        presence_locked == False, effective_available == True
- PUT /api/servicer/presence {presence:"on_break"} (on-shift) → 200,
        body effective_available == False
- with freeze_time OUTSIDE any window:
    GET /api/servicer/home → 200, current_shift == null, presence_locked == True
    PUT /api/servicer/presence {presence:"working"} → 409   (server lock)
- GET /api/servicer/home as supervisor → 403
- DELETE /api/servicer/presence → 405
```

- [ ] **Step 2: Run them (fail)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_api.py -k servicer -q`
Expected: FAIL.

- [ ] **Step 3: Implement `dal/self.py`** (self-scoped reads + presence write)

```python
# conduit/servicer/dal/self.py
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from conduit.shared.models import (
    RosterAssignment, Section, StaffProfile, StaffSkill,
)


async def get_profile(
    s: AsyncSession, account_id: uuid.UUID
) -> StaffProfile | None:
    return await s.get(StaffProfile, account_id)


async def get_skills(s: AsyncSession, account_id: uuid.UUID) -> list[str]:
    r = await s.execute(
        select(StaffSkill.skill).where(StaffSkill.account_id == account_id)
    )
    return sorted(r.scalars().all())


async def get_assignments(
    s: AsyncSession, account_id: uuid.UUID
) -> list[RosterAssignment]:
    r = await s.execute(
        select(RosterAssignment)
        .where(RosterAssignment.account_id == account_id)
        .options(selectinload(RosterAssignment.roster))
    )
    return list(r.scalars().all())


async def get_section_label(
    s: AsyncSession, section_id: uuid.UUID | None
) -> str | None:
    if section_id is None:
        return None
    sec = await s.get(Section, section_id)
    return None if sec is None else sec.label


async def set_presence(
    s: AsyncSession, account_id: uuid.UUID,
    presence: str, set_at: dt.datetime,
) -> StaffProfile:
    p = await s.get(StaffProfile, account_id)
    p.presence = presence
    p.presence_set_at = set_at
    return p
```
NOTE: `RosterAssignment` needs a `roster` relationship for `selectinload`. If the merged model has no relationships (the codebase favours explicit joins), instead fetch rosters explicitly by id in the DAL and attach them, keeping `availability.py`'s `assignment.roster` contract. Read `roster_assignment.py` from Task 2 and choose the approach consistent with how the merged models handle relations; do not add relationships to other models.

- [ ] **Step 4: Implement `schemas/home.py`** (`extra="forbid"`: `ShiftOut{shift_start, shift_end, section_label|None, role}`, `ServicerHomeOut{profile, skills, current_shift|None, next_shift|None, presence, presence_locked, effective_available}`, `SetPresenceIn{presence}`).

- [ ] **Step 5: Implement `services/home.py` + `services/presence.py`**

`home.get_home(s, actor)`: fetch profile/skills/assignments via `dal.self`; `now = clock.now()`; `w = availability.current_window(assignments, now)`; compose `current_shift` from `w` (+ its assignment's section label/role), `next_shift` = the soonest future active window among assignments, `presence_locked = w is None`, `effective_available = availability.effective_available(profile, assignments, now)`. A read — no event, no commit.
`presence.set_presence(s, actor, presence)`: `now = clock.now()`; if `availability.current_window(assignments, now) is None` → `ConflictError` (the 409 server lock); `dal.self.set_presence(..., set_at=now)`; emit `presence_changed` via the `shared/events` writer; `await s.flush()`. API handler commits.

- [ ] **Step 6: Implement `api/self.py`** + register (create `servicer/api/__init__.py` mirroring `supervisor/api/__init__.py` if absent; ensure `main.py` already composes the servicer router — it does for the existing `/servicer/queue`; read `main.py` to confirm and follow it). `GET /servicer/home`, `PUT /servicer/presence`, gate `require_roles("servicer")`, edge commit on the PUT only.

- [ ] **Step 7: Run tests (pass)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_api.py -q`
Expected: PASS (all staffing API cases incl. servicer).

- [ ] **Step 8: Commit**

```bash
cd /workspace/Conduit-staffing
git add backend/conduit/servicer backend/tests/spine/test_staffing_api.py
git commit -m "feat(servicer): home (derived shift) + presence (off-shift 409 lock)"
```

---

## Task 8: Structural guards (the catch-any-regression net)

**Files:**
- Create: `backend/tests/spine/test_staffing_structural.py`
- Create: `backend/tests/spine/__snapshots__/route_contract.json` (generated, committed)

Read spec §11 "Structural guards". These tests must trip on regressions no one wrote a case for.

- [ ] **Step 1: Write the structural tests**

Create `backend/tests/spine/test_staffing_structural.py` with:
- **Route/contract snapshot:** build the app, serialize a sorted list of `(method, path, sorted(status codes), response_model schema name)` for every route under `/api/supervisor/staff`, `/api/supervisor/rosters`, `/api/servicer/*`; compare to `backend/tests/spine/__snapshots__/route_contract.json`; on mismatch, fail with a diff and the message "regenerate the snapshot if this change was intentional (spec §4)". First run writes the file if absent.
- **Role×endpoint matrix:** for each staffing endpoint, hit it as guest / servicer / supervisor / duty_manager / unauthenticated; assert the exact allow/deny matrix from spec §8.
- **No-DELETE sweep:** for every staffing path, `DELETE` → `405`.
- **Response parse-back:** call `GET /api/supervisor/staff`, assert no response object contains `secret_hash`/`username`/`password` keys (account internals never leak through the join).
- **Named-exception guard:** `grep`-style assertion that `delete(` appears in exactly one DAL module (`supervisor/dal/staff.py`, the `replace_skills` function) across `backend/conduit/**/dal/`.
- **Append-only guard:** after a `create_profile` call through the service, assert exactly one `event` row and exactly one matching detail row exist for it (within the test transaction).

- [ ] **Step 2: Run, generating the snapshot**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_staffing_structural.py -q`
Expected: PASS (first run writes `route_contract.json`; commit it).

- [ ] **Step 3: Commit**

```bash
cd /workspace/Conduit-staffing
git add backend/tests/spine/test_staffing_structural.py backend/tests/spine/__snapshots__/route_contract.json
git commit -m "test(spine): structural guards + committed route-contract snapshot"
```

---

## Task 9: End-to-end staffing sentinel

**Files:**
- Create: `backend/tests/spine/test_e2e_staffing.py`

Read spec §11 "E2E staffing sentinel". One test, time pinned with `freeze_time`.

- [ ] **Step 1: Write the sentinel**

Create `backend/tests/spine/test_e2e_staffing.py`: supervisor logs in → creates a roster window (covering a fixed pinned `now`) → POSTs a housekeeping profile + skills for a servicer → assigns that servicer `owner` of a section in the window → servicer logs in → `GET /servicer/home` shows the derived shift + `effective_available True` → `PUT /presence on_break` → `effective_available False` → `PUT /presence working` → `True` → with `freeze_time` shifted to before the window, `home` shows locked + `effective_available False` and `PUT /presence` → `409` → supervisor PATCHes the profile `status=disabled` → with time back in-window, `effective_available False` (disabled gate) → re-enable → `True`. Assert exactly one `event` per mutation along the way.

- [ ] **Step 2: Run it (pass)**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest tests/spine/test_e2e_staffing.py -q`
Expected: PASS.

- [ ] **Step 3: Full backend suite + coverage gate**

Run: `cd /workspace/Conduit-staffing/backend && .venv/bin/pytest -q`
Expected: PASS, coverage ≥ the existing `--cov-fail-under` (do not change that number). If coverage is short, add focused service/dal branch tests in the existing staffing test modules — not by lowering the gate.

- [ ] **Step 4: Commit**

```bash
cd /workspace/Conduit-staffing
git add backend/tests/spine/test_e2e_staffing.py
git commit -m "test(spine): end-to-end staffing journey sentinel"
```

---

## Task 10: Frontend — install + compose components

**Files:**
- Add (shadcn): `frontend/src/components/ui/toggle-group.tsx`, `frontend/src/components/ui/toggle.tsx`
- Create: `frontend/src/components/common/staff-profile-form-dialog.tsx`, `skills-field.tsx`, `roster-window-form-dialog.tsx`, `assignment-editor.tsx`, `presence-control.tsx`, `shift-card.tsx`, `staff-presence-cell.tsx`

Read spec §10. Read the merged `frontend/src/components/common/issue-code-form-dialog.tsx` and `frontend/src/components/common/data-table-shell.tsx` and `frontend/src/shell/supervisor/pages/issue-codes.tsx` first — clone their structure, do not invent new patterns.

- [ ] **Step 1: Install the only new primitive**

Run:
```bash
cd /workspace/Conduit-staffing/frontend
npx shadcn@latest add toggle-group
```
Expected: `toggle-group.tsx` and `toggle.tsx` created in `src/components/ui/`. Do not hand-edit beyond what later steps specify; never re-run `add` on an edited file.

- [ ] **Step 2: Compose `staff-profile-form-dialog.tsx`** — clone `issue-code-form-dialog.tsx` exactly; replace fields with a single `staff_class` `Select` (`housekeeping|engineering|room_service|concierge|runner`); create path = `POST` profile, edit path = `PATCH` (class/status); toasts + `extra`-safe payloads as in the exemplar.

- [ ] **Step 3: Compose `skills-field.tsx`** — `Input` + add-on-Enter producing removable `Badge` chips; controlled value `string[]`; on save the parent calls the PUT replace-set hook. No new primitive.

- [ ] **Step 4: Compose `roster-window-form-dialog.tsx`** — clone the form-dialog shell; body is the existing `date-range-field` for `shift_start`/`shift_end`; zod refine `end > start` mirroring the server `422`.

- [ ] **Step 5: Compose `assignment-editor.tsx`** — for use inside a `Sheet`: `combobox-field` (servicer picker) + section `Select` + role `Select`. When the picked servicer's class is `engineering`, disable the Section select and show a tooltip "Engineering is skill-matched, not section-pooled (D18)"; when role ∈ owner/backup, mark Section required with an inline helper. Mirror the issue-codes "taught lock" tooltip pattern.

- [ ] **Step 6: Compose `presence-control.tsx`** — wrap `toggle-group` (single-select, values `working|on_break|off`); prop `locked: boolean` → disabled + caption "Available when your shift starts"; `onChange` calls the presence mutation.

- [ ] **Step 7: Compose `shift-card.tsx`** + `staff-presence-cell.tsx` — `shift-card`: section · role · window + one derived line ("On shift · ends in Xh Ym" / "Off shift · next …" / "No upcoming shift"). `staff-presence-cell`: the monochrome glyph `● Working · On shift` / `○ Off · Off shift` (weight/fill only, no colour alarm). Tailwind classes consistent with the tightened tokens (`rounded-lg`, `text-muted-foreground`, etc.).

- [ ] **Step 8: Typecheck/build**

Run: `cd /workspace/Conduit-staffing/frontend && npm run build`
Expected: build succeeds (components compile even before pages wire them).

- [ ] **Step 9: Commit**

```bash
cd /workspace/Conduit-staffing
git add frontend/src/components/ui/toggle-group.tsx frontend/src/components/ui/toggle.tsx frontend/src/components/common/staff-profile-form-dialog.tsx frontend/src/components/common/skills-field.tsx frontend/src/components/common/roster-window-form-dialog.tsx frontend/src/components/common/assignment-editor.tsx frontend/src/components/common/presence-control.tsx frontend/src/components/common/shift-card.tsx frontend/src/components/common/staff-presence-cell.tsx
git commit -m "feat(ui): install toggle-group + compose staffing components"
```

---

## Task 11: Frontend — supervisor Staff page + hook

**Files:**
- Create: `frontend/src/shell/supervisor/hooks/use-staff.ts`, `frontend/src/shell/supervisor/pages/staff.tsx`
- Modify: `frontend/src/shell/supervisor/nav.tsx`, `frontend/src/App.tsx`

Read the merged `frontend/src/shell/supervisor/hooks/use-issue-codes.ts` and `pages/issue-codes.tsx` — clone exactly.

- [ ] **Step 1: `use-staff.ts`** — clone `use-issue-codes.ts` shape: types (`StaffRow`, `Profile`), `useStaff()` (`['staff']`), `useCreateProfile()` / `usePatchProfile()` / `useSetSkills()` mutations, each invalidating `['staff']`.

- [ ] **Step 2: `pages/staff.tsx`** — clone `issue-codes.tsx`: `PageHeader` + `DataTableShell`; columns Name · Class (or "Not profiled" + a `Create profile` action) · Skills (chips) · `staff-presence-cell` · `StatusBadge` · `⋯` (Create profile / Edit / Edit skills / Disable·Enable via `Confirm`); responsive `cards` slot like the exemplar.

- [ ] **Step 3: Wire nav + route** — add `{ title: "Staff", url: "/supervisor/staff" }` under the Setup group in `supervisor/nav.tsx`; add the route in `App.tsx` next to the issue-codes route (same lazy/element pattern).

- [ ] **Step 4: Build**

Run: `cd /workspace/Conduit-staffing/frontend && npm run build`
Expected: success.

- [ ] **Step 5: Commit**

```bash
cd /workspace/Conduit-staffing
git add frontend/src/shell/supervisor/hooks/use-staff.ts frontend/src/shell/supervisor/pages/staff.tsx frontend/src/shell/supervisor/nav.tsx frontend/src/App.tsx
git commit -m "feat(ui): supervisor Staff page"
```

---

## Task 12: Frontend — supervisor Rosters page (Sheet master-detail) + hook

**Files:**
- Create: `frontend/src/shell/supervisor/hooks/use-rosters.ts`, `frontend/src/shell/supervisor/pages/rosters.tsx`
- Modify: `frontend/src/shell/supervisor/nav.tsx`, `frontend/src/App.tsx`

Read spec §10 (Rosters). Reuse the installed `Sheet`, `data-table-shell`, the Task-10 `roster-window-form-dialog` + `assignment-editor`.

- [ ] **Step 1: `use-rosters.ts`** — `useRosters()` (`['rosters']`), `useCreateRoster()`/`usePatchRoster()`; `useAssignments(rosterId)` (`['rosters', rosterId, 'assignments']`), `useCreateAssignment()`/`usePatchAssignment()`; invalidate by key prefix on mutation. Clone the `use-issue-codes.ts` mutation/invalidation idiom.

- [ ] **Step 2: `pages/rosters.tsx`** — `PageHeader` (+ `roster-window-form-dialog` as the new-window action) + `DataTableShell` window list; row click sets `selected` and opens a `Sheet`; the Sheet body renders the window header + an assignments `DataTableShell` + an `assignment-editor` to add; edit/disable rows via `Confirm`. Mobile: Sheet is full-height (shadcn default side behaviour).

- [ ] **Step 3: Wire nav + route** — add `{ title: "Rosters", url: "/supervisor/rosters" }` under Setup; add the route in `App.tsx`.

- [ ] **Step 4: Build**

Run: `cd /workspace/Conduit-staffing/frontend && npm run build`
Expected: success.

- [ ] **Step 5: Commit**

```bash
cd /workspace/Conduit-staffing
git add frontend/src/shell/supervisor/hooks/use-rosters.ts frontend/src/shell/supervisor/pages/rosters.tsx frontend/src/shell/supervisor/nav.tsx frontend/src/App.tsx
git commit -m "feat(ui): supervisor Rosters page (Sheet master-detail)"
```

---

## Task 13: Frontend — servicer home (replace the stale stub) + hook + nav

**Files:**
- Replace: `frontend/src/shell/servicer/index.tsx`, `frontend/src/shell/servicer/nav.tsx`, `frontend/src/shell/servicer/hooks/use-servicer.ts`
- Modify: `frontend/src/App.tsx` (verify the `/servicer` route renders the new home)

Read spec §10 (Servicer home) + §4 (cleanup scope — this replacement is in-scope). The old files pre-build an unbuilt dispatch task-queue; replace them wholesale.

- [ ] **Step 1: Replace `hooks/use-servicer.ts`** — delete the speculative task-queue hooks; implement `useServicerHome()` (`['servicer','home']`, `refetchInterval` consistent with the codebase's AD7 polling — match the value the old hook used) and `usePresence()` (mutation → invalidate `['servicer','home']`).

- [ ] **Step 2: Replace `index.tsx`** — one calm mobile-first screen: identity (display name + class `role-badge` + skill chips), `shift-card`, `presence-control` (pass `locked = !current_shift` and the consequence caption), one secondary line "On break and off pause new task routing". Use `DataTableShell`-grade state handling is unnecessary (single object) — but loading/error use the same `Skeleton`/`ErrorState` primitives, never hand-rolled `<p>` strings.

- [ ] **Step 3: Replace `nav.tsx`** — single entry `{ title: "Home", url: "/servicer" }` (icon from lucide, e.g. `HomeIcon`); keep the `NavConfig` shape.

- [ ] **Step 4: Verify route** — confirm `App.tsx` `/servicer` renders the new home component (rename the imported symbol if it changed).

- [ ] **Step 5: Build**

Run: `cd /workspace/Conduit-staffing/frontend && npm run build`
Expected: success, no references to the deleted task-queue hooks remain (`grep -rn "useTaskQueue\|useAcceptWorkOrder\|useEscalateWorkOrder" src` → no matches).

- [ ] **Step 6: Commit**

```bash
cd /workspace/Conduit-staffing
git add frontend/src/shell/servicer/index.tsx frontend/src/shell/servicer/nav.tsx frontend/src/shell/servicer/hooks/use-servicer.ts frontend/src/App.tsx
git commit -m "feat(ui): servicer portal home (replaces speculative task-queue stub)"
```

---

## Task 14: Finalize — full suite, push, PR

**Files:** none (verification + delivery only)

- [ ] **Step 1: Full backend suite under savepoint isolation + coverage gate**

Run:
```bash
cd /workspace/Conduit-staffing/backend && .venv/bin/pytest -q
```
Expected: PASS, coverage gate met, no leak-sentinel failure. If anything is red, fix within the owning task's Files and re-run — do not push red.

- [ ] **Step 2: Frontend typecheck + build**

Run:
```bash
cd /workspace/Conduit-staffing/frontend && npm run build
```
Expected: success.

- [ ] **Step 3: Confirm the worktree is the only thing changed and review the diff**

Run:
```bash
cd /workspace/Conduit-staffing
git status -s            # expect clean (everything committed)
git log --oneline origin/main..HEAD
git diff --stat origin/main..HEAD
```
Expected: a clean tree and the task commits listed; no changes under `/workspace/Conduit`.

- [ ] **Step 4: Push the branch**

Run:
```bash
cd /workspace/Conduit-staffing
git push -u origin feat/staffing-availability
```
Expected: branch published.

- [ ] **Step 5: Raise the PR**

Run:
```bash
cd /workspace/Conduit-staffing
gh pr create --base main --head feat/staffing-availability \
  --title "Staffing & Availability slice — staff profiles, rosters, presence (#3)" \
  --body "$(cat <<'EOF'
## Summary
The routing-precondition slice: supervisor declares staffing structure
(staff class/skills + time-bounded rosters with section owner/backup),
servicer declares presence; a pure derived effective-availability
predicate (`shared/domain/availability.py`) the next slice's routing
consumes. Implements D4/D12/D18/D39 (see `docs/datamodels/` and
`docs/archi/`); design in
`docs/superpowers/specs/2026-05-16-staffing-availability-design.md`.

## Guarantees
- Migration `0004` stacks on `0003`, round-trips; physical invariants
  (1:1 profile, composite skill pk, one active owner per section, owner
  needs section) enforced and tested both ways.
- Exhaustive availability truth-table incl. every boundary; freezegun
  time control (business time via one Python call site; audit time DB).
- Structural guards: committed route-contract snapshot, role×endpoint
  matrix, no-DELETE→405, response parse-back, named-exception guard,
  append-only guard. Unconditional savepoint-rollback isolation.
- Servicer portal brought online (replaces the speculative task-queue
  stub); one new shadcn primitive (`toggle-group`).

## Out (stated seams)
Routing/dispatch/WorkOrder, timers/spine, event read model — later
slices. No auth-owned changes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL printed.

- [ ] **Step 6: Report**

Print the PR URL and the final `pytest -q` summary line. Done.

---

## Self-review (completed by plan author)

- **Spec coverage:** §2 scope → Tasks 2–13; §6 data model → Task 2; §7 derivation → Tasks 3–4,7; §8 API → Tasks 5–7; §9 journeys → exercised by Task 9 e2e; §10 frontend → Tasks 10–13; §11 test bench (savepoint isolation reused from merged conftest; layered → Tasks 2,3,5,6,7; structural guards → Task 8; e2e → Task 9; freezegun → Tasks 4,7,9); §13 cleanup → Tasks 1,13. No uncovered section.
- **Placeholder scan:** no TBD/TODO; every code step shows code; the few "mirror the merged exemplar X" instructions name the exact file and the exact idiom to copy (a concrete instruction, not a placeholder) because the merged file is the authoritative pattern and must not be diverged from.
- **Type consistency:** `effective_available(profile, assignments, now)`, `current_window`, `on_shift` consistent across Tasks 3/7/9; `record_event` flagged in Task 5 as "confirm exact name from `shared/events`" so later tasks reuse the same call; `ServicerHomeOut` fields consistent §8 ↔ Task 7 schema ↔ Task 13 hook.
- **Worktree/venv/env/PR mechanics:** Task 0 (worktree off `origin/main`, venv from `/workspace/Conduit/backend/.venv`, copy both `.env` files), Task 14 (tests → push → PR). Opus-only + exact Files blocks stated in "Subagent rules". No reference to any external product folder anywhere in this plan.
