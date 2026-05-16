// src/shell/supervisor/hooks/use-issue-codes.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

export type FulfilmentMode = "dispatch" | "no_dispatch"
export type RoutingModel = "section_pooled" | "skill_matched" | "none"
export type IntentKind = "service" | "problem_report"
export type Status = "active" | "disabled"

export type IssueCode = {
  id: string
  code: string
  label: string
  department: string
  fulfilment_mode: FulfilmentMode
  routing_model: RoutingModel
  intent_kind: IntentKind
  is_reservation_mutation: boolean
  status: Status
  created_at: string
}

export type CreateIssueCode = {
  code: string
  label: string
  department: string
  fulfilment_mode: FulfilmentMode
  routing_model: RoutingModel
  intent_kind: IntentKind
}

export type PatchIssueCode = {
  label?: string
  department?: string
  fulfilment_mode?: FulfilmentMode
  routing_model?: RoutingModel
  intent_kind?: IntentKind
  status?: Status
}

export function useIssueCodes() {
  return useQuery({
    queryKey: ["issue-codes"],
    queryFn: () => api.get<IssueCode[]>("/supervisor/issue-codes"),
  })
}

export function useCreateIssueCode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: CreateIssueCode) =>
      api.post<IssueCode>("/supervisor/issue-codes", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issue-codes"] }),
  })
}

export function useUpdateIssueCode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string } & PatchIssueCode) => {
      const { id, ...patch } = v
      return api.patch<IssueCode>(`/supervisor/issue-codes/${id}`, patch)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issue-codes"] }),
  })
}
