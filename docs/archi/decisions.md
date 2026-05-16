# Architecture Decisions

Numbered, reasoned, with the alternative we rejected. The AD-series is the
technical analogue of the product's D-series (the product decisions log). On
any conflict with the product decisions, the product decisions win.

---

### AD1 — Compute: ECS on EC2 (EC2 launch type)

One container running on a single `t4g.small` EC2 instance registered to an
ECS cluster; ECS service desired-count 1.

**Why:** at one property the load is modest and steady — there is no
autoscaling, scale-to-zero, or bin-packing for Fargate to earn its premium on.
A single always-on Fargate task behind an ALB is the worst of both: the
elasticity tax and the LB tax for zero elasticity. ECS (control plane free)
keeps task-definition/deploy tooling identical to a future Fargate move if
multi-property ever lands.

**Rejected:** Fargate + ALB (premium for unused elasticity; ALB hourly + LCU +
constant health-check pings on one static target). Plain EC2 without ECS
(simplest, but loses the portable deploy model and Fargate-parity path).

### AD2 — No load balancer; Caddy on the host

The ECS task binds a **static host port**; **Caddy** on the EC2 host
terminates TLS and reverse-proxies to it. An **Elastic IP** gives the stable
address an ALB would otherwise have provided, for the price of the IPv4 charge.

**Why:** removes ALB cost entirely; Caddy gives automatic Let's Encrypt
certs with zero cert ops. See [infrastructure.md](infrastructure.md) §SSL.

**Rejected:** ALB/NLB (cost, unused at this scale), API Gateway (stable-origin
problem still needs an LB or unstable task IP).

### AD3 — Data: managed RDS Postgres, single-AZ `t4g.micro`, PITR

**Why:** the product's load-bearing invariant is "nothing is silently lost"
(D10/D23). That promise physically lives in durable DB state and timers, so
the database is the one component **not** cost-optimised: it stays managed,
with automated backups + point-in-time recovery. Single-AZ is the accepted
cost trade (R2) — it costs availability minutes on failure, never data.

**Rejected:** Postgres co-located on the EC2 box (eliminates ~$14/mo but puts
the core durability promise on an unmanaged single disk — refused). Multi-AZ
(~+$30/mo redundancy not warranted for a single-env pilot). Aurora Serverless
v2 (min 0.5 ACU never cheaper than `t4g.micro` for always-on; never idles
because the engine polls every cycle).

### AD4 — Backend is one deployable; the engine runs in-process

The lifecycle/timer engine is an asyncio background task **inside the API
container**, not a separate service.

**Why:** at one property the engine's volume does not justify its own service;
DB-backed timers (AD5) survive an API restart, so co-location costs nothing in
durability. Halves the compute footprint vs a second service.

**Rejected:** a separate `conduit-engine` service (the second-deployable
async-worker shape — correct at multi-tenant scale, ceremony here).

### AD5 — Timers: DB-backed rows + in-process poller

Timer rows written in the **same transaction** as the state transition that
creates them; an in-process loop polls `WHERE state='pending' AND fire_at <=
now() FOR UPDATE SKIP LOCKED`. Time source is the DB's `now()`. A slower
**sweeper** loop hunts timers that should have fired but did not and emits a
CloudWatch metric + alarm.

**Why:** keeps timers and the state they govern transactionally co-located in
one store; crash-safe (restart resumes everything already due) which preserves
"nothing silently lost" on cheap single-instance infra; `SKIP LOCKED` keeps it
correct if a second poller ever runs. Detail in
[infrastructure.md](infrastructure.md) §Timers.

**Rejected:** Step Functions / EventBridge Scheduler (extra managed service,
timer/state split across two systems; volume here does not need it).

### AD6 — Frontend: AWS Amplify Hosting, single SPA

One React SPA, role-routed to a per-portal "shell" (guest/servicer/
supervisor). Amplify provides CDN + managed TLS + git CI/CD; an Amplify
**reverse-proxy rewrite** sends `/api/*` server-side to the Caddy/EC2
backend — single origin, **no CORS**, frontend deploy decoupled from backend.

**Caveat:** the Amplify proxy suits the polling-first real-time model (AD7).
If SSE/WebSocket is adopted later, the SPA must call `api.<domain>` directly
with CORS.

**Rejected:** CloudFront + S3 hand-rolled (Amplify is that, managed, for ~the
same money); Caddy serving the SPA (loses CDN + git CI/CD).

### AD7 — Real-time: polling-first

In-portal updates (awareness stream, decision queue, guest status) via short-
interval polling. SSE/WebSocket deferred.

**Why:** the product mandates in-portal, passive notifications only
(FR-27/D42); supervisor-SLA is minutes, so a few-second poll is well within
tolerance. WebSocket would drag in a Redis/ElastiCache connection backplane —
unjustified at one property in v1.

**Rejected:** SSE + Postgres `LISTEN/NOTIFY` (nicer feel, fanout complexity);
WebSocket + ElastiCache (backplane cost/complexity).

### AD8 — Auth: app-managed JWT, no Cognito

Own users/sessions, JWT, room/section as ambient session context that the
relocation event mutates (D20/D29/D32).

**Why:** guests are supervisor-provisioned, stay-scoped, and relocation
re-binds the account's room mid-stay — a lifecycle Cognito fits poorly.
A conventional app-managed JWT/session pattern handles it cleanly.

**Rejected:** Cognito user pools (ephemeral, re-bindable, supervisor-
provisioned identities map awkwardly).

### AD9 — Single environment, Terraform, parameterised

One environment for v1; Terraform modules parameterised so adding
dev/staging/prod later is a variable flip, not a rewrite.

**Why:** the product spec scopes a single property; multi-env redundancy is not warranted
yet but should not require restructuring later.

### AD10 — Dropped from the reference template

No multi-tenancy (`{tenant_slug}` prefix, tenant models, `super_admin`
portal), no RBAC engine (`core/rbac.py`). Conduit is one property, three fixed
roles via simple dependency gates.

**Why:** the product spec puts RBAC explicitly out of scope; single property removes the
multi-tenant need. Net simplification over the reference.

### AD11 — LLM: OpenAI GPT-5.4-mini, external, bulkheaded

Calls go out via the host's Internet Gateway egress. Wrapped in a timeout +
circuit breaker; failures fall into paths the **product already defines** —
decomposition failure → conservative/flag-to-supervisor; grounded-answer
failure → the existing "ungroundable → human concierge" path (D25).

**Why:** the product's degraded paths double as the LLM-outage fallback, so an
external dependency on the request path degrades rather than stalls the
lifecycle. Privacy note: guest text + reservation context leaves the AWS
boundary — minimise PII in prompts (room/section codes over names where the
task allows), rely on API-tier no-train default + a DPA.

**Rejected:** Amazon Bedrock (in-account boundary — not chosen by the
operator); deferring provider choice.
