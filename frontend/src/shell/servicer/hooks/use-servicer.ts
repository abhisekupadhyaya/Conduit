import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

type Task = {
  workOrderId: string
  title: string
  kind: "pushed" | "claimable"
  slaSecondsLeft: number
}
type Queue = { tasks: Task[] }

const keys = {
  queue: ["servicer", "queue"] as const,
}

/** Task queue — polled; accept-window/SLA countdowns are live (D23/AD7). */
export function useTaskQueue() {
  return useQuery({
    queryKey: keys.queue,
    queryFn: () => api.get<Queue>("/servicer/queue"),
    refetchInterval: 5_000,
  })
}

export function useAcceptWorkOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (woId: string) =>
      api.post<void>(`/servicer/work-orders/${woId}/accept`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.queue }),
  })
}

export function useEscalateWorkOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (woId: string) =>
      api.post<void>(`/servicer/work-orders/${woId}/escalate`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.queue }),
  })
}
