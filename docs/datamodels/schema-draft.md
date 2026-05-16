# Tentative Detailed Schema — DRAFT, SUBJECT TO CHANGE

> ⚠️ **A sketch to give us a concrete, *complete* picture — not a commitment.**
> Types are *indicative* (Postgres-flavoured). Keys, indexes, enum-vs-table,
> embed-vs-separate, JSONB-vs-columns are all **provisional**. Where this
> resolves an [open question](entities.md#open-modelling-questions) it does so
> *tentatively* and says so. Read as "something like this", never "this".

Now traced against the **full** source corpus: `decisions.md` (D1–D44),
`sitemap.md` (8 supervisor pages + guest/servicer surfaces), the 3 journeys,
the 4 flows. The [decision-coverage matrix](#decision-coverage) at the bottom
shows where every D-number lands.

Conventions: `pk` · `fk→X` · `?` nullable · `enum(...)` indicative ·
`jsonb` where shape is deliberately still soft · *DERIVED* = read-model, not a
stored core table.

---

## IDENTITY

```
property
  id  uuid pk · name text · timezone text · created_at timestamptz

account                                  -- TENTATIVE Q1: unified + role extension
  id uuid pk
  role          enum(guest, servicer, supervisor, duty_manager)   -- D2,D3,D21,D25
  display_name  text                      -- shown to guest, "Maria is on her way" (D17)
  auth_id       text ?                     -- supervisor-provisioned (D3a); guests never self-register
  secret_hash   text ?
  status        enum(active, disabled)     -- persistent, never torn down (D29)
  created_at / updated_at timestamptz

staff_profile                            -- 1:1 optional, role != guest
  account_id   uuid pk fk→account
  staff_class  enum(housekeeping, runner, engineering, room_service, concierge) ?  -- D4
  skills       jsonb                       -- engineering skill-match (D18)
  availability enum(available, on_break, off_shift)   -- on-shift from roster + manual toggle (D39)
  updated_at   timestamptz

room
  id uuid pk · property_id fk→property · label text
  section_id  uuid ? fk→section            -- TENTATIVE Q2: field, not history (D12)

stay
  id uuid pk
  guest_account_id   uuid fk→account
  room_id            uuid fk→room           -- RE-BINDABLE: relocation mutates this (D20/D29)
  check_in / check_out_expected timestamptz
  check_out_actual   timestamptz ?
  reservation        jsonb                  -- rate/billing/late-checkout = D24-mutable facts (D32)
  status             enum(active, ended)    -- a request presupposes an active stay (D29)
  created_at / updated_at timestamptz
```

## CONFIG (supervisor-owned; rows edited at runtime — never migrations)

```
section          id uuid pk · property_id fk · name text                       -- D12,D13

roster                                                                          -- TENTATIVE Q4
  id uuid pk · property_id fk · shift_start/shift_end timestamptz

roster_assignment
  id uuid pk · roster_id fk→roster · account_id fk→account
  section_id  uuid ? fk→section
  assignment  enum(owner, backup, member)   -- positional accountability (D12); engineering uses skills not section (D18)

issue_code                                  -- THE join point (D34)
  id uuid pk · property_id fk · code text · label text
  department          text
  servicer_class      enum(...staff_class) ?            -- null for pure no-dispatch
  fulfilment_mode     enum(dispatch, no_dispatch)       -- D4
  routing_model       enum(section_pooled, skill_matched, none)  -- D12 vs D18 vs no-dispatch
  sla_preset_id       uuid fk→sla_preset                -- D15
  intent_kind         enum(service, problem_report)     -- D43: problem_report ⇒ Glitch at triage
  requires_supervisor bool                              -- reservation/revenue ⇒ always flag (D24/D30)
  is_system_default   bool                              -- ships default catalog, supervisor-tunable (D34)
  active              bool
  created_at / updated_at timestamptz
  -- "uncategorized" is the ABSENCE of a match → clarify→flag (D34), not a row

sla_preset                                  -- P1–P4 named presets (D14/D15)
  id uuid pk · property_id fk
  tier enum(P1,P2,P3,P4)
  accept_window_seconds  int                 -- D23 timer 1
  fulfilment_sla_seconds int                 -- D23 timer 2 / D15
  supervisor_sla_seconds int                 -- D9 time-box

escalation_ladder
  id uuid pk · property_id fk
  steps jsonb                                -- ordered; soft shape; duty-mgr own ladder open (flow 03)
  duty_manager_account_id uuid fk→account    -- non-time-boxed floor (D21)
  max_auto_cycles int                        -- the D21 bound N

kb_entry         id uuid pk · property_id fk · topic text · body text · active bool
                 · updated_by fk→account · created_at/updated_at               -- D26, sitemap 3.6
```

## SPINE (runtime core)

```
request                                     -- raw intake container, ~immutable post-decompose
  id uuid pk · stay_id fk→stay               -- ambient {guest,room,section} derived from stay (D3a)
  raw_text text · channel enum(text)         -- channel-agnostic for later voice (D11)
  split_echoed bool                          -- >1 child ⇒ echo split back (D36); else instant ack (D5)
  created_at timestamptz

child_sub_request                            -- THE UNIT (D35) — routing/SLA/closure all here
  id uuid pk
  request_id      uuid fk→request
  predecessor_id  uuid ? fk→child_sub_request          -- modify = cancel+recreate (D38)
  issue_code_id   uuid ? fk→issue_code                 -- resolved at triage; null while uncategorized
  fulfilment_mode enum(dispatch, no_dispatch) ?
  triage_outcome  enum(auto, clarify, flag, no_dispatch) ?      -- D5
  priority_tier   enum(P1,P2,P3,P4) ?                  -- from sla_preset; INDEPENDENT of triage (D20)
  uncategorized   bool                                 -- no issue_code match → clarify→flag (D34)
  is_problem_report bool                               -- from issue_code.intent_kind ⇒ Glitch (D43)
  state           enum( intake, triaged, clarifying, routing, pushed, broadcast,
                        accepted, in_progress, done_pending_confirm, answered,
                        concierge_queue, closed, reopened, cancelled )          -- soft, big on purpose
  closure_state   enum( none, awaiting_guest_confirm, confirmed,
                        disputed_reopened, lite_closed, cancelled )             -- D8/D37/D44; lite=flow 04
  revised_eta     timestamptz ?                        -- set on stall, shown to guest (D22)
  sla_preset_id   uuid ? fk→sla_preset                 -- snapshot of preset in force
  cancelled_reason text ?
  created_at / updated_at timestamptz · closed_at timestamptz ?

triage_result                                -- TENTATIVE Q3: separate, not embedded
  id uuid pk · child_id fk→child_sub_request
  slots jsonb                                 -- slot completeness (D5); identity/room pre-filled (D3a)
  risk_level enum(none, flag)                 -- deterministic rulebook (D30)
  risk_raised_by_llm bool                     -- LLM may only RAISE, never lower (D5/D30)
  clarify_turns_used int                      -- budget ~1–2 then flag (D5)
  decided_outcome enum(auto, clarify, flag, no_dispatch)
  created_at timestamptz

clarification_turn
  id uuid pk · child_id fk→child_sub_request · turn_no int
  prompt text · guest_reply text ? · created_at timestamptz

work_order                                   -- dispatch children AND human-concierge deferrals
  id uuid pk · child_id fk→child_sub_request  -- 0..1 per child
  kind            enum(dispatch, human_concierge_answer)        -- D25: only no-dispatch "task"
  routing_model   enum(section_pooled, skill_matched)           -- D12 vs D18
  assigned_account_id    uuid ? fk→account    -- current executor (opportunistic, D12)
  accountable_account_id uuid ? fk→account    -- positional OWNER stays accountable (D12)
  dispatch_mode   enum(pushed, broadcast_claim_fallback) ?      -- D12
  priority_tier   enum(P1,P2,P3,P4)           -- engineering priority queue; P1 preempts (D18)
  queue_position  int ?                       -- skill-scarce queue (D18); soft
  state           enum(created, pushed, broadcast, accepted, in_progress, completed, stalled)
  completion_notes text ?                     -- notes-only in v1; evidence/inventory deferred (D16/D28)
  accepted_at / completed_at timestamptz ?
  created_at / updated_at timestamptz

no_dispatch_resolution                       -- flow 04; TENTATIVE Q7: separate vs fields on child
  id uuid pk · child_id fk→child_sub_request
  mode            enum(grounded_answer, human_deferral)         -- D25/D26
  answer_text     text ?
  grounded_on     jsonb                       -- {reservation:bool, kb_entry_ids:[...]} provenance (D26)
  deferred_work_order_id uuid ? fk→work_order -- human_deferral ⇒ concierge queue (D25)
  closure_lite_helpful   bool ?               -- "did this help?" (flow 04 / D8-lite)
  created_at timestamptz
  -- answer↔action seam: a follow-up that mutates reservation is a NEW request → flag path (D24)

timer                                        -- durable obligation (AD5); stall keys off whichever first (D23)
  id uuid pk
  subject_type enum(child_sub_request, work_order, escalation)  -- polymorphic; may become explicit FKs
  subject_id   uuid
  timer_type   enum(accept_window, fulfilment_sla, supervisor_sla, backstop_cycle)  -- D23/D9/D21
  fire_at      timestamptz                    -- DB now() basis
  state        enum(pending, fired, cancelled)
  created_at timestamptz · fired_at timestamptz ?
  -- tentative index (state, fire_at)

escalation                                   -- decision-queue item; the D9 spine
  id uuid pk · child_id fk→child_sub_request · work_order_id uuid ? fk→work_order
  trigger             enum(triage_flag, stall, servicer_raised)    -- the 3 triggers (D20)
  recommendation_kind enum(reassignment, relocation, reservation_mutation, generic)  -- D9/D20/D24
  recommendation_text text                    -- AI always prepares; never a blank ticket (D7/D9)
  recommendation_data jsonb ?                 -- relocation: rooms/upgrade/comp · mutation: avail/policy
  state               enum(open, approved, edited, overridden, auto_proceeded, hard_escalated)
  cycle_no            int default 0           -- D21 bounded auto-cycles → hard_escalated
  resolved_by         uuid ? fk→account · resolved_at timestamptz ?
  created_at / updated_at timestamptz

glitch                                       -- annotation riding child(ren) (D43/D14), no own dispatch
  id uuid pk
  opened_from        enum(problem_report, closure_dispute)        -- D43; D8 dispute = re-assert
  state              enum(open, held_open, auto_closed, manually_closed)  -- D44
  recovery_owed      bool
  recovery_cost_note text ?                   -- MANUAL, only if supervisor comped (D19/D43)
  created_at timestamptz · closed_at timestamptz ?
  -- a servicer-raised escalation on an already-glitched request RIDES this, no new row (D43)

glitch_link        glitch_id fk→glitch · child_id fk→child_sub_request · pk(both)   -- many-to-many

cross_dept_notification                      -- D14: completion unblocks/notifies another dept
  id uuid pk
  source_work_order_id uuid fk→work_order     -- e.g. maintenance clears room
  target_department    text                   -- → housekeeping + front desk
  target_child_id      uuid ? fk→child_sub_request
  reason               text · emitted_at timestamptz
  -- TENTATIVE Q6: explicit table vs purely event-derived; explicit because D14 calls it first-class

event                                        -- APPEND-ONLY spine (no update/delete)
  id uuid pk                                  -- bigserial vs uuid: open
  producer      enum(guest, servicer, supervisor, duty_manager, system)
  actor_account_id uuid ? fk→account
  subject_type  text · subject_id uuid        -- child/work_order/escalation/glitch/stay/...
  type          text                          -- OPEN VOCABULARY — new types additive (incl. stay.relocated)
  payload       jsonb · occurred_at timestamptz
  -- tentative index (subject_type, subject_id, occurred_at)
```

## DERIVED read-models (not stored core tables; read from `event`)

```
guest_status_card   ← events: state + assigned servicer display_name (D17) + revised_eta (D22), per child
awareness_stream    ← events: incoming · task delegation · servicer recent work · glitches (D2/D14; sitemap 3.2)
decision_queue      ← escalation WHERE state=open + supervisor_sla timer + auto-proceed indicator (D9; sitemap 3.3)
analytics           ← events: time-to-ack · SLA adherence by issue_code · dispute rate ·
                       recurring-fault (glitch × issue_code) · auto-route % (D1/D28; sitemap 3.8)
ambient_context     ← active stay → {guest, room, section}; relocation mutates it (D3a/D20/D29) — NOT a table
```

## Relationship summary

```
property 1─* room ─*─1 section        roster 1─* roster_assignment *─1 account
account 1─0..1 staff_profile          account 1─* stay *─1 room
issue_code *─1 sla_preset
request 1─* child_sub_request
child 1─0..1 work_order · 1─0..1 triage_result · 1─0..1 no_dispatch_resolution
child 1─* clarification_turn · 1─* timer · 1─* escalation
child *─* glitch (glitch_link) · child 0..1─ predecessor (self, modify lineage)
work_order 1─* cross_dept_notification
* ─► event   (append-only; awareness/decision/analytics read it, never the reverse)
```

## Firm vs soft (so we know what will move)

**Firmest** (expensive to change — straight from D-series):
- `child_sub_request` as the unit; `request` a thin container (D35).
- `event` append-only as the *only* analytics/awareness source (D1/D28).
- four `timer_type`s; stall = whichever breaches first (D23/D9/D21).
- `work_order.accountable_account_id` ≠ `assigned_account_id` (D12).
- `glitch` separate, many-to-many, rides children (D43/D14).
- `issue_code` as the join point incl. `intent_kind` + `requires_supervisor`
  + `routing_model` + `fulfilment_mode` (D34/D43/D24/D4).
- no-dispatch grounding provenance (`grounded_on`) — anti-hallucination (D26).
- **Priority-integrity invariant:** `child.priority_tier` is derived *only*
  from `issue_code → sla_preset`, **never** from guest-asserted urgency. This
  is what makes the spine immune to priority-inflation / prompt-injection
  (stress-test header; D5). Treat as a hard rule, not a column default.

**Soft** (expect to move in build):
- Every `enum(...)` (several → lookup/CONFIG tables); the `state` mega-enums
  (likely split status + sub-status).
- All `jsonb` (`reservation`, `slots`, `steps`, `recommendation_data`,
  `grounded_on`, `payload`).
- Q1/Q2/Q3/Q6/Q7 tentative resolutions — first to be revisited.
- `cross_dept_notification` as a table vs event-derived (Q6).
- `revised_eta` as a column vs an event payload (Q8).
- `id` strategy, all indexes, all constraints.

## Decision coverage

Every D1–D44 mapped to where it lands in the model (or why it doesn't).

| D | Where it lands |
|---|---|
| D1 | analytics DERIVED; the whole model exists to remove the coordination layer |
| D2 | `account.role=supervisor`; awareness_stream DERIVED (read, no action) |
| D3/D3a | three portals (no table); `account` supervisor-provisioned, ambient session |
| D4 | `issue_code.fulfilment_mode` + `staff_class` |
| D5 | `triage_result` (slots, clarify budget, outcome) |
| D6 | not data — a guarded transition out of every `child.state` (lifecycle) |
| D7/D9 | `escalation.recommendation_*` + `timer(supervisor_sla)` + auto_proceeded |
| D8 | `child.closure_state` (awaiting_guest_confirm / confirmed / disputed) |
| D10 | `escalation.trigger=stall` via `timer` breach |
| D11 | `request.channel` (channel-agnostic for later voice) |
| D12 | `work_order` routing_model=section_pooled, owner≠assignee, dispatch_mode |
| D13 | all CONFIG entities (supervisor setup) |
| D14 | vocabulary; `cross_dept_notification`; glitch first-class |
| D15 | `sla_preset` per issue_code |
| D16/D28 | `work_order.completion_notes` notes-only; analytics-only integrity |
| D17 | `guest_status_card` shows `account.display_name` |
| D18 | `work_order` routing_model=skill_matched, priority_tier, queue_position |
| D19 | `glitch.recovery_cost_note` manual; no automated comp |
| D20 | `escalation.trigger=servicer_raised`; relocation → `stay.room_id` mutate |
| D21 | `escalation_ladder.max_auto_cycles`, `duty_manager`; `timer(backstop_cycle)` |
| D22 | `child.revised_eta` |
| D23 | `timer(accept_window, fulfilment_sla)` |
| D24 | `issue_code.requires_supervisor`; answer↔action seam → flag |
| D25 | `no_dispatch_resolution.mode=human_deferral` → concierge `work_order` |
| D26 | `no_dispatch_resolution.grounded_on` (reservation + kb_entry) |
| D27 | OUT — no dedup/abuse/rate-limit entities (trusted, one req/issue) |
| D29 | `account.status` persistent; `stay` per-stay binding |
| D30 | `triage_result.risk_level` objective; `risk_raised_by_llm` |
| D31 | OUT — no roster/ladder validation entities (trust valid config) |
| D32 | self-contained: `stay.reservation` owned, no PMS entity |
| D33 | all 8 supervisor surfaces map to CONFIG + DERIVED |
| D34 | `issue_code` system-default + customizable; uncategorized path |
| D35 | `child_sub_request` is the unit; independent children |
| D36 | `request.split_echoed` |
| D37 | `child.closure_state=cancelled` anytime until Closed |
| D38 | `child.predecessor_id` (cancel+recreate) |
| D39 | `staff_profile.availability` |
| D40 | OUT — shift handover manual; orphan caught by stall spine |
| D41 | OUT — i18n deferred |
| D42 | DERIVED only — in-portal passive; no notification entity, no out-of-band |
| D43 | `issue_code.intent_kind`, `child.is_problem_report`, `glitch.opened_from` |
| D44 | `glitch.state` auto_closed with underlying; held_open |
| RBAC | OUT — three fixed roles via `account.role`, no permission model |

**Documented gaps (product-level, not modelled — open threads):** AI-degraded
mode, CSAT capture, audit-trail-as-feature. The append-only `event` log is the
natural substrate for the latter two when they're specified; noted, not silently
absent.

**Underspecified in the source (flagged, not invented):**

- **Room Service / IRD workflow** — D4 + domain-reference §3/§6 say it is *not*
  a simple dispatch (kitchen ticket → tray → course timing). The decisions
  never resolve its model; here it is a generic `work_order`. Real gap to
  resolve with the product owner before build, not guessed.
- **Credit/point work-balancing** — domain-reference §2 (checkout ≈1,
  stayover ≈0.5, suite ≈2; Room Attendant Sheet). D14 *explicitly defers*
  this; `staff_profile.availability` is the minimal D39 form only. A future
  routing-detail phase, recorded so it isn't silently lost.
- **P4 Planned / preventive maintenance** — a real domain tier, but Conduit v1
  is reactive (guest-request-driven); PM has no guest and no scheduler entity.
  Out of v1 by the same reasoning as other deferrals.
