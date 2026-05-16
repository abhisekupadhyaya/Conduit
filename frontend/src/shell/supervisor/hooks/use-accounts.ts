import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api-client"

export type Account = {
  id: string; role: string; username: string
  display_name: string; status: string; created_at: string
}

export function useAccounts(role?: string, status?: string) {
  const qs = new URLSearchParams()
  if (role) qs.set("role", role)
  if (status) qs.set("status", status)
  return useQuery({
    queryKey: ["accounts", role ?? null, status ?? null],
    queryFn: () => api.get<Account[]>(`/supervisor/accounts?${qs}`),
  })
}

export function useCreateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (b: { role: string; username: string;
      display_name: string; password: string }) =>
      api.post<Account>("/supervisor/accounts", b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  })
}

export function useUpdateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...b }: { id: string; display_name?: string;
      status?: string; password?: string }) =>
      api.patch<Account>(`/supervisor/accounts/${id}`, b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  })
}
