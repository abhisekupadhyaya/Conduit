import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// All guest API access goes through TanStack Query (auth is the only exception).

type ChildStatus = {
  id: string
  title: string
  state: string
  servicer?: string
  revisedEta?: string
}
type Thread = { children: ChildStatus[] }

const keys = {
  thread: ["guest", "thread"] as const,
}

/** Conversation/status — polled (AD7: in-portal, passive, no websockets). */
export function useGuestThread() {
  return useQuery({
    queryKey: keys.thread,
    queryFn: () => api.get<Thread>("/guest/thread"),
    refetchInterval: 4_000,
  })
}

export function useSubmitRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (text: string) =>
      api.post<{ requestId: string }>("/guest/requests", { text }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.thread }),
  })
}

export function useConfirmChild() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (childId: string) =>
      api.post<void>(`/guest/children/${childId}/confirm`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.thread }),
  })
}
