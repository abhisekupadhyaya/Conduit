# Entities

Grouped by stability (see [README](README.md)). Attributes listed are the
**load-bearing** ones only — physical detail is deliberately omitted and will
be decided at build time.

```
IDENTITY            CONFIG (supervisor-owned)        SPINE (runtime core)
────────            ─────────────────────────        ────────────────────
Property            Section ── Room                  Request
  └ Account         Roster (per shift)                  └─* ChildSubRequest ──* Event (append-only)
  └ Stay ── Room    IssueCode ── SLAPreset                   ├─0..1 WorkOrder
                    EscalationLadder                         ├─* Timer
                    KBEntry                                  ├─* Escalation ──0..1 Recommendation
                                                             └─0..1 predecessor (modify lineage)
                                                       Glitch ──* ChildSubRequest
```

---

## IDENTITY

### Property `IDENTITY`
Single property in v1; modelled as one entity so multi-property is later
config, not a rewrite (AD9). *Open: whether anything is property-scoped now or
deferred entirely.*

### Account `IDENTITY`
A person who acts. **Carries:** role ∈ {guest, servicer, supervisor,
duty_manager}; status. Servicer-specific attributes (class ∈ {housekeeping,
engineering, room_service, concierge, runner}, skills, availability =
roster + manual break/off toggle) hang off the servicer role (D4/D12/D18/D39).
*Open: one Account table with role-specific extensions vs separate Staff/Guest
— deliberately unresolved.*

### Stay `IDENTITY`
Binds a guest Account to a Room for a date range, plus reservation facts
(late-checkout, billing, etc. — the things D24 mutations touch). **The
room binding is re-bindable mid-stay** (relocation, D20/D29). Ambient
{guest, room, section} is derived from the active Stay at session time
(D3a/D29/D32) — Conduit owns this; no PMS.

### Room `IDENTITY` / bridges to `Section`
A physical room. Maps to exactly one housekeeping Section at a time (D12).
*Provisional: room→section as a field on Room vs a mapping entity — leave open;
it may need history if sections are re-cut per shift.*

---

## CONFIG (supervisor-owned; rows, edited at runtime)

### Section `CONFIG`
A housekeeping positional zone. Has an accountable owner + backup **per
shift** via Roster (D12).

### Roster `CONFIG`
Per-shift assignment: which servicers are on-shift, section owner/backup,
engineering skills present. Routing and availability read this (D12/D18/D39).
*Open: shift modelled explicitly vs roster rows time-bounded — left open.*

### IssueCode `CONFIG`
The classification target — **the join point** (D34). **Carries:** department;
servicer class; SLA preset ref; routing model ∈ {section_pooled, skill_matched,
none} (D12 vs D18 vs no-dispatch); fulfilment mode ∈ {dispatch, no_dispatch}
(D4); reservation-mutation flag → always-flag (D24/D30); **intent kind ∈
{service, problem_report}** — a problem_report opens a Glitch at triage (D43).
System-default set + supervisor-customizable (D34). An unmatched intake is the
*absence* of a code → clarify → flag, never dropped (the "uncategorized" path).

### SLAPreset `CONFIG`
A tunable timing bundle (P1–P4). **Carries:** accept-window duration,
fulfilment-SLA duration, supervisor-SLA duration (D9/D15/D23). Only the *tier
definitions* are fixed; the minutes are property config.

### EscalationLadder `CONFIG`
The escalation path + the non-time-boxed duty manager backstop and its
N-cycle bound (D21).

### KBEntry `CONFIG`
A curated fact for grounding no-dispatch answers (D26). Small, supervisor-
edited. *Open: keyed/topic retrieval vs embeddings — modelling-neutral here;
flagged in archi as a build decision.*

---

## SPINE (runtime core)

### Request `SPINE`
The raw intake. **Carries:** originating guest/stay (ambient), raw text,
channel (text only, v1), created_at. Decomposed into N children (D35); if
>1, the split is echoed back (D36). The Request itself is largely immutable
after decomposition — it is a container, not the unit of work.

### ChildSubRequest `SPINE` — *the unit*
The single most important entity. Routing, SLA, lifecycle, and closure all
attach **here**, never to the raw Request (D35). **Carries:** parent Request;
issue code (resolved by triage); triage outcome ∈ {AUTO, CLARIFY, FLAG,
NO_DISPATCH} (D5/D30); fulfilment mode (D4); **priority tier P1–P4** — derived
from the issue code's SLA preset and **independent of the triage outcome**
(a P1 can be fully AUTO — D20); `uncategorized` when no code matched (D34);
`is_problem_report` (from the code's intent kind → drives Glitch, D43);
`revised_eta` set on a stall and shown to the guest (D22); SLA preset in
force; lifecycle state (see [lifecycle.md](lifecycle.md)); closure state incl.
closure-lite for no-dispatch (D8/flow 04); cancel/modify lineage —
`predecessor` link, since modify = cancel + recreate (D38).
*Provisional: triage detail (slot completeness, deterministic-risk evaluation,
LLM-raised risk, clarify budget used) — embedded vs a TriageResult entity left
open; it is information, treat it as evolvable.*

### WorkOrder `SPINE`
Exists for dispatch-mode children **and** for the one no-dispatch exception —
a human-concierge deferral (D25). **Carries:** the child; `kind` ∈ {dispatch,
human_concierge_answer}; `routing_model` ∈ {section_pooled (D12),
skill_matched (D18)}; assigned servicer; **accountable owner** (stays
accountable even when a claim-fallback claimant executes — D12);
claim-fallback/broadcast state; priority tier + queue position (engineering is
skill-scarce, P1 preempts — D18); accept / in-progress / complete + completion
notes (notes-only v1 — D16/D28). Grounded no-dispatch children have *no*
WorkOrder — they resolve via NoDispatchResolution.

### NoDispatchResolution `SPINE`
The no-dispatch outcome (flow 04). **Carries:** the child; mode ∈
{grounded_answer, human_deferral} (D25); answer text; **grounding provenance**
— which reservation fields / KB entries the answer was built from, for
anti-hallucination and audit (D26); closure-lite "did this help?" signal (D8
-lite); a link to the concierge WorkOrder when deferred. The *answer↔action
seam*: a follow-up that mutates the reservation is a **new** request on the
flag path (D24), not a mutation of this. *Open Q7: separate entity vs fields
on the child — tentative.*

### CrossDeptNotification `SPINE`
A completion in one department unblocking/notifying another — maintenance
clears a room → notify housekeeping + front desk (D14, an explicit lifecycle
element). **Carries:** the source completion (work order); target department;
optionally the child it unblocks; reason. *Open Q6: a first-class table vs
purely event-derived — modelled explicitly because D14 names it first-class,
but tentative.*

### Timer `SPINE`
A durable scheduled obligation (AD5). **Carries:** subject (a child / work
order / escalation); type ∈ {accept_window, fulfilment_sla, supervisor_sla,
backstop_cycle}; fire_at (DB time); state ∈ {pending, fired, cancelled}.
Written in the same transaction as the transition that creates it. Cancel/
modify cancels the child's pending timers (D23/D37/D38).

### Escalation / DecisionItem `SPINE`
What lands in the supervisor decision queue. **Carries:** the child; trigger ∈
{triage_flag, stall, servicer_raised} (D9/D20); the AI **Recommendation** (the
human never gets a blank ticket — D7/D9); outcome ∈ {approved, edited,
overridden, auto_proceeded} ; cycle count → hard-escalate to duty manager at
the bound (D21). *Provisional: Recommendation embedded vs its own entity —
open.*

### Glitch `SPINE`
A service-quality **annotation riding one or more children** (D43/D14) — not
the unit of work, a parallel marker. **Carries:** the child(ren) it annotates;
opened-from intent (problem-report / D8 dispute); state (open / held-open /
auto-closed-with-underlying — D44); recovery-owed flag + recovery cost as a
**manual field** (no automated comp in v1 — D19). Routine asks never become
glitches.

### Event `SPINE` — *append-only*
The spine of observability. **Carries:** producer (portal/actor/system);
subject (child / work order / escalation / glitch / stay); type; payload;
at. Every state transition appends one. Awareness stream and analytics are
**read models over this**, never over the core tables (D1/D28, dataflow
§C/D). New event types are additive — this is the primary evolution seam.

---

## Deliberately out / deferred (not oversights)

- **Notification** — v1 is in-portal, passive (FR-27/D42). Likely a read model
  over Event, not a stored entity. Left unmodelled on purpose.
- **AnalyticsAggregate** — derived from Event (FR-30); not core-modelled.
- **Audit trail / CSAT / degraded-mode** — product-level deferrals (PRD §12);
  noted so their absence is conscious.
- **Inventory loop, mass-events, RBAC, i18n** — out of v1 scope (D16/D27/D41);
  no entities here by design.

## Open modelling questions (for us, as we execute)

1. Account: unified with role extensions vs split Guest/Staff?
2. Room→Section: field vs mapping entity — does it need history (shift re-cuts)?
3. TriageResult and Recommendation: embedded in their parent vs own entities?
4. Roster/Shift: explicit Shift entity vs time-bounded roster rows?
5. Closure: state on ChildSubRequest vs its own entity (no-dispatch uses
   closure-lite — D8) ?
6. CrossDeptNotification: a first-class table vs purely event-derived (D14)?
7. NoDispatchResolution: own entity vs fields on ChildSubRequest?
8. Revised ETA (D22): a column on the child vs an event payload only?

None of these block the shape; all are intentionally left for build, when
real query patterns decide them.
