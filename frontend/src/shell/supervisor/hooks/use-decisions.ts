// src/shell/supervisor/hooks/use-decisions.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// Mirrors backend supervisor/schemas/decisions.py (E3 — Spec §8 "Supervisor
// decisions" / §7.4). The queue is the D9 time-boxed checkpoint surface;
// `supervisor_sla_deadline` is the server-truth countdown target (AD5),
// `non_time_boxed` flags a D21 duty-manager hard escalation.

export type RecommendationOut = {
  action: string // ck_rec_action: reassign | relocate | extend_sla | broadcast | approve | deny
  rationale_text: string
  // Per-action `rec_*` detail, curated by action (D9):
  //   reassign  -> { target_account_id }
  //   relocate  -> { target_room_id }
  //   extend_sla-> { extend_seconds }
  //   broadcast/approve/deny -> {}
  detail: Record<string, unknown>
}

// Spec §8 / §4 (decision: API): for `action === 'relocate'` the server
// populates `detail` with the room context (no schema-class change). This is
// an ADDITIVE narrowing of `RecommendationOut.detail` — existing callers that
// read `detail` as `Record<string, unknown>` are unaffected.
export type RelocateRoom = {
  id: string
  label: string
}
export type RelocateDetail = {
  current_room?: RelocateRoom | null
  recommended_room?: RelocateRoom | null
  eligible_rooms?: RelocateRoom[]
  // The manual Glitch recovery surfaced for the comp note (D19), if present.
  recovery_owed?: string | number | null
  recovery_cost?: string | number | null
}

/** Narrow a relocate recommendation's `detail` to the typed room context.
 *  Defensive: tolerates partial/absent fields (additive, server-populated). */
export function asRelocateDetail(
  detail: Record<string, unknown>,
): RelocateDetail {
  const room = (v: unknown): RelocateRoom | null => {
    if (v && typeof v === "object") {
      const o = v as Record<string, unknown>
      if (o.id != null)
        return { id: String(o.id), label: String(o.label ?? o.id) }
    }
    return null
  }
  const eligible = Array.isArray(detail.eligible_rooms)
    ? (detail.eligible_rooms as unknown[])
        .map(room)
        .filter((r): r is RelocateRoom => r !== null)
    : []
  return {
    current_room: room(detail.current_room),
    recommended_room: room(detail.recommended_room),
    eligible_rooms: eligible,
    recovery_owed:
      detail.recovery_owed as string | number | null | undefined ?? null,
    recovery_cost:
      detail.recovery_cost as string | number | null | undefined ?? null,
  }
}

export type DecisionOut = {
  escalation_id: string
  child_id: string
  issue_label: string | null
  trigger: string // triage_flag | stall | servicer_raised
  state: string
  cycle_count: number
  supervisor_sla_deadline: string | null
  non_time_boxed: boolean
  recommendation: RecommendationOut | null
}

// approve → run the STORED rec verbatim (silence ≡ approve is structural,
// D2/D3); edit/override → supervisor-supplied typed action + params, sent
// as `payload = { action, ...params }` (services/decisions.py).
export type ResolveAction = "approve" | "edit" | "override"
export type ResolveOut = {
  escalation_id: string
  state: string
  resolved_by_account_id: string | null
}

const keys = {
  decisions: ["supervisor", "decisions"] as const,
}

/** Decision queue — polled (AD7); the supervisor-SLA countdown is live (D9). */
export function useDecisions(status?: string) {
  return useQuery({
    queryKey: status ? [...keys.decisions, status] : keys.decisions,
    queryFn: () =>
      api.get<DecisionOut[]>(
        `/supervisor/decisions${status ? `?status=${status}` : ""}`,
      ),
    refetchInterval: 5_000,
  })
}

/** THE single human resolve path (Spec §7.4) — approve | edit | override. */
export function useResolveDecision() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: {
      escalationId: string
      action: ResolveAction
      payload?: Record<string, unknown>
    }) =>
      api.post<ResolveOut>(`/supervisor/decisions/${v.escalationId}/resolve`, {
        action: v.action,
        ...(v.payload ? { payload: v.payload } : {}),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.decisions }),
  })
}
