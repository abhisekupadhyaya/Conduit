# Conduit

An AI-driven, **self-contained, single-property guest-request orchestrator**.

A guest asks for something in plain text. Conduit understands it, splits a
multi-part ask into independent sub-requests, triages each mechanically,
routes it straight to the accountable person, owns the full task lifecycle
(timers, stalls, escalation, closure), keeps the guest informed, and surfaces
only exceptions to a human supervisor who acts as a *time-boxed checkpoint —
never a bottleneck*. Management gets a live operational view.

The human who does the physical work stays human. The human coordination
layer that decided *who* does it and *when* is what Conduit replaces.

## Status

**Planning / design.** No application code yet. The architecture and the data
model are drafted and converged; the data model is deliberately marked
*subject to change* until build hardens it.

| Area | State |
|---|---|
| Product scope & decisions | Defined (D-series), the source of truth |
| Infrastructure architecture | Converged — see [docs/archi/](docs/archi/) |
| Data model | First draft, evolvable — see [docs/datamodels/](docs/datamodels/) |
| Backend / frontend code | Not started |

## Shape (planned)

Single FastAPI backend (the lifecycle engine runs in-process) in a container
on ECS/EC2, fronted by Caddy for API TLS; a single React SPA on AWS Amplify;
durable state and timers in managed Postgres (RDS). One environment,
Terraform-defined. Detail and rationale in [docs/archi/](docs/archi/).

Planned repository layout (when code begins):

```
backend/    FastAPI: per-portal slices (guest/servicer/supervisor/public) + in-process engine
frontend/   React SPA: one shell per portal
dev-ops/    terraform/ + scripts/  (AWS)
docs/       architecture + data models  ← currently the only populated tree
```

The full intended structure is in
[docs/archi/code-structure.md](docs/archi/code-structure.md).

## Documentation

Start at [docs/](docs/). Read order: the product scope/decisions, then
[docs/archi/](docs/archi/) (how it runs), then
[docs/datamodels/](docs/datamodels/) (the entities those decisions imply).

## Principle

The product promise is *"nothing is silently lost."* That durability lives in
the database state machine and its timers — not in redundant infrastructure —
which is why the data model and the timer engine are treated as the most
load-bearing parts of this system.
