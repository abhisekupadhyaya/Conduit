// src/shell/supervisor/hooks/use-rooms.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Room = {
  id: string; label: string; section_id: string
  section_label: string; created_at: string
}
export function useRooms(sectionId?: string) {
  return useQuery({
    queryKey: ["rooms", sectionId ?? null],
    queryFn: () => api.get<Room[]>(
      `/supervisor/rooms${sectionId ? `?section_id=${sectionId}` : ""}`),
  })
}
export function useCreateRoom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { label: string; section_id: string }) =>
      api.post<Room>("/supervisor/rooms", v),
    onSuccess: () => invalidateBinding(qc, ["rooms", "sections", "stays"]),
  })
}
export function useUpdateRoom() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...b }: {
      id: string; label?: string; section_id?: string
    }) => api.patch<Room>(`/supervisor/rooms/${id}`, b),
    onSuccess: () => invalidateBinding(qc, ["rooms", "sections", "stays"]),
  })
}
