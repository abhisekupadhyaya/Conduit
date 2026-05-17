// src/shell/supervisor/hooks/use-escalation-ladder.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// Mirrors backend supervisor/schemas/setup.py (E5 — Spec §8 "Supervisor
// SLA/ladder CONFIG", D21 escalation ladder + duty manager). CONFIG CRUD,
// disable-not-delete: NO delete handler — "remove" is PATCH
// status='disabled'. The merged issue_codes API idiom VERBATIM.

export type EscalationLadderOut = {
  id: string
  property_id: string
  duty_manager_account_id: string
  n_cycle_bound: number
  status: string
  created_at: string
}

export type EscalationLadderCreate = {
  property_id: string
  duty_manager_account_id: string
  n_cycle_bound: number
}

export type EscalationLadderPatch = {
  duty_manager_account_id?: string
  n_cycle_bound?: number
  status?: string
}

const keys = {
  escalationLadder: ["supervisor", "escalation-ladder"] as const,
}

export function useEscalationLadder(status?: string) {
  return useQuery({
    queryKey: status
      ? [...keys.escalationLadder, status]
      : keys.escalationLadder,
    queryFn: () =>
      api.get<EscalationLadderOut[]>(
        `/supervisor/escalation-ladder${status ? `?status=${status}` : ""}`,
      ),
  })
}

export function useCreateEscalationLadder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: EscalationLadderCreate) =>
      api.post<EscalationLadderOut>("/supervisor/escalation-ladder", v),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: keys.escalationLadder }),
  })
}

export function useUpdateEscalationLadder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string } & EscalationLadderPatch) => {
      const { id, ...patch } = v
      return api.patch<EscalationLadderOut>(
        `/supervisor/escalation-ladder/${id}`,
        patch,
      )
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: keys.escalationLadder }),
  })
}
