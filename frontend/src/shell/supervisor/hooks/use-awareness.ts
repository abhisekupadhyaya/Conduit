// src/shell/supervisor/hooks/use-awareness.ts
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// Mirrors backend supervisor/schemas/awareness.py (E6 — Spec §8/§9). ONE
// composite event-derived projection: incoming · task delegation · servicer
// recent work · open glitches. WATCH-ONLY (D2 — separate route from the
// decision queue); polled (AD7), never mutated here.

// issue_label / servicer_name are the human-readable fields the UI renders
// (backend embeds them — the StayOut.room_label idiom). Raw ids stay for
// stable keys/future deep-links but are not shown.
export type IncomingItem = {
  escalation_id: string
  child_id: string
  issue_label: string | null
  trigger: string // triage_flag | stall | servicer_raised
  at: string
}

export type DelegationItem = {
  work_order_id: string
  child_id: string
  issue_label: string | null
  servicer_id: string | null
  servicer_name: string | null
  at: string
}

export type RecentWorkItem = {
  work_order_id: string
  child_id: string
  issue_label: string | null
  servicer_id: string | null
  servicer_name: string | null
  at: string
}

export type OpenGlitchItem = {
  glitch_id: string
  child_id: string
  issue_label: string | null
  opened_from: string // problem_report | dispute
  at: string
}

export type AwarenessOut = {
  incoming: IncomingItem[]
  task_delegation: DelegationItem[]
  servicer_recent_work: RecentWorkItem[]
  open_glitches: OpenGlitchItem[]
}

const keys = {
  awareness: ["supervisor", "awareness"] as const,
}

/** The composite awareness projection — polled (AD7), watch-only (D2). */
export function useAwareness() {
  return useQuery({
    queryKey: keys.awareness,
    queryFn: () => api.get<AwarenessOut>("/supervisor/awareness"),
    refetchInterval: 5_000,
  })
}
