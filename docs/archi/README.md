# Conduit — Architecture

How Conduit is built and run. Product scope/requirements live separately in the
the product spec + decisions log (D-series); **this folder is the technical
counterpart** and introduces no product decisions — only how to realise them.

| | |
|---|---|
| **Status** | Converged draft (2026-05-16) |
| **Scope** | v1 — single property, single environment |
| **Source of truth** | [decisions.md](decisions.md) (AD1–ADn). Other files synthesise it. |

## Files

- [decisions.md](decisions.md) — numbered architecture decisions (AD-series)
  with reasoning + alternatives considered. **Read this first.**
- [infrastructure.md](infrastructure.md) — the AWS resource inventory, cost,
  SSL termination, and the timer engine. The "what runs where".
- [code-structure.md](code-structure.md) — repo/folder layout, backend +
  frontend + dev-ops.
- [risks.md](risks.md) — accepted-risk register (R1–R4) and open items.

## One-paragraph summary

Conduit is a self-contained, single-property guest-request orchestrator. The
backend is a single FastAPI deployable (the lifecycle **engine runs in-process**)
in a container on **ECS/EC2** (one `t4g.small`), fronted by **Caddy** on the
host for API TLS. The frontend is a single React SPA on **AWS Amplify** which
reverse-proxies `/api/*` to the backend. State and durable **timers live in
managed Postgres (RDS)** — that is where the product's "nothing silently lost"
promise physically lives, which is why it is the one component we do not
cost-optimise away. Everything is Terraform, one environment, ~$40/mo AWS.
