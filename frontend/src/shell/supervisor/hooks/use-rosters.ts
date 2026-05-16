// src/shell/supervisor/hooks/use-rosters.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

// Mirrors backend RosterOut/AssignmentOut + Create*/Patch* (supervisor/
// schemas/roster.py). Clones the use-issue-codes / use-staff house shape:
// array query keys, mutations via the shared `api` client, centralized
// queryClient.invalidateQueries. Assignments hang off a nested key
// (['rosters', rosterId, 'assignments']) and mutations invalidate by the
// appropriate key prefix.

export type Roster = {
  id: string
  shift_start: string
  shift_end: string
  status: string
}

export type CreateRoster = {
  shift_start: string
  shift_end: string
}

export type PatchRoster = {
  shift_start?: string
  shift_end?: string
  status?: string
}

export type Assignment = {
  id: string
  roster_id: string
  account_id: string
  section_id: string | null
  assignment: string
  status: string
}

export type CreateAssignment = {
  account_id: string
  section_id?: string | null
  assignment: string
}

export type PatchAssignment = {
  section_id?: string | null
  assignment?: string
  status?: string
}

export function useRosters() {
  return useQuery({
    queryKey: ["rosters"],
    queryFn: () => api.get<Roster[]>("/supervisor/rosters"),
  })
}

export function useCreateRoster() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: CreateRoster) =>
      api.post<Roster>("/supervisor/rosters", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rosters"] }),
  })
}

export function usePatchRoster() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string } & PatchRoster) => {
      const { id, ...patch } = v
      return api.patch<Roster>(`/supervisor/rosters/${id}`, patch)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rosters"] }),
  })
}

export function useAssignments(rosterId: string | null) {
  return useQuery({
    queryKey: ["rosters", rosterId, "assignments"],
    queryFn: () =>
      api.get<Assignment[]>(`/supervisor/rosters/${rosterId}/assignments`),
    enabled: !!rosterId,
  })
}

export function useCreateAssignment(rosterId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: CreateAssignment) =>
      api.post<Assignment>(
        `/supervisor/rosters/${rosterId}/assignments`,
        v,
      ),
    onSuccess: () =>
      qc.invalidateQueries({
        queryKey: ["rosters", rosterId, "assignments"],
      }),
  })
}

export function usePatchAssignment(rosterId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string } & PatchAssignment) => {
      const { id, ...patch } = v
      return api.patch<Assignment>(
        `/supervisor/rosters/${rosterId}/assignments/${id}`,
        patch,
      )
    },
    onSuccess: () =>
      qc.invalidateQueries({
        queryKey: ["rosters", rosterId, "assignments"],
      }),
  })
}
