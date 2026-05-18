# Multi-Intent Fan-Out + Relocation Sub-Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two stacked journey slices in one isolated worktree: Slice 7 (realise the stubbed `decompose`/`triage` pipeline + split-echo) then Slice 8 (wire the relocate seam: eligible-room selection, real re-bind, front-office move task, sibling re-bind), then test, commit, push, and raise one PR.

**Architecture:** Single worktree off current `main` (which must already contain the merged conversation-answer-action substrate, migration `0006_conv_aa`). Slice 7 is pure-mechanism + intake reorder, zero schema. Slice 8 adds one migration (`0007`, `down_revision='0006_conv_aa'`), wires Phase-E relocate ctx, and spawns a system move task. Backend = FastAPI + SQLAlchemy 2 async + Alembic + Postgres (required, no sqlite). Frontend = React 19 + TanStack Query + shadcn (radix-nova). All work is additive on the merged substrate; the route/contract snapshot must not drift.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, pytest (Postgres-backed, savepoint-isolated), React 19, Vite, TanStack Query v5, shadcn/lucide, `gh` CLI.

**Specs (the authoritative design — read before implementing):**
- `docs/superpowers/specs/2026-05-18-multi-intent-fanout-design.md` (Slice 7)
- `docs/superpowers/specs/2026-05-18-relocation-subflow-design.md` (Slice 8)

**Hard rules for every executor and subagent:**
- **Never** write the upstream product codename this work derives from, or any `/workspace/` product-source directory path, into any file, commit message, branch name, PR title/body, or code comment. Use only this project's own vocabulary (D-series decision ids and the two spec paths above).
- The product behaviour is defined solely by the two spec files above and the existing `/workspace/Conduit` code. Do not consult or reference any external product doc.
- **Subagents must be Opus.** Every `Agent` dispatch in this plan MUST pass `model: "opus"` and `subagent_type: "general-purpose"`. Never sonnet/haiku. Every dispatch MUST list the exact files the subagent may create/modify (the "Subagent files" block on each task) and forbid touching anything else.
- TDD: failing test → run-fail → minimal impl → run-pass → commit. Commit after every green step. Postgres must be reachable (`postgres:5432`) for the suite.
- Additive only. Do not rewrite any merged slice-6 code. Preserve slice-6's intake conversation-window build, its `is_reservation_mutation` FLAG→`spine.open_escalation` branch, and `requested_checkout` persistence verbatim.

---

## Phase 0 — Precondition gate, worktree, environment (executor runs these directly; NOT subagents)

### Task 0.1: Verify the slice-6 substrate is on `main`

**Files:** none (read-only checks)

- [ ] **Step 1: Confirm `main` is clean and has the conversation-answer-action migration**

Run:
```bash
cd /workspace/Conduit
git fetch origin -q
git rev-parse --abbrev-ref HEAD            # expect: main
git status --porcelain                      # expect: empty
git log --oneline -1 origin/main
ls backend/migrations/versions/0006_conversation_answer_action.py 2>/dev/null \
  && grep -E '^revision|^down_revision' backend/migrations/versions/0006_conversation_answer_action.py
```
Expected: `0006_conversation_answer_action.py` exists on `main` with `revision = "0006_conv_aa"` and `down_revision = "0005_dispatch"`.

- [ ] **Step 2: If `0006_conv_aa` is NOT on `main`, STOP and run the slice-6 recovery (Task 0.2). If it IS present, skip Task 0.2 and go to Task 0.3.**

### Task 0.2: (Only if Step 0.1 failed) Land slice 6 via a clean branch — close the tangled PR #10

**Files:** none in `main` (git/PR operations only)

- [ ] **Step 1: Diagnose & confirm**

Run:
```bash
cd /workspace/Conduit
gh pr view 10 --json mergeable,mergeStateStatus,headRefName,baseRefName
git merge-base origin/main origin/feat/conversation-answer-action
```
Expected: PR #10 `CONFLICTING/DIRTY` (it re-introduces the already-squash-merged spine). It must NOT be conflict-resolved.

- [ ] **Step 2: Build a clean slice-6 branch off current `main`**

```bash
cd /workspace/Conduit
git switch -c feat/conv-aa-clean origin/main
MB=$(git merge-base origin/main origin/feat/conversation-answer-action)
git diff "$MB"..origin/feat/conversation-answer-action -- \
  backend/conduit backend/migrations backend/tests frontend/src \
  > /tmp/slice6.patch
git apply --3way /tmp/slice6.patch
```
Expected: patch applies cleanly (slice 6 was authored additive-on-spine; `main` already has the spine).

- [ ] **Step 3: Verify slice-6 suite green, commit, push, open PR, merge, return to main**

```bash
cd /workspace/Conduit/backend && .venv/bin/pytest -q
cd /workspace/Conduit
git add -A
git commit -m "feat: conversation context + answer-action seam (clean rebuild off main)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push -u origin feat/conv-aa-clean
gh pr close 10 --comment "Superseded: spine already on main via #6; this branch re-introduced it. Slice 6 delivered cleanly via feat/conv-aa-clean."
gh pr create --base main --head feat/conv-aa-clean \
  --title "Conversation context + answer-action seam" \
  --body "Clean additive rebuild of slice 6 off current main. 🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr merge --squash --delete-branch
git switch main && git pull -q origin main
```
Expected: suite green; PR #10 closed; slice 6 squash-merged; `main` now has `0006_conv_aa`. Re-run Task 0.1 Step 1 to confirm, then continue.

### Task 0.3: Create the isolated worktree

**Files:** Create worktree dir `/workspace/Conduit-fanout-relocation`

- [ ] **Step 1: Create the branch + worktree off current main**

```bash
cd /workspace/Conduit
git fetch origin -q
git worktree add -b feat/fanout-relocation /workspace/Conduit-fanout-relocation origin/main
cd /workspace/Conduit-fanout-relocation
git log --oneline -1                       # expect tip == origin/main
```
Expected: worktree at `/workspace/Conduit-fanout-relocation` on new branch `feat/fanout-relocation`.

- [ ] **Step 2: Copy the env files into the worktree (NOT committed)**

```bash
cp /workspace/Conduit/backend/.env  /workspace/Conduit-fanout-relocation/backend/.env
cp /workspace/Conduit/frontend/.env /workspace/Conduit-fanout-relocation/frontend/.env
grep -q '^backend/\.env$\|\.env' /workspace/Conduit-fanout-relocation/.gitignore || true
git -C /workspace/Conduit-fanout-relocation status --porcelain | grep -E '\.env$' \
  && echo "WARNING: .env is tracked — STOP and add to .gitignore" || echo ".env untracked OK"
```
Expected: both `.env` files present in the worktree and untracked.

### Task 0.4: Build the worktree virtualenv from the source interpreter

**Files:** Create `/workspace/Conduit-fanout-relocation/backend/.venv`

- [ ] **Step 1: Recreate the venv (do NOT `cp -r` the source venv — venvs hardcode absolute paths)**

The source env is `/workspace/Conduit/backend/.venv`, whose interpreter resolves to `/workspace/environment/python/bin/python3.12`. Use that same interpreter as the source to build a fresh, path-correct venv in the worktree, then editable-install.

```bash
SRC_PY=$(/workspace/Conduit/backend/.venv/bin/python -c 'import sys;print(sys.executable)')
echo "source interpreter: $SRC_PY"
cd /workspace/Conduit-fanout-relocation/backend
"$SRC_PY" -m venv .venv
.venv/bin/pip -q install --upgrade pip
.venv/bin/pip -q install -e ".[dev]"
.venv/bin/python -c "import fastapi, sqlalchemy, alembic, pytest; print('env OK')"
```
Expected: `env OK`.

- [ ] **Step 2: Baseline-green gate (the substrate must be green before we touch it)**

```bash
cd /workspace/Conduit-fanout-relocation/backend && .venv/bin/pytest -q
```
Expected: full suite PASS (this is `main` + slice 6). If red, STOP — do not build on a red baseline.

- [ ] **Step 3: Read the specs**

Run: `sed -n '1,9999p' /workspace/Conduit-fanout-relocation/docs/superpowers/specs/2026-05-18-multi-intent-fanout-design.md` and the relocation spec. The executor (and every subagent, via its task prompt) treats these two files as the sole behavioural source of truth.

---

## Phase A — Slice 7: Multi-intent fan-out + split-echo (zero schema)

> All Phase-A work in `/workspace/Conduit-fanout-relocation`. Backend cwd: `backend/`. Test runner: `.venv/bin/pytest -q`. Spec: `docs/superpowers/specs/2026-05-18-multi-intent-fanout-design.md` §7/§11.

### Task A1: Conftest decompose double (keeps single-need fixtures green)

**Files:**
- Modify: `backend/tests/spine/conftest.py`

**Subagent files (Opus):** may modify ONLY `backend/tests/spine/conftest.py`.

- [ ] **Step 1: Add a `fake_decompose` fixture mirroring `fake_llm`**

Append to `backend/tests/spine/conftest.py`:
```python
@pytest.fixture()
def fake_decompose(monkeypatch):
    """Deterministic decompose double. Default: identity (1 message → 1 text)
    so every single-need fixture stays byte-identical. Tests that want a
    multi-need split set state["texts"] to a list."""
    from conduit.shared.domain import triage as _t
    state = {"texts": None}

    def _d(raw_text: str):
        return state["texts"] if state["texts"] is not None else [raw_text]

    monkeypatch.setattr(_t, "decompose", _d)
    return state
```

- [ ] **Step 2: Run to verify collection still works**

Run: `.venv/bin/pytest -q tests/spine/conftest.py --collect-only 2>&1 | tail -2`
Expected: no collection error.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/spine/conftest.py
git commit -m "test(spine): deterministic decompose double (single-need stays green)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task A2: Pure `decompose()` (TDD)

**Files:**
- Modify: `backend/conduit/shared/domain/triage.py` (the `decompose` stub at the `raise NotImplementedError`)
- Modify: `backend/conduit/shared/integrations/openai.py` (add a `decompose` LLM call; classify prompt already history-aware from slice 6 — do not touch it)
- Test: `backend/tests/spine/test_triage.py`

**Subagent files (Opus):** may modify ONLY `backend/conduit/shared/domain/triage.py`, `backend/conduit/shared/integrations/openai.py`, `backend/tests/spine/test_triage.py`. Must NOT touch `intake.py` or any model.

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/spine/test_triage.py`:
```python
import pytest
from conduit.shared.integrations import openai as llm
from conduit.shared.domain import triage


async def test_decompose_single_need_returns_one(monkeypatch):
    async def fake(t): return [t]
    monkeypatch.setattr(llm, "decompose", fake)
    assert await triage.decompose("can I get extra towels") == \
        ["can I get extra towels"]


async def test_decompose_multi_need_returns_n(monkeypatch):
    async def fake(t):
        return ["extra towels", "the TV is broken", "what time is checkout"]
    monkeypatch.setattr(llm, "decompose", fake)
    out = await triage.decompose(
        "towels, the TV is broken, and what time is checkout?")
    assert out == ["extra towels", "the TV is broken", "what time is checkout"]


async def test_decompose_empty_or_garbage_never_zero(monkeypatch):
    async def fake(t): return []
    monkeypatch.setattr(llm, "decompose", fake)
    out = await triage.decompose("zzz")
    assert out == ["zzz"]                       # never 0; never a silent drop


async def test_decompose_llm_unavailable_falls_back_to_single(monkeypatch):
    async def boom(t): raise llm.LLMUnavailable("down")
    monkeypatch.setattr(llm, "decompose", boom)
    out = await triage.decompose("a and b")
    assert out == ["a and b"]                   # AD11 conservative single text
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest -q tests/spine/test_triage.py -k decompose`
Expected: FAIL (`NotImplementedError` / `llm.decompose` missing).

- [ ] **Step 3: Implement**

In `backend/conduit/shared/integrations/openai.py` add an async `decompose(raw_text: str) -> list[str]` mirroring the existing `classify` call shape (same client/bulkhead, raises `LLMUnavailable` on failure; returns a list of need-strings). Follow the file's existing `_SYS_*` prompt + `_Child` patterns; the system prompt instructs: "Split the guest message into independent service needs; return each need verbatim-ish as a separate string; a single need returns a one-element list."

In `backend/conduit/shared/domain/triage.py` replace the `decompose` body:
```python
async def decompose(raw_text: str) -> list[str]:
    """One guest message → N independent child texts (D35).

    >1 ⇒ caller echoes the split back (D36). LLM-assisted; any failure or an
    empty result falls back to the single original text — never 0, never a
    silent drop (AD11)."""
    try:
        texts = await llm.decompose(raw_text)
    except llm.LLMUnavailable:
        return [raw_text]
    cleaned = [t.strip() for t in (texts or []) if t and t.strip()]
    return cleaned or [raw_text]
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest -q tests/spine/test_triage.py -k decompose`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/conduit/shared/domain/triage.py backend/conduit/shared/integrations/openai.py backend/tests/spine/test_triage.py
git commit -m "feat(domain): decompose() — D35 split, AD11-conservative

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task A3: Deterministic `triage()` + `TriagedChild.issue_label` (TDD)

**Files:**
- Modify: `backend/conduit/shared/domain/triage.py` (`triage` stub; add `issue_label` to `TriagedChild`; keep slice-6's `requested_checkout` field as-is)
- Test: `backend/tests/spine/test_triage.py`

**Subagent files (Opus):** ONLY `backend/conduit/shared/domain/triage.py`, `backend/tests/spine/test_triage.py`.

- [ ] **Step 1: Write failing tests** (slot-completeness + D30 rulebook + D20/D30 signatures)

Append to `backend/tests/spine/test_triage.py`:
```python
def test_triage_complete_low_risk_auto():
    r = triage.triage("2 extra bath towels to my room")
    assert r.outcome == triage.TriageOutcome.AUTO

def test_triage_missing_slot_clarifies():
    r = triage.triage("I need something")
    assert r.outcome == triage.TriageOutcome.CLARIFY

def test_triage_d30_risk_flags():
    r = triage.triage("there is water flooding the bathroom, urgent")
    assert r.outcome == triage.TriageOutcome.FLAG

def test_triage_tier_not_from_asserted_urgency():
    a = triage.triage("extra towels")
    b = triage.triage("URGENT!!! extra towels NOW")
    assert a.outcome == b.outcome            # D20: urgency ≠ outcome/tier
```
Note: the exact slot/risk rule set is defined in spec §7.2 / D5 / D30; implement those rules deterministically (objective triggers: money/safety/move/mutation), LLM may only *raise*.

- [ ] **Step 2: Run → fail.** `.venv/bin/pytest -q tests/spine/test_triage.py -k triage_` → FAIL.

- [ ] **Step 3: Implement** per spec §7.2: add `issue_label: str | None = None` to `TriagedChild`; implement `triage(child_text)` as the pure deterministic slot-completeness + objective D30 risk rulebook returning `TriagedChild` with `AUTO|CLARIFY|FLAG`. No LLM call inside `triage` (extraction stays in `classify`). Reservation-mutation → FLAG (preserve the existing Resolution-A force-flag semantics).

- [ ] **Step 4: Run → pass.** Expected: PASS. Also run full `test_triage.py` (the 2 inherited tests stay green).

- [ ] **Step 5: Commit**
```bash
git add backend/conduit/shared/domain/triage.py backend/tests/spine/test_triage.py
git commit -m "feat(domain): deterministic triage() (D5/D30); TriagedChild.issue_label

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task A4: Intake reorder on the post-slice-6 shape + split-echo fields (TDD)

**Files:**
- Modify: `backend/conduit/guest/services/intake.py` (reorder to `window → decompose → per-text classify(history) → triage → route`; assemble `split`)
- Modify: `backend/conduit/guest/schemas/conversation.py` (`RequestOut.split: bool`; `ChildOut.issue_label: str|None`; `ChildOut.outcome: str`)
- Test: `backend/tests/spine/test_intake_service.py`, `backend/tests/spine/test_structural_guards.py`

**Subagent files (Opus):** ONLY the four files above. Must PRESERVE verbatim: slice-6's conversation-window build, the `is_reservation_mutation` FLAG→`spine.open_escalation` branch, and `requested_checkout` persistence. Read `intake.py` fully before editing; the reorder wraps the existing per-child loop body in a decompose loop — it does not rewrite the routing branches.

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/spine/test_intake_service.py` (use `fake_decompose` + `fake_llm`/`monkeypatch_all` + `seeded_guest_with_stay`):
```python
async def test_multi_intent_fans_into_independent_children(
        db, seeded_guest_with_stay, fake_decompose, fake_llm):
    fake_decompose["texts"] = ["extra towels", "what time is checkout"]
    async def fc(t, cat, history=""):
        code = "HK_REQUEST" if "towel" in t else "INFO_GENERAL"
        mode = "dispatch" if "towel" in t else "no_dispatch"
        return [{"text": t, "issue_code": code, "fulfilment_mode": mode,
                 "outcome": "auto" if "towel" in t else "no_dispatch",
                 "is_problem_report": False}]
    async def fg(q, ctx, history=""):
        return {"grounded": True, "leaves_no_dispatch": False,
                "answer": "11am", "used_kb_ids": [], "used_fields": []}
    fake_llm["classify"] = fc; fake_llm["ground"] = fg
    actor, _ = seeded_guest_with_stay
    from conduit.guest.services import intake
    out = await intake.submit_request(db, actor, "towels and checkout time?")
    await db.flush()
    assert out["split"] is True
    assert len(out["children"]) == 2
    assert {c["text"] for c in out["children"]} == {
        "extra towels", "what time is checkout"}

async def test_single_need_is_instant_ack_not_split(
        db, seeded_guest_with_stay, fake_decompose, fake_llm):
    async def fc(t, cat, history=""):
        return [{"text": t, "issue_code": "HK_REQUEST",
                 "fulfilment_mode": "dispatch", "outcome": "auto",
                 "is_problem_report": False}]
    fake_llm["classify"] = fc
    actor, _ = seeded_guest_with_stay
    from conduit.guest.services import intake
    out = await intake.submit_request(db, actor, "extra towels")
    await db.flush()
    assert out["split"] is False and len(out["children"]) == 1
```
Add to `backend/tests/spine/test_structural_guards.py`:
```python
def test_request_out_shapes_parse_back():
    from conduit.guest.schemas.conversation import RequestOut, ChildOut
    RequestOut(request_id="r", split=True, children=[ChildOut(
        child_id="c", text="t", issue_code=None, issue_label="L",
        outcome="auto", terminal="logged", state="routing")])
```

- [ ] **Step 2: Run → fail.** Expected: FAIL (`split`/`issue_label`/`outcome` unknown; intake single-intent).

- [ ] **Step 3: Implement** the additive schema fields and the intake reorder per spec §7.3 (wrap the existing classify→child→route loop in `for child_text in await triage.decompose(raw_text):`; per text call `classify(child_text, catalog, history=window)` then `triage`; keep every routing branch and the slice-6 reservation-FLAG branch unchanged; set `split = len(children) >= 2`; populate `issue_label`/`outcome` per child).

- [ ] **Step 4: Run → pass.** Run `.venv/bin/pytest -q tests/spine/test_intake_service.py tests/spine/test_structural_guards.py`. Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/conduit/guest/services/intake.py backend/conduit/guest/schemas/conversation.py backend/tests/spine/test_intake_service.py backend/tests/spine/test_structural_guards.py
git commit -m "feat(intake): decompose→per-child triage pipeline + D36 split-echo

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task A5: Update inherited single-intent tests + zero-schema guard + multi-intent e2e (TDD)

**Files:**
- Modify: `backend/tests/spine/test_e2e_journey.py` (the `len(children)==1` assertion → multi-aware; use `fake_decompose` default identity so its single-need script stays 1)
- Modify: `backend/tests/spine/test_guest_dispatch.py` (any single-child indexing → iterate)
- Create: `backend/tests/spine/test_e2e_fanout.py` (one scripted 3-need journey)
- Modify: `backend/tests/spine/test_migration.py` (positive guard: model column-sets byte-identical → Slice 7 added zero schema)

**Subagent files (Opus):** ONLY the four test files above.

- [ ] **Step 1: Write the e2e sentinel + zero-schema guard**

`backend/tests/spine/test_e2e_fanout.py`: drive the real `POST /api/guest/requests` via `client` with a supervisor-seeded catalog; `fake_decompose["texts"]` = 3 needs (towel HK dispatch, TV problem-report ENG, checkout no-dispatch); assert `split is True`, 3 children, each on its own lifecycle, exactly one append-only event per transition (before/after scoped counts, the `test_e2e_dispatch` idiom), zero residue on a deliberately failed sub-leg.
`test_migration.py`: add a test asserting `inspect(ChildSubRequest).columns`, `WorkOrder`, `IssueCode`, `Recommendation` column-name sets are exactly the slice-6 sets (enumerate them) — proves Slice 7 added zero columns/tables.

- [ ] **Step 2: Run → fail.** New e2e fails (pipeline assertions); guard passes (it should — Slice 7 is zero-schema). Fix `test_e2e_journey.py`/`test_guest_dispatch.py` to be multi-aware (default `fake_decompose` keeps them 1 child).

- [ ] **Step 3: Run the FULL suite.** `.venv/bin/pytest -q`. Expected: ALL PASS (Postgres up). Investigate any red before proceeding.

- [ ] **Step 4: Commit**
```bash
git add backend/tests/spine/test_e2e_fanout.py backend/tests/spine/test_e2e_journey.py backend/tests/spine/test_guest_dispatch.py backend/tests/spine/test_migration.py
git commit -m "test(spine): multi-intent e2e sentinel + zero-schema guard; update single-intent assumptions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task A6: Slice-7 frontend — enrich the split-echo receipt

**Files:**
- Modify: `frontend/src/shell/guest/hooks/use-conversation.ts` (additive types: `Req.split`, `Child.issue_label`, `Child.outcome`)
- Modify: `frontend/src/components/common/request-receipt.tsx` (per-child `issue_label` + status chip; gate on `split`)

**Subagent files (Opus):** ONLY the two files above. No new hook, no new route, no shadcn install in this task.

- [ ] **Step 1: Implement** the additive type fields; in `request-receipt.tsx` render, per child, `issue_label` (fallback to text) + the existing monochrome `StatusBadge` chip; render only when `split === true` (the component already early-returns for ≤1).

- [ ] **Step 2: Typecheck/build**

Run: `cd /workspace/Conduit-fanout-relocation/frontend && npm install --no-audit --no-fund -s && npm run build`
Expected: typecheck + build PASS.

- [ ] **Step 3: Commit**
```bash
cd /workspace/Conduit-fanout-relocation
git add frontend/src/shell/guest/hooks/use-conversation.ts frontend/src/components/common/request-receipt.tsx
git commit -m "feat(guest-ui): split-echo receipt — per-child label + status chip

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task A7: Phase-A gate

- [ ] **Step 1:** `cd backend && .venv/bin/pytest -q` → ALL PASS. `cd ../frontend && npm run build` → PASS. Do not start Phase B until both are green.

---

## Phase B — Slice 8: Relocation sub-flow (migration `0007`)

> Spec: `docs/superpowers/specs/2026-05-18-relocation-subflow-design.md`. Decisions locked: `issue_code.origin`; `ck_wo_kind+='relocation_move'`; move-task reuses the triggering child's `Request` with `predecessor_child_id` lineage; `RecRelocate` populate-not-add; one reserved accent.

### Task B1: Migration `0007` + `issue_code.origin` + `ck_wo_kind` widen + `FO-GUEST-MOVE` seed (TDD)

**Files:**
- Modify: `backend/conduit/shared/models/issue_code.py` (add `origin` mapped column + CHECK)
- Modify: `backend/conduit/shared/models/work_order.py` (widen `ck_wo_kind`)
- Create: `backend/migrations/versions/0007_relocation_subflow.py` (`down_revision='0006_conv_aa'`)
- Modify: `backend/conduit/seed.py` (idempotent `FO-GUEST-MOVE`, `origin='system'`)
- Test: `backend/tests/spine/test_migration_0007.py` (new), `backend/tests/spine/test_structural_guards.py`

**Subagent files (Opus):** ONLY the five files above. `RecRelocate` MUST stay byte-identical (populate-not-add — asserted).

- [ ] **Step 1: Write failing tests**

`backend/tests/spine/test_migration_0007.py`:
```python
from sqlalchemy import inspect
from conduit.shared.models import IssueCode, WorkOrder, RecRelocate

def test_revision_chain():
    import importlib
    m = importlib.import_module(
        "migrations.versions.0007_relocation_subflow")
    assert m.down_revision == "0006_conv_aa"

def test_issue_code_has_origin():
    assert "origin" in {c.name for c in inspect(IssueCode).columns}

def test_recrelocate_unchanged_populate_not_add():
    assert {c.name for c in inspect(RecRelocate).columns} == {
        "recommendation_escalation_id", "target_room_id"}
```
Add a structural guard asserting the seeded `FO-GUEST-MOVE` has `origin == "system"` and that `icdal.list_codes(..., origin="guest")` excludes it (signature: system code never enters the guest catalog).

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** per spec §6: add `origin text NOT NULL server_default 'guest'` + `CHECK(origin in ('guest','system'))` to `IssueCode`; widen `WorkOrder` `ck_wo_kind` to add `'relocation_move'`; write `0007_relocation_subflow.py` (`revision='0007_relocation_subflow'`, `down_revision='0006_conv_aa'`) doing the `ADD COLUMN` + CHECK + the `ck_wo_kind` drop/recreate, additive, with a clean `downgrade`; add `FO-GUEST-MOVE` to the idempotent seed (`origin='system'`, `fulfilment_mode='dispatch'`, sensible `routing_model`, `intent_kind='service'`, `is_reservation_mutation=false`).

- [ ] **Step 4: Run → pass.** Then `.venv/bin/pytest -q tests/spine/test_migration_0007.py tests/spine/test_structural_guards.py tests/spine/test_seed.py tests/spine/test_issue_codes.py` (the last two stay green — idempotent seed, unfiltered supervisor CRUD).

- [ ] **Step 5: Migration round-trip**

Run: `.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head`
Expected: returncode 0 each.

- [ ] **Step 6: Commit**
```bash
git add backend/conduit/shared/models/issue_code.py backend/conduit/shared/models/work_order.py backend/migrations/versions/0007_relocation_subflow.py backend/conduit/seed.py backend/tests/spine/test_migration_0007.py backend/tests/spine/test_structural_guards.py
git commit -m "feat(migration): 0007 — issue_code.origin + ck_wo_kind+=relocation_move + FO-GUEST-MOVE

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task B2: Guest catalog filtered to `origin='guest'` (TDD)

**Files:**
- Modify: `backend/conduit/supervisor/dal/issue_codes.py` (add optional `origin` filter param to `list_codes`)
- Modify: `backend/conduit/guest/services/intake.py` (call `list_codes(..., origin="guest")`)
- Test: `backend/tests/spine/test_structural_guards.py`

**Subagent files (Opus):** ONLY the three files above. The intake change is a single call-site argument; do NOT alter the Phase-A pipeline.

- [ ] **Step 1:** failing test: build catalog via the guest path with `FO-GUEST-MOVE` seeded → assert it is absent; supervisor `list_codes()` (no filter) → present.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3:** implement the optional `origin` filter (default None = unfiltered, back-compat) + the intake call-site.
- [ ] **Step 4:** run → pass; full guest/intake tests green.
- [ ] **Step 5:** commit `feat(intake): guest triage catalog excludes system codes (origin filter)`.

### Task B3: Pure `room_selection` (TDD)

**Files:**
- Create: `backend/conduit/shared/domain/room_selection.py`
- Test: `backend/tests/spine/test_room_selection.py` (new)

**Subagent files (Opus):** ONLY the two files above. Pure module — no DB, no clock, no imports of SQLAlchemy models for I/O.

- [ ] **Step 1: Write failing tests**
```python
from conduit.shared.domain import room_selection as rs

def test_excludes_occupied_and_current_deterministic():
    rooms = [("r1","101"),("r2","102"),("r3","103")]
    occupied = {"r2"}
    rec, elig = rs.select(rooms=rooms, occupied_room_ids=occupied,
                          current_room_id="r1")
    assert "r1" not in elig and "r2" not in elig
    assert elig == ["r3"] and rec == "r3"

def test_empty_when_none_available():
    rec, elig = rs.select(rooms=[("r1","101")], occupied_room_ids=set(),
                          current_room_id="r1")
    assert rec is None and elig == []
```
- [ ] **Step 2:** run → fail.
- [ ] **Step 3:** implement `select(*, rooms, occupied_room_ids, current_room_id) -> tuple[str|None, list[str]]` — available-only, deterministic order, current excluded; empty → `(None, [])`. Pure.
- [ ] **Step 4:** run → pass.
- [ ] **Step 5:** commit `feat(domain): pure room_selection (available-only, deterministic)`.

### Task B4: Wire recommendation + spine relocate (compute, persist, auto-proceed-safe) (TDD)

**Files:**
- Modify: `backend/conduit/shared/domain/recommendation.py` (the `relocate` branch carries the computed `target_room_id`)
- Modify: `backend/conduit/shared/engine/spine.py` (`_assemble_context` SERVICER_RAISED → engine-local rooms/occupancy read → `room_selection`; persist on `RecRelocate.target_room_id`; `_execute_action` resolves `stay_id`/`new_room_id`)
- Test: `backend/tests/spine/test_recommendation.py`, `backend/tests/spine/test_spine.py`

**Subagent files (Opus):** ONLY the four files above. Additive only — the inherited `test_apply_recommendation_relocate_closes_glitch` and `test_e2e_dispatch` leg (c) MUST stay green. Do NOT change the `relocate_stay` seam or the Glitch-close hop.

- [ ] **Step 1: Write failing tests** per spec §7.2/§11: servicer-raised + eligible room → `relocate{target_room_id=pick}` (params not LLM); none → `extend_sla` (regression); `open_escalation` persists `RecRelocate.target_room_id`; **silence/auto-proceed end-state ≡ approve** using the persisted room (signature equality except `resolved_by_account_id`).
- [ ] **Step 2:** run → fail.
- [ ] **Step 3:** implement per spec §7.2: engine-local read of property rooms + active-stay occupancy; call `room_selection.select`; set the recommendation `target_room_id`; persist; `_execute_action` reads the persisted `RecRelocate.target_room_id` (or the supervisor-edited value via the existing edited/overridden path) and resolves `stay_id` via the existing `child→Request→Stay` chain.
- [ ] **Step 4:** run → pass; run `tests/spine/test_spine.py tests/spine/test_recommendation.py tests/spine/test_engine.py` — inherited relocate tests still green.
- [ ] **Step 5:** commit `feat(spine): compute+persist relocate room; auto-proceed-safe (D9/D30)`.

### Task B5: Front-office move task spawn (TDD)

**Files:**
- Modify: `backend/conduit/shared/domain/lifecycle/__init__.py` (`_escalation_hops` relocate: after `relocate_stay`+Glitch-close, spawn the move child+WO)
- Modify: `backend/conduit/shared/engine/spine.py` only if a ctx field is needed for the spawn (additive)
- Test: `backend/tests/spine/test_spine.py` (or `test_lifecycle.py`)

**Subagent files (Opus):** ONLY the files above. Reuse the existing C4 routing path to create the WorkOrder; do NOT reimplement routing. The move `ChildSubRequest` reuses the triggering child's `request_id` and sets `predecessor_child_id = triggering_child.id`; issue code = `FO-GUEST-MOVE`; the WorkOrder `kind='relocation_move'`.

- [ ] **Step 1: Write failing test:** approve a servicer-raised relocate → assert exactly one new `ChildSubRequest` with `predecessor_child_id == trigger.id` and same `request_id`, exactly one `WorkOrder kind='relocation_move'`, it appears via `GET /servicer/tasks`, exactly one append-only event per transition.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3:** implement the spawn in `_escalation_hops` (relocate branch) reusing the routing hop.
- [ ] **Step 4:** run → pass; full spine/lifecycle/servicer suites green.
- [ ] **Step 5:** commit `feat(lifecycle): spawn front-office relocation_move task (predecessor lineage)`.

### Task B6: API enrichment — decision detail + resolve edit variant + guest relocated_to (TDD)

**Files:**
- Modify: `backend/conduit/supervisor/services/decisions.py` (populate relocate `detail`: `current_room`/`recommended_room`/`eligible_rooms`; handle `edit` `payload={"new_room_id"}` → 409/422 on occupied/unknown)
- Modify: `backend/conduit/guest/dal/requests.py` + `backend/conduit/guest/schemas/requests.py` (`DispatchCardOut.relocated_to: str|None`, additive output)
- Test: `backend/tests/spine/test_supervisor_decisions.py`, `backend/tests/spine/test_guest_dispatch.py`, `backend/tests/spine/test_structural_guards.py`

**Subagent files (Opus):** ONLY the five files above. ZERO new routes — `detail` and `payload` are already `dict`; only the service populates/validates more keys. Assert the route/contract snapshot does not drift.

- [ ] **Step 1: Write failing tests:** `GET /supervisor/decisions` relocate item carries `current_room`/`recommended_room`/`eligible_rooms`; `POST .../resolve` `edit {new_room_id}` re-binds to the chosen room; occupied/unknown → 409/422; `DispatchCardOut.relocated_to` set on a live sibling whose stay re-bound; all shapes parse back under `extra="forbid"`; snapshot unchanged.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3:** implement the additive service population + validation + the `relocated_to` projection.
- [ ] **Step 4:** run → pass; full supervisor/guest suites green.
- [ ] **Step 5:** commit `feat(api): relocate decision detail + edit variant + guest relocated_to (zero new routes)`.

### Task B7: Cross-slice sibling-rebind e2e (the integration proof) (TDD)

**Files:**
- Modify: `backend/tests/spine/test_e2e_dispatch.py` (extend leg (c): computed room + supervisor-edit + silent auto-proceed; assert the move WO spawns and is acceptable by a front-office servicer)
- Create: `backend/tests/spine/test_e2e_sibling_rebind.py` (fan `{AC, towel}` → AC relocates → towel sibling ambient re-resolves → `GET /guest/requests` shows `relocated_to`)

**Subagent files (Opus):** ONLY the two files above.

- [ ] **Step 1:** write both; **Step 2:** run → fail until prior tasks complete (they are complete here); **Step 3:** make green by fixing only test wiring (no product change — if a product gap appears, STOP and report); **Step 4:** run the FULL suite `.venv/bin/pytest -q` → ALL PASS; **Step 5:** commit `test(spine): cross-slice sibling-rebind e2e + extended relocate leg`.

### Task B8: Slice-8 frontend — relocation decision card, room picker, hover-card, accent, status taxonomy

**Files:**
- Run shadcn add (creates `frontend/src/components/ui/hover-card.tsx`)
- Create: `frontend/src/components/common/relocation-decision.tsx`, `frontend/src/components/common/room-picker.tsx`
- Modify: `frontend/src/shell/supervisor/hooks/use-decisions.ts` (additive `detail` types), `frontend/src/shell/guest/hooks/use-conversation.ts` (`DispatchCard.relocated_to`)
- Modify: `frontend/src/shell/supervisor/pages/decisions.tsx` (route `relocate` action to the new card), `frontend/src/components/common/child-status-card.tsx` (`relocated_to` line), `frontend/src/components/common/status-badge.tsx` (unified monochrome taxonomy), `frontend/src/index.css` (apply reserved `--accent-action` — one job)

**Subagent files (Opus):** ONLY the files above. Install primitive via the official command, then re-token. Accent is applied ONLY to decision-queue Approve + guest "All set". No new route/page; no new hook.

- [ ] **Step 1: Install the one new primitive**
```bash
cd /workspace/Conduit-fanout-relocation/frontend
npx --yes shadcn@latest add hover-card
```
Expected: `src/components/ui/hover-card.tsx` created (radix-nova style). Re-token to the OKLCH vars + `size="xs"` button idiom to match the codebase.

- [ ] **Step 2: Implement** `relocation-decision.tsx` (two-column current→proposed, `eligible_rooms` via `room-picker.tsx` over the existing `combobox-field`, comp note from the Glitch field, `Countdown` on `supervisor_sla_deadline`, Approve/Edit/Override; `hover-card` peeks origin + siblings); wire `decisions.tsx` to render it for `action==='relocate'`; add the `relocated_to` line to `child-status-card.tsx`; unify `status-badge.tsx` (monochrome taxonomy incl. P1–P4 weight, never chromatic); apply `--accent-action` only to the two specified primary actions.

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: typecheck + build PASS.

- [ ] **Step 4: Commit**
```bash
cd /workspace/Conduit-fanout-relocation
git add frontend/src/components/ui/hover-card.tsx frontend/src/components/common/relocation-decision.tsx frontend/src/components/common/room-picker.tsx frontend/src/shell/supervisor/hooks/use-decisions.ts frontend/src/shell/guest/hooks/use-conversation.ts frontend/src/shell/supervisor/pages/decisions.tsx frontend/src/components/common/child-status-card.tsx frontend/src/components/common/status-badge.tsx frontend/src/index.css
git commit -m "feat(ui): relocation decision card + room picker + unified status taxonomy + one-job accent

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase C — Full verification, push, PR

### Task C1: Full green gate

**Files:** none

- [ ] **Step 1: Backend full suite (Postgres up)**

Run: `cd /workspace/Conduit-fanout-relocation/backend && .venv/bin/pytest -q`
Expected: ALL PASS, coverage gate (`--cov-fail-under=90`) satisfied. If red, fix the responsible task before continuing — do not push red.

- [ ] **Step 2: Migration round-trip from a clean DB**

Run: `.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade base && .venv/bin/alembic upgrade head`
Expected: returncode 0 each.

- [ ] **Step 3: Frontend build**

Run: `cd ../frontend && npm run build`
Expected: PASS.

- [ ] **Step 4: No forbidden references / no env leak**

```bash
cd /workspace/Conduit-fanout-relocation
# Needle assembled from fragments so THIS file never contains the literal token/path.
B1=Lance; B2=Live
! grep -rInE -i "${B1}${B2}|${B1} ${B2}|/workspace/${B1}${B2}" backend/conduit backend/tests frontend/src docs/superpowers/plans docs/superpowers/specs/2026-05-18-*.md
git status --porcelain | grep -E '\.env$' && echo "FAIL: .env tracked" && exit 1 || echo "OK: no .env tracked, no forbidden refs"
```
Expected: prints `OK …` (non-zero grep = clean). If any hit, STOP and remove it.

### Task C2: Push and raise the PR

**Files:** none (git/PR)

- [ ] **Step 1: Confirm branch + clean tree**

Run: `cd /workspace/Conduit-fanout-relocation && git branch --show-current && git status --porcelain`
Expected: `feat/fanout-relocation`, empty status.

- [ ] **Step 2: Push**

Run: `git push -u origin feat/fanout-relocation`

- [ ] **Step 3: Open the PR**

```bash
gh pr create --base main --head feat/fanout-relocation \
  --title "Multi-intent fan-out + relocation sub-flow" \
  --body "$(cat <<'EOF'
Two stacked journey slices, additive on the merged conversation-answer-action substrate.

**Slice 7 — multi-intent fan-out + split-echo**
- Implements the deterministic `decompose()`/`triage()` pipeline (was stubbed).
- One message → N independent children; D36 split-echo (informational-only).
- Zero schema, zero migration. Single-need behaviour byte-identical.

**Slice 8 — relocation sub-flow**
- Pure `room_selection` (available-only, deterministic); recommendation room computed + persisted at build time (auto-proceed-safe).
- Real `relocate_stay()` re-bind + linked-Glitch close (invoked, not reimplemented).
- Front-office `relocation_move` task spawned (reuses the triggering Request; `predecessor_child_id` lineage).
- Sibling re-bind surfaced to the guest (`relocated_to`).
- Migration `0007_relocation_subflow` (`down_revision=0006_conv_aa`); `RecRelocate` populate-not-add.
- Zero new HTTP routes (response/payload enrichment only).

Full Postgres-backed suite green incl. coverage gate, migration round-trip, route/contract snapshot unchanged, cross-slice sibling-rebind e2e.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR created against `main`. Report the PR URL.

- [ ] **Step 4: Do NOT merge.** Leave the PR open for human review. Report the URL and the final `pytest -q` summary line.

---

## Subagent dispatch protocol (for the executing skill)

- Use **subagent-driven-development**: one fresh subagent per Task (A1…B8). Every `Agent` call MUST set `subagent_type: "general-purpose"` and **`model: "opus"`**. Never sonnet/haiku.
- Each subagent prompt MUST include: (a) the Task's exact "Subagent files" allow-list and an explicit "modify nothing else" instruction; (b) the two spec paths as the sole behavioural source of truth; (c) the hard rule forbidding the upstream product codename and any `/workspace/` product-source directory path; (d) the worktree path `/workspace/Conduit-fanout-relocation` and venv `backend/.venv/bin/pytest`; (e) the TDD steps verbatim; (f) "preserve slice-6 code verbatim" for any task touching `intake.py`/`spine.py`/`recommendation.py`.
- The orchestration tasks in Phase 0 and Phase C (worktree, venv, env copy, push, PR, recovery) are run by the **executor directly, not delegated**.
- Between tasks: executor runs the named test command and confirms PASS before dispatching the next subagent. Never advance on red.

## Self-review notes (done)

- **Spec coverage:** Slice 7 §7.1/§7.2/§7.3/§7.4 → A2/A3/A4; §11 → A1/A4/A5; §10 → A6. Slice 8 §6 → B1/B2; §7.1 → B3; §7.2/§7.3 → B4/B5; §8 → B6; §11 cross-slice → B7; §10 → B8. No spec section is unmapped.
- **Placeholders:** none — every code/test step shows code or an exact command + expected result; enumerations that are long (D5/D30 rule set, exhaustive field lists) explicitly defer to the in-repo spec section by number, which the engineer must open (a real, in-repo doc — not a TBD).
- **Type consistency:** `triage.decompose`/`triage.triage`/`TriagedChild.issue_label`, `RequestOut.split`, `ChildOut.issue_label/outcome`, `room_selection.select(*, rooms, occupied_room_ids, current_room_id)`, `RecRelocate.target_room_id`, `WorkOrder.kind='relocation_move'`, `issue_code.origin`, migration `0007_relocation_subflow`/`down_revision='0006_conv_aa'`, `DispatchCardOut.relocated_to` — used identically across all tasks.
