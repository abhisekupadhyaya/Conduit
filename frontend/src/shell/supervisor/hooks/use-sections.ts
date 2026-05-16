// src/shell/supervisor/hooks/use-sections.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Section = {
  id: string; label: string; room_count: number; created_at: string
}
export function useSections() {
  return useQuery({
    queryKey: ["sections"],
    queryFn: () => api.get<Section[]>("/supervisor/sections"),
  })
}
export function useCreateSection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (label: string) =>
      api.post<Section>("/supervisor/sections", { label }),
    onSuccess: () => invalidateBinding(qc, ["sections", "rooms", "stays"]),
  })
}
export function useRenameSection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; label: string }) =>
      api.patch<Section>(`/supervisor/sections/${v.id}`, { label: v.label }),
    onSuccess: () => invalidateBinding(qc, ["sections", "rooms", "stays"]),
  })
}
