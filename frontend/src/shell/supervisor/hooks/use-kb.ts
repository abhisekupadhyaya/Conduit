// src/shell/supervisor/hooks/use-kb.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

export type KBStatus = "active" | "disabled"

export type KBEntry = {
  id: string
  topic: string
  content: string
  status: KBStatus
  created_at: string
}

export type CreateKBEntry = { topic: string; content: string }

export type PatchKBEntry = {
  topic?: string
  content?: string
  status?: KBStatus
}

export function useKB() {
  return useQuery({
    queryKey: ["kb"],
    queryFn: () => api.get<KBEntry[]>("/supervisor/kb"),
  })
}

export function useCreateKBEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: CreateKBEntry) =>
      api.post<KBEntry>("/supervisor/kb", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kb"] }),
  })
}

export function useUpdateKBEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string } & PatchKBEntry) => {
      const { id, ...patch } = v
      return api.patch<KBEntry>(`/supervisor/kb/${id}`, patch)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kb"] }),
  })
}
