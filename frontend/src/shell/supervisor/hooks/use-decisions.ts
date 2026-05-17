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

export type DecisionOut = {
  escalation_id: string
  child_id: string
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
