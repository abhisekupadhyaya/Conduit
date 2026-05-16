// src/shell/supervisor/hooks/use-staff.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

export type StaffClass = string
export type Presence = "working" | "on_break" | "off"
export type ProfileStatus = "active" | "disabled"

export type Profile = {
  staff_class: StaffClass
  presence: string
  status: string
}

// Mirrors backend StaffOut (supervisor/schemas/staff.py). `on_shift` and
// `effective_available` are REAL Task-5b derivations returned even for
// un-profiled accounts — top-level siblings of profile/skills.
export type StaffRow = {
  account_id: string
  display_name: string
  profile: Profile | null
  skills: string[]
  on_shift: boolean
  effective_available: boolean
}

export type CreateProfile = {
  account_id: string
  staff_class: string
}

export type PatchProfile = {
  account_id: string
  staff_class?: string
  status?: string
}

export type SetSkills = {
  account_id: string
  skills: string[]
}

export function useStaff() {
  return useQuery({
    queryKey: ["staff"],
    queryFn: () => api.get<StaffRow[]>("/supervisor/staff"),
  })
}

export function useCreateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: CreateProfile) => {
      const { account_id, ...body } = v
      return api.post<StaffRow>(`/supervisor/staff/${account_id}/profile`, body)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["staff"] }),
  })
}

export function usePatchProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: PatchProfile) => {
      const { account_id, ...patch } = v
      return api.patch<StaffRow>(`/supervisor/staff/${account_id}/profile`, patch)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["staff"] }),
  })
}

export function useSetSkills() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: SetSkills) => {
      const { account_id, skills } = v
      return api.put<StaffRow>(`/supervisor/staff/${account_id}/skills`, {
        skills,
      })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["staff"] }),
  })
}
