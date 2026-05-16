import { useCallback, useEffect, useMemo, useState } from "react"
import { api, setOnUnauthorized } from "@/lib/api-client"
import { AuthContext, type User } from "@/auth/use-auth"

type Me = { id: string; role: User["role"]; username: string; display_name: string }
const toUser = (m: Me): User =>
  ({ id: m.id, role: m.role, username: m.username, name: m.display_name })

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    try {
      setUser(toUser(await api.get<Me>("/auth/me")))
    } catch {
      setUser(null)
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const m = await api.post<Me>("/auth/login", { username, password })
    setUser(toUser(m))
  }, [])

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout", {}) } finally { setUser(null) }
  }, [])

  useEffect(() => {
    setOnUnauthorized(() => setUser(null))
    refreshUser().finally(() => setLoading(false))
  }, [refreshUser])

  const value = useMemo(
    () => ({ user, isAuthenticated: user !== null, loading,
             login, logout, refreshUser }),
    [user, loading, login, logout, refreshUser])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
