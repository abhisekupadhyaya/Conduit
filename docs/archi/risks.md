# Accepted Risks & Open Items

Same discipline as the product's stress-test register: risks are **named and
consciously accepted**, not silent.
The infra trades *redundancy* for cost; the product's reliability promise is
unaffected because durability lives in managed Postgres (AD3/AD5), not in the
metal.

## Accepted risks

| ID | Risk | Disposition / mitigation |
|---|---|---|
| **R1** | **No compute HA.** Single EC2 box; box loss = full outage until recovery. | Accepted for v1/single-env. CloudWatch instance auto-recovery + a tested AMI/restore runbook. **Data is safe in RDS throughout** — only availability is lost. |
| **R2** | **Single-AZ database.** Instance/AZ failure costs minutes of recovery. | Accepted. Automated backups + PITR intact; no data loss. Multi-AZ is a one-variable upgrade (AD3) when warranted. |
| **R3** | **Single egress path.** No NAT redundancy; OpenAI unreachable on egress failure. | Accepted. Falls into the product's existing "ungroundable → human concierge" path (D25/AD11). Degrades, does not break. |
| **R4** | **Deploy blip.** One box + one task ⇒ a rolling deploy is a brief stop-then-start. | Accepted for a pilot. Alternative (size the box to hold 2 tasks transiently for zero-downtime) deferred. DB-backed timers (AD5) survive the blip. |

These mirror the product's consciously-accepted findings (G7/D42): the
*kind* of trade-off, not a regression of the promise.

## Open items

| Item | State |
|---|---|
| Timer mechanism | **Decided** — DB-poll (AD5). EventBridge Scheduler was the rejected alternative. |
| Real-time delivery | **Decided** — polling-first (AD7). SSE/WebSocket deferred; revisit triggers the Amplify-proxy caveat (AD6). |
| Domain / DNS | **Open prerequisite** — a registered domain is required (Amplify custom domain + Caddy API endpoint). Blocks edge + TLS. |
| WAF | **Deferred** — D27 puts abuse/flooding out of v1 scope. Minimal rate-limit rule is the first add if a pilot shows need. |
| Zero-downtime deploy | **Deferred** (R4) — revisit if the deploy blip is unacceptable in practice. |
| Multi-AZ DB / compute HA | **Deferred** (R1/R2) — parameterised to enable later without restructuring (AD9). |

## First revisit targets (if a pilot shows strain)

1. R1 — compute HA (a second instance / ASG) if outage windows bite.
2. Domain/DNS — must be resolved before any deploy.
3. WAF rate-limit — if abuse appears despite D27's scoping.
