import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api-client"
import { useAuth } from "@/auth/use-auth"

export function useUpdateSelf() {
  const { refreshUser } = useAuth()
  return useMutation({
    mutationFn: (b: { display_name?: string; current_password?: string;
      new_password?: string }) => api.patch("/auth/me", b),
    onSuccess: () => refreshUser(),
  })
}
