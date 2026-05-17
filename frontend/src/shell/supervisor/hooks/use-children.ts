// src/shell/supervisor/hooks/use-children.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// Mirrors backend supervisor/schemas/override.py (E4 — Spec §8 "Supervisor
// children/override", D6 god-mode). The explorer GET is global by role
// (the supervisor sees everything); takeover/reassign/cancel are dedicated
// ACTION endpoints. Polled (AD7) since it is a live read.

export type WorkOrderRef = {
  assigned_servicer_id: string | null
  accountable_owner_id: string | null
  state: string
}

export type EscalationRef = {
  escalation_id: string
  trigger: string
  state: string
}

export type GlitchRef = {
  glitch_id: string
  state: string
}

export type ChildExplorerOut = {
  child_id: string
  state: string
  work_order: WorkOrderRef | null
  escalation: EscalationRef | null
  glitch: GlitchRef | null
}

export type OverrideOut = {
  child_id: string
  child_state: string | null
  assigned_servicer_id: string | null
  accountable_owner_id: string | null
}

const keys = {
  children: ["supervisor", "children"] as const,
}

/** Global task explorer — polled (AD7); optional child_id / state filter. */
export function useChildren(filters?: { child_id?: string; state?: string }) {
  const qs = new URLSearchParams()
  if (filters?.child_id) qs.set("child_id", filters.child_id)
  if (filters?.state) qs.set("state", filters.state)
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  return useQuery({
    queryKey: [...keys.children, filters?.child_id ?? "", filters?.state ?? ""],
    queryFn: () =>
      api.get<ChildExplorerOut[]>(`/supervisor/children${suffix}`),
    refetchInterval: 5_000,
  })
}

/** D6 takeover — absent target → acting supervisor; present → named servicer. */
export function useTakeover() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { childId: string; target_servicer_id?: string }) =>
      api.post<OverrideOut>(`/supervisor/children/${v.childId}/takeover`, {
        ...(v.target_servicer_id
          ? { target_servicer_id: v.target_servicer_id }
          : {}),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.children }),
  })
}

/** D6 reassign — explicit hand-to-target (target_servicer_id required). */
export function useReassignChild() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { childId: string; target_servicer_id: string }) =>
      api.post<OverrideOut>(`/supervisor/children/${v.childId}/reassign`, {
        target_servicer_id: v.target_servicer_id,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.children }),
  })
}

/** D6 cancel — supervisor interrupt via the C4 single writer (empty body). */
export function useCancelChild() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { childId: string }) =>
      api.post<OverrideOut>(`/supervisor/children/${v.childId}/cancel`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.children }),
  })
}
