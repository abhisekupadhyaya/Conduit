# Lifecycles

State machines for the things that move. States trace to product decisions;
**transitions, not storage**. Names are indicative and may be renamed in
build — the *shape* is the commitment.

## ChildSubRequest — the central lifecycle

```
                    ┌──────────── CLARIFY (budgeted ~1–2 turns) ───┐
                    ▼                                              │
 INTAKE ─► TRIAGED ─┼─ AUTO ───────────────► ROUTING ─► … ─► CLOSED
                    ├─ FLAG ──────► (Escalation/decision queue)
                    └─ NO_DISPATCH ─┬─ grounded ─► ANSWERED ─► CLOSED(lite)
                                    └─ ungroundable ─► CONCIERGE_QUEUE ─► …

 ROUTING ─► PUSHED/BROADCAST ─► ACCEPTED ─► IN_PROGRESS ─► DONE_PENDING_CONFIRM
                                                                  │
                          guest confirms ──► CLOSED               │
                          guest "no" ──────► REOPEN ─► (re-enter)  │
                          no response ─────► stays open (ages, supervisor-visible)

 Any state ──(supervisor takeover/reassign/cancel)──► interrupt (D6)
 Any state ──(guest cancel until Closed)──► CANCELLED (notify committed servicer, D37)
 modify ──► CANCELLED + new ChildSubRequest via INTAKE (predecessor link, D38)
```

Notes:
- The child is the unit; children of one Request **never share fate** (D35).
- Triage is mechanical: slot-completeness + deterministic risk rulebook; LLM
  may only *raise* risk (D5/D30).
- Reservation/revenue mutations never go AUTO — always FLAG (D24).
- Closure is guest-final; no response keeps it open and aging, not closed;
  no-dispatch uses closure-lite (D8).
- "Interruptible from every state" is a property of the machine, not a state
  (D6) — model as guarded transitions, not a special node.

*Open: whether CLARIFY / REOPEN are states or sub-states; whether closure is a
nested machine on the child or its own entity (entities.md Q5).*

## WorkOrder (dispatch mode only)

```
CREATED ─► (PUSHED to section owner | BROADCAST claim-fallback) ─► ACCEPTED
        ─► IN_PROGRESS ─► COMPLETED(notes)
CREATED/PUSHED ──accept-window breach──► STALL ─► (Escalation)
ACCEPTED/IN_PROGRESS ──fulfilment-SLA breach──► STALL ─► (Escalation)
any ──servicer "cannot resolve"──► raises Escalation (D20 trigger 3)
```

The **accountable owner** does not change when a claim-fallback claimant
executes — owner stays accountable to Closed/SLA (D12). Two timers run; stall
fires on whichever breaches first (D23). Engineering work orders are not
section-pooled: skill-match → least-loaded → **priority queue, P1 preempts**
(D18).

**On COMPLETED:** a completion may emit a `CrossDeptNotification` — one
department's done-state unblocks/notifies another (maintenance clears a room →
housekeeping + front desk, D14). This is part of the lifecycle, not a
side-effect.

## NoDispatchResolution (the second fulfilment mode — flow 04)

```
TRIAGE no_dispatch ─┬─ groundable (reservation + KB) ─► GROUNDED_ANSWER ─► closure-lite "did this help?"
                    │                                     └─ "no" ─► escalate
                    └─ ungroundable ─► HUMAN_DEFERRAL ─► concierge WorkOrder(kind=human_concierge_answer)
 follow-up mutates reservation/revenue ─► leaves no-dispatch ─► NEW request on the D24 flag path
```

Never free-formed: a grounded answer records *which* reservation fields / KB
entries it used (D26). Ungroundable never guesses — honest deferral to a human
concierge (D25). The answer↔action seam (D24) is a hard boundary, not a state.

## Escalation / DecisionItem

```
OPEN(with AI Recommendation) ─► supervisor: APPROVED | EDITED | OVERRIDDEN
                              └► silence past supervisor-SLA ─► AUTO_PROCEEDED
AUTO_PROCEEDED ×N cycles ─► HARD_ESCALATED (duty manager, non-time-boxed, D21)
```

Every path carries a Recommendation — never a blank ticket (D7/D9). The
supervisor is a time-boxed checkpoint everywhere except the D21 floor.

## Glitch (annotation, parallel)

```
OPEN ─┬─ underlying child(ren) resolved ─► AUTO_CLOSED
      └─ supervisor holds (recovery owed) ─► HELD_OPEN ─► (manual close)
```

Rides the child(ren); auto-closes with them unless held; recovery cost is a
manual field, no automated comp v1 (D43/D44/D19). Surfaced on the awareness
stream throughout (D14).

## Timer

```
PENDING ──fire_at ≤ now()──► FIRED (transition applied, Event appended)
PENDING ──child cancel/modify──► CANCELLED
```

Durable; crash-safe (restart resumes due timers); `SKIP LOCKED` poll prevents
double-fire (AD5; archi `infrastructure.md` §Timers).

## The one event that mutates ambient context

Relocation (glitch resolved by moving the guest) **re-binds the Stay's room**,
which changes the ambient {room, section} every subsequent flow reads (D20).
It is the single context-mutating event in the system — modelled as a Stay
transition that emits an Event, not as a field edit scattered across children.

---

These machines are the stable part. Where a node is "state vs sub-state vs
own entity" is left open on purpose (see entities.md open questions) — the
transitions and their triggers are what we commit to now.
