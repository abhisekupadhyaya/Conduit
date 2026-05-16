# Infrastructure

The AWS resource inventory, cost, TLS termination, and the timer engine.
Decisions and their rationale: [decisions.md](decisions.md).

## Topology

```
                 git push
  developer ───────────────► AWS Amplify (frontend SPA)
                               │  CDN + managed TLS
   browser ──TLS──────────────┤
                               │  /api/*  reverse-proxy rewrite (server-side)
                               ▼
                         api.<domain> ─► EIP ─► EC2 (public subnet)
                               │  Caddy: TLS (Let's Encrypt, auto-renew)
                               ▼  localhost:PORT (loopback, plaintext)
                         ECS task  (FastAPI API + in-process engine)
                               │  TLS (sslmode=require)
                               ▼
                         RDS PostgreSQL (private subnet, single-AZ, PITR)

   ECS task ──IGW egress──► OpenAI API (GPT-5.4-mini)
```

## Resource inventory

| Layer | Resource |
|---|---|
| Network | 1 VPC, public subnet (EC2 + EIP), private subnet (RDS). SG: 80/443 to EC2, 5432 RDS-from-EC2 only. **No NAT** (egress via IGW). |
| Compute | ECS cluster (free) · 1× `t4g.small` EC2 container instance · 1 task definition · ECS service desired-count 1 · ECR repo · Caddy on host · Elastic IP |
| Data | RDS PostgreSQL `t4g.micro`, single-AZ, gp3, automated backups + PITR. `sslmode=require`. |
| Frontend | AWS Amplify Hosting (CDN + managed TLS + git CI/CD), `/api/*` reverse-proxy rewrite |
| Secrets | SSM Parameter Store SecureString — OpenAI key, DB creds, JWT signing secret (Parameter Store standard tier is free) |
| Observability | CloudWatch logs (7-day retention) + metrics + alarms · SNS → ops email |
| DNS | Route 53 hosted zone · `A` record `api.<domain> → EIP` (also enables the ACME challenge) |
| IaC | Terraform, single env, S3 state + DynamoDB lock table (IaC plumbing — the only DynamoDB anywhere) |

**Prerequisite:** a registered domain (Amplify custom domain + the Caddy API
endpoint both need it).

## SSL / TLS

Two surfaces, both auto-managed — **no manual cert ops**:

1. **Browser → frontend:** Amplify provisions and auto-renews the cert (ACM +
   CloudFront under the hood).
2. **Browser → `/api/*` → backend:** the Amplify rewrite fetches `/api/*`
   server-side from **Caddy on EC2**, which obtains and auto-renews a **Let's
   Encrypt** cert (ACME, 90-day) for `api.<domain>`, then proxies to the ECS
   task over **loopback plaintext** (never leaves the host).
3. **Backend → RDS:** TLS enforced (`sslmode=require`, RDS CA bundle).

Requirements: `A` record `api.<domain> → EIP` (ACME challenge); SG open on 80
(challenge) + 443 (Amplify proxy). WAF deferred (D27 puts abuse out of v1).

## Timers (the engine)

DB-backed timers + an in-process poller. This is the riskiest, most-tested
component — see [code-structure.md](code-structure.md) `backend/conduit/engine/`.

- **Storage:** `due_timers` rows written **in the same transaction** as the
  state transition that creates them. Per child: accept-window + fulfilment-SLA
  (D23); plus supervisor-SLA (D9) and a cycle counter for the bounded backstop
  (D21). Index `(state, fire_at)`.
- **Poller** (`engine/runner.py`, in-process): every ~5–15 s —
  `SELECT … WHERE state='pending' AND fire_at <= now() FOR UPDATE SKIP LOCKED
  LIMIT k`, fire each (stall→spine, supervisor-silence→auto-proceed,
  N-cycles→hard-escalate), append to the event log, mark fired, commit.
  `SKIP LOCKED` ⇒ no double-fire even with a second poller.
- **Time source:** the DB's `now()`, never the host clock. Precision = poll
  interval; SLAs are minutes, so seconds-level is ample.
- **Durability:** timers live in Postgres, not memory. EC2/container restart
  (deploy blip R4, crash, ECS replacement) loses nothing — boot resumes
  everything already due. This is what keeps "nothing silently lost" intact on
  single-instance infra.
- **Cancel/modify:** cancel marks the child's timers cancelled in the same
  txn; modify = cancel + recreate with fresh `fire_at` (FR-22/23).
- **Failure isolation:** per-timer try/except; failed transition →
  `failed_transitions` table **+ alarm** (never silent); loop continues.
- **Sweeper** (`engine/sweeper.py`): slower loop hunting timers that should
  have fired but did not, and orphaned states; emits the **"age of oldest
  unfired timer"** custom metric → alarm. The watchdog-over-the-watchdog that
  justifies running this on one cheap box.

## Cost (monthly, single property / single env)

| Line | Monthly |
|---|---|
| EC2 `t4g.small` (Savings Plan ~$8 / on-demand ~$12) | ~$8–12 |
| RDS `t4g.micro` single-AZ + PITR | ~$14 |
| Public IPv4 / EIP | ~$4 |
| EBS + ECR + CloudWatch + Route 53 + data transfer | ~$10 |
| Amplify Hosting (near free-tier at this volume) | ~$1–5 |
| ECS control plane | $0 |
| **AWS total** | **~$37–45/mo** |
| + OpenAI GPT-5.4-mini (external, usage-based) | ~$5–20 |
| **All-in** | **~$45–65/mo** (~$40 AWS with an EC2 Savings Plan) |

Floor is **RDS + EC2 + IPv4**. Managed Postgres is the largest line and the
one deliberately not cut (AD3). EC2 Spot (~$4) is possible but adds churn for
an always-on host — Savings Plan preferred over Spot here.
