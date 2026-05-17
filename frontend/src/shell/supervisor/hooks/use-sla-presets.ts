// src/shell/supervisor/hooks/use-sla-presets.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// Mirrors backend supervisor/schemas/setup.py (E5 — Spec §8 "Supervisor
// SLA/ladder CONFIG", D15). CONFIG CRUD, disable-not-delete: there is NO
// delete handler — "remove" is PATCH status='disabled'. The merged
// issue_codes API idiom VERBATIM.

export type SLAPresetOut = {
  id: string
  property_id: string
  tier: string
  accept_window_seconds: number
  fulfilment_sla_seconds: number
  supervisor_sla_seconds: number
  status: string
  created_at: string
}

// property_id is resolved server-side (single-property v1, AD9) — not part
// of the create body; it remains on SLAPresetOut for display.
export type SLAPresetCreate = {
  tier: string
  accept_window_seconds: number
  fulfilment_sla_seconds: number
  supervisor_sla_seconds: number
}

export type SLAPresetPatch = {
  tier?: string
  accept_window_seconds?: number
  fulfilment_sla_seconds?: number
  supervisor_sla_seconds?: number
  status?: string
}

const keys = {
  slaPresets: ["supervisor", "sla-presets"] as const,
}

export function useSlaPresets(status?: string) {
  return useQuery({
    queryKey: status ? [...keys.slaPresets, status] : keys.slaPresets,
    queryFn: () =>
      api.get<SLAPresetOut[]>(
        `/supervisor/sla-presets${status ? `?status=${status}` : ""}`,
      ),
  })
}

export function useCreateSlaPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: SLAPresetCreate) =>
      api.post<SLAPresetOut>("/supervisor/sla-presets", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.slaPresets }),
  })
}

export function useUpdateSlaPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string } & SLAPresetPatch) => {
      const { id, ...patch } = v
      return api.patch<SLAPresetOut>(`/supervisor/sla-presets/${id}`, patch)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.slaPresets }),
  })
}
