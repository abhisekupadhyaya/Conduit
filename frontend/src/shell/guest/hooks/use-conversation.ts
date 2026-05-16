// src/shell/guest/hooks/use-conversation.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// Mirrors use-sections.ts: array query key, TanStack mutation, invalidation
// by the same key. Resolution C — the submit mutation's pending state IS the
// instant-ack; no polling, no extra endpoint (the no-dispatch journey).

export type Child = {
  child_id: string
  text: string
  issue_code?: string | null
  terminal: "answered" | "logged"
  answer?: string | null
  closure_prompt?: boolean | null
  state?: string | null
}
export type Req = { request_id: string; children: Child[] }

export function useConversation() {
  return useQuery({
    queryKey: ["conversation"],
    queryFn: () => api.get<Req[]>("/guest/requests"),
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
