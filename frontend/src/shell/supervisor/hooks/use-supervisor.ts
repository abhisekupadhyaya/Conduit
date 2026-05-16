import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

type DecisionItem = {
  escalationId: string
  trigger: "triage_flag" | "stall" | "servicer_raised"
  recommendation: string
  supervisorSlaSecondsLeft: number
}
type DecisionQueue = { items: DecisionItem[] }
type SetupConfig = Record<string, unknown>

const keys = {
  decisions: ["supervisor", "decisions"] as const,
  setup: ["supervisor", "setup"] as const,
}

/** Decision queue — polled; supervisor-SLA countdown is live (D9/AD7). */
export function useDecisionQueue() {
  return useQuery({
    queryKey: keys.decisions,
    queryFn: () => api.get<DecisionQueue>("/supervisor/decisions"),
    refetchInterval: 5_000,
  })
}

export function useResolveDecision() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { escalationId: string; action: string }) =>
      api.post<void>(`/supervisor/decisions/${vars.escalationId}`, {
        action: vars.action,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.decisions }),
  })
}

/** Setup/config — read-only here; config edits are separate mutations. */
export function useSetupConfig() {
  return useQuery({
    queryKey: keys.setup,
    queryFn: () => api.get<SetupConfig>("/supervisor/setup"),
  })
}
