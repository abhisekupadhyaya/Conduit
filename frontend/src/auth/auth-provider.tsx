import { useCallback, useMemo, useState } from "react"
import { AuthContext, type User } from "@/auth/use-auth"

const STORAGE_KEY = "conduit-auth"

function readStored(): User | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as User) : null
  } catch {
    return null
  }
}

/**
 * Scaffolding auth. App-managed session (AD8) — no Cognito.
 * The real implementation will call the backend; for now this fakes a
 * supervisor-provisioned login so the shells are reachable.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(readStored)

  const login = useCallback(async (username: string, _password: string) => {
    void _password
    // Stub: derive a role from the username prefix until the API exists.
    const role = username.startsWith("sup")
      ? "supervisor"
      : username.startsWith("svc")
        ? "servicer"
        : "guest"
    const next: User = {
      id: crypto.randomUUID(),
      name: username,
      email: `${username}@conduit.local`,
      role,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setUser(next)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, isAuthenticated: user !== null, login, logout }),
    [user, login, logout]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
