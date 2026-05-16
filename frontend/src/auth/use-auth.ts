import { createContext, useContext } from "react"

// The three v1 portals + the non-time-boxed backstop actor (D2/D3/D21).
export type Role = "guest" | "servicer" | "supervisor" | "duty_manager"

export type User = {
  id: string
  name: string
  email: string
  role: Role
}

export type AuthState = {
  user: User | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthState | undefined>(undefined)

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (ctx === undefined)
    throw new Error("useAuth must be used within an AuthProvider")
  return ctx
}
