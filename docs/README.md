# Conduit — Documentation

The technical documentation for Conduit. Product scope and the numbered
product decisions (D-series) are the source of truth and live with the product
spec; everything here is the **technical counterpart** and introduces no
product decisions — only how to realise them.

## Doc sets

### [archi/](archi/) — Architecture

How Conduit is built and run.

- [archi/README.md](archi/README.md) — index + one-paragraph summary
- [archi/decisions.md](archi/decisions.md) — **AD-series**: every technical
  decision with its rationale *and the rejected alternative*. Read first.
- [archi/infrastructure.md](archi/infrastructure.md) — AWS inventory, cost,
  SSL termination, the timer engine
- [archi/code-structure.md](archi/code-structure.md) — planned repo layout
- [archi/risks.md](archi/risks.md) — accepted-risk register + open items

### [datamodels/](datamodels/) — Data Models

The conceptual → logical model. Deliberately low-opinion; **expected to
evolve** during build.

- [datamodels/README.md](datamodels/README.md) — conventions + how it evolves
- [datamodels/entities.md](datamodels/entities.md) — entities by stability
  (IDENTITY / CONFIG / SPINE)
- [datamodels/lifecycle.md](datamodels/lifecycle.md) — the state machines
- [datamodels/schema-draft.md](datamodels/schema-draft.md) — tentative
  field-level sketch + a full decision-coverage matrix

## Reading order

1. Product scope + decisions (D-series) — *the source of truth (with the
   product spec).*
2. [archi/decisions.md](archi/decisions.md) → the rest of [archi/](archi/) —
   how it runs and why.
3. [datamodels/](datamodels/) — the entities those decisions imply.

## Conventions

- **D-series** = product decisions (authoritative). **AD-series** =
  architecture decisions (this folder). On conflict, product decisions win.
- Data-model docs tag stability and flag what is *Provisional* / *Open* — what
  is committed vs what build will harden.
- Accepted risks are **named, not silent** (see
  [archi/risks.md](archi/risks.md)).
