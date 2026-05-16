# Conduit — Data Models

The conceptual/logical model. Traces to the product's data-movement spec
(§A/B/C) and decisions (D-series). It is the technical design the PRD §12
names as the build blocker.

| | |
|---|---|
| **Status** | First draft (2026-05-16) — **expected to evolve during build** |
| **Level** | Conceptual/logical. **Not** physical schema. |
| **Source of truth** | Product `decisions.md` (D1–D44) for *what*; this for *shape*. |

## Files

- [entities.md](entities.md) — the entities, grouped by stability, with the
  load-bearing attributes and relationships only.
- [lifecycle.md](lifecycle.md) — the state machines for the things that move
  (child sub-request, work order, escalation, glitch, timer).
- [schema-draft.md](schema-draft.md) — a **tentative detailed** field-level
  sketch (indicative types). Concrete enough to picture; explicitly marked
  subject to change, with a firm-vs-soft breakdown.

## How to read this (and how it evolves)

This is intentionally **low-opinion**. We commit to the *entities, their
relationships, and their states* — those are load-bearing and trace to
product decisions. We **do not** commit yet to: physical types, primary/foreign
key strategy, indexes, or whether a thing is an embedded structure vs its own
table. Those are build-time calls and will change.

Conventions:

- **Stability tag** per entity:
  - `SPINE` — load-bearing runtime core; shape is stable, change with care.
  - `CONFIG` — supervisor-owned setup data; *rows*, not schema — expected to
    be edited constantly at runtime (issue codes, SLA presets, sections…).
  - `IDENTITY` — accounts, stays, rooms.
- *Provisional* marks an attribute/relationship we expect to revisit.
- *Open* lists modelling questions deliberately left unresolved.

Evolution principles we are designing toward (so change stays cheap):

1. **The append-only event log decouples consumers.** Awareness stream and
   analytics read events, not core tables — new consumers/event types are
   additive (D1/D28, dataflow §C/D).
2. **The child sub-request is the unit** of routing, SLA, closure — never the
   raw message (D35). Everything hangs off the child.
3. **Modify = cancel + recreate**, never in-place mutation (D38) — history is
   lineage, not overwrites.
4. **Config is data, not schema** (product principle 8 / D12-D13). Adding an
   issue code or SLA tier is a row, never a migration.
5. **Mechanism in code, structure in data** — do not encode business rules in
   schema constraints; keep the model permissive so rule changes don't
   migrate data.
