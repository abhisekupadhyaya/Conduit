import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import type { Presence } from "@/components/common/presence-control"

// Bound to the real ServicerHomeOut (backend/conduit/servicer/schemas/home.py).
// `skills` is a top-level sibling of `profile` (also mirrored inside profile);
// the page uses the top-level one. `profile` is null for an un-profiled
// account. `presence_locked` is the authoritative server gate (off-shift).
export type ServicerProfile = {
  // On the wire the schema aliases this field `class`.
  class: string
  skills: string[]
  status: string
}

export type ServicerShift = {
  shift_start: string
  shift_end: string
  section_label: string | null
  role: string
}

export type ServicerHome = {
  profile: ServicerProfile | null
  skills: string[]
  current_shift: ServicerShift | null
  next_shift: ServicerShift | null
  presence: Presence
  presence_locked: boolean
  effective_available: boolean
}

const keys = {
  home: ["servicer", "home"] as const,
}

/** Composed derived read; polled (AD7) — matches the old hook's 5s cadence. */
export function useServicerHome() {
  return useQuery({
    queryKey: keys.home,
    queryFn: () => api.get<ServicerHome>("/servicer/home"),
    refetchInterval: 5_000,
  })
}

/**
 * The servicer's one write (D39). `PUT /servicer/presence {presence}` returns
 * the updated ServicerHomeOut. Off-shift → 409 (the server lock); the caller
 * catches `ApiError.status === 409` for a calm toast — `ApiError` propagates.
 */
export function usePresence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (presence: Presence) =>
      api.put<ServicerHome>("/servicer/presence", { presence }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.home }),
  })
}
