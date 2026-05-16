// src/shell/supervisor/hooks/use-stays.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { invalidateBinding } from "./invalidate-binding"

export type Stay = {
  id: string; guest_account_id: string; guest_display_name: string
  room_id: string; room_label: string; section_id: string
  section_label: string; check_in: string; check_out: string
  status: "active" | "ended"; created_at: string
}
export function useStays(status?: string, guestId?: string) {
  const qs = new URLSearchParams()
  if (status) qs.set("status", status)
  if (guestId) qs.set("guest_id", guestId)
  const s = qs.toString()
  return useQuery({
    queryKey: ["stays", status ?? null, guestId ?? null],
    queryFn: () => api.get<Stay[]>(`/supervisor/stays${s ? `?${s}` : ""}`),
  })
}
export function useCreateStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { guest_account_id: string; room_id: string
      check_in: string; check_out: string }) =>
      api.post<Stay>("/supervisor/stays", v),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}
export function useRelocateStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; new_room_id: string }) =>
      api.post<Stay>(`/supervisor/stays/${v.id}/relocate`,
        { new_room_id: v.new_room_id }),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}
export function useCheckoutStay() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Stay>(`/supervisor/stays/${id}/checkout`, {}),
    onSuccess: () => invalidateBinding(qc, ["stays"]),
  })
}
