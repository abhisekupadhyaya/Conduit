// src/shell/servicer/hooks/use-tasks.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// F3 (Spec §10 Servicer) — the polled Task Queue surface + the five guarded
// servicer actions. Mirrors the merged servicer array-key idiom EXACTLY
// (use-servicer.ts: a `const keys = {...} as const` object + per-hook
// `refetchInterval` for AD7-polled surfaces + centralized `invalidateQueries`
// by the same key, all via the shared `api` client). Strictly additive — the
// staffing servicer home reads/mutations in use-servicer.ts are untouched.

// Bound to the real TaskOut (backend/conduit/servicer/schemas/tasks.py):
// the curated servicer-facing card only — no routing model, no owner/assignee
// id, no section id. `kind` partitions the queue: 'pushed' = owned work,
// 'claimable' = in-zone broadcast. The two deadline fields are the
// server-truth targets the F1 countdown ticks against (D23, AD5).
export type Task = {
  work_order_id: string
  child_id: string
  kind: "pushed" | "claimable"
  state: string
  priority_tier: string
  issue_label?: string | null
  accept_window_deadline?: string | null
  fulfilment_sla_deadline?: string | null
}

// Merged array-key idiom (use-servicer.ts). The tasks key is the
// spec-mandated ['servicer','tasks'] — every mutation below invalidates
// exactly this key (centralized invalidation).
const keys = {
  tasks: ["servicer", "tasks"] as const,
}

/**
 * Polled task queue, self-scoped to the caller (AD7: in-portal, passive, no
 * websockets). GET /servicer/tasks → list[TaskOut] (pushed owned + claimable
 * in-zone, with live SLA / accept-window deadlines, D23). Matches the merged
 * servicer poll cadence (use-servicer.ts: refetchInterval 5_000) and the
 * ['servicer','tasks'] key. A read — it never mutates.
 */
export function useTasks() {
  return useQuery({
    queryKey: keys.tasks,
    queryFn: () => api.get<Task[]>("/servicer/tasks"),
    refetchInterval: 5_000,
  })
}

// The action endpoints return a small ack ({work_order_id, state, ...}) — the
// queue is the source of truth, so each mutation just invalidates the tasks
// key and lets the next poll/refetch re-derive the card set (D12/D14/D20/D23).
type ActionAck = {
  work_order_id?: string
  state?: string
  escalation_id?: string
  child_id?: string
}

/** Claim a broadcast (in-zone) task (D12). Not claimable → 409; not in
 *  zone → 403 (ApiError propagates for a calm caller-side toast). */
export function useClaim() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (woId: string) =>
      api.post<ActionAck>(`/servicer/tasks/${woId}/claim`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tasks }),
  })
}

/** Accept → stops the accept-window timer; the fulfilment SLA runs on (D23). */
export function useAccept() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (woId: string) =>
      api.post<ActionAck>(`/servicer/tasks/${woId}/accept`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tasks }),
  })
}

/** Begin work → in_progress. */
export function useStart() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (woId: string) =>
      api.post<ActionAck>(`/servicer/tasks/${woId}/start`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tasks }),
  })
}

/** Complete (optional notes) → the C4 hop drives the child to
 *  done_pending_confirm (D14). */
export function useComplete() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { woId: string; notes?: string }) =>
      api.post<ActionAck>(`/servicer/tasks/${v.woId}/complete`, {
        notes: v.notes ?? null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tasks }),
  })
}

/** D20 servicer-raised mid-lifecycle escalation via the spine → 201. */
export function useRaise() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { woId: string; reason: string }) =>
      api.post<ActionAck>(`/servicer/tasks/${v.woId}/raise`, {
        reason: v.reason,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tasks }),
  })
}
