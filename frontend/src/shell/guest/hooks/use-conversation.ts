// src/shell/guest/hooks/use-conversation.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// Mirrors use-sections.ts: array query key, TanStack mutation, invalidation
// by the same key. Resolution C — the submit mutation's pending state IS the
// instant-ack; no polling, no extra endpoint (the no-dispatch journey).
//
// F2 (Spec §10 Guest) ADDS the dispatch surface alongside the existing
// no-dispatch journey — strictly additive, the back-compat reads/mutations
// below are unchanged. The merged guest array-key idiom (use-guest.ts /
// use-servicer.ts: a `const keys = {...} as const` object + per-hook
// `refetchInterval` for AD7-polled surfaces + `invalidateQueries` by the same
// key) is matched EXACTLY — the dispatch key is the spec-mandated
// ['guest','requests'].

export type Child = {
  child_id: string
  text: string
  issue_code?: string | null
  terminal: "answered" | "logged"
  answer?: string | null
  closure_prompt?: boolean | null
  state?: string | null
  // D36 split-echo: server-decided per-child label + triage outcome
  // (auto|clarify|flag|no_dispatch). Additive output only.
  issue_label?: string | null
  outcome?: string
}
// D36 split-echo: server-decided (≥2 children ⇒ echo, 1 ⇒ instant-ack).
export type Req = { request_id: string; children: Child[]; split: boolean }

// E1 backend shape (conduit/guest/schemas/requests.py — DispatchCardOut). The
// curated guest-facing card: NAME never id (D17), server-provided revised_eta
// (the F1 countdown's deadline truth — AD5), and an open-Glitch badge.
export type DispatchCard = {
  child_id: string
  state: string
  issue_label?: string | null
  assigned_servicer_name?: string | null
  revised_eta?: string | null
  glitch: boolean
  // Spec §8 / §4 — additive output (DispatchCardOut.relocated_to). Set on a
  // live sibling card once the stay re-binds to the new room (the towel
  // follows the guest to 511). Calm reassurance, never an alert.
  relocated_to?: string | null
}

// Merged array-key idiom (use-guest.ts / use-servicer.ts). The dispatch cards
// key is the spec-mandated ['guest','requests'] — centralized invalidation
// below targets exactly this key.
const keys = {
  requests: ["guest", "requests"] as const,
}

// No-dispatch conversation surface (grounded answers, smalltalk, honest
// deferrals D25). Distinct path — GET /guest/requests is won by the dispatch
// router, so the no-dispatch journey lives at /guest/conversation. Polled at
// the same cadence as dispatch cards so async outcomes (a deferral, or a
// reservation-mutation result after supervisor action) appear without a
// manual refresh.
export function useConversation() {
  return useQuery({
    queryKey: ["conversation"],
    queryFn: () => api.get<Req[]>("/guest/conversation"),
    refetchInterval: 4_000,
  })
}

export function useSubmitRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (text: string) =>
      api.post<Req>("/guest/requests", { text }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversation"] }),
  })
}

export function useConfirmChild() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; helpful: boolean }) =>
      api.post<Child>(`/guest/children/${v.id}/confirm`, {
        helpful: v.helpful,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversation"] }),
  })
}

// --- F2: dispatch status cards + the three guarded guest actions ---------

/**
 * Polled dispatch status cards (Spec §8 / §10 Guest, AD7: in-portal, passive,
 * no websockets). GET /guest/requests serves list[DispatchCardOut] (the E1
 * dispatch router wins this path match). Matches the merged guest poll cadence
 * (use-guest.ts: refetchInterval 4_000) and the ['guest','requests'] key.
 */
export function useDispatchCards() {
  return useQuery({
    queryKey: keys.requests,
    queryFn: () => api.get<DispatchCard[]>("/guest/requests"),
    refetchInterval: 4_000,
  })
}

/** Guest confirms dispatched work → child Closed (D8). */
export function useConfirmDispatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (childId: string) =>
      api.post<{ child_id: string; state: string }>(
        `/guest/requests/${childId}/confirm`,
        {},
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.requests }),
  })
}

/** Guest says it is NOT resolved → child Reopened (D8). */
export function useReopenDispatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (childId: string) =>
      api.post<{ child_id: string; state: string }>(
        `/guest/requests/${childId}/reopen`,
        {},
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.requests }),
  })
}

/** Guest cancels — allowed until Closed; the committed servicer is notified
 *  via the C4 child_cancelled event (D37). */
export function useCancelDispatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (childId: string) =>
      api.post<{ child_id: string; state: string }>(
        `/guest/requests/${childId}/cancel`,
        {},
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.requests }),
  })
}
