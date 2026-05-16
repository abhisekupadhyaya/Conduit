import { Navigate, useLocation } from "react-router-dom"
import { useAuth, type Role } from "@/auth/use-auth"
import { roleHome } from "@/lib/role-routing"

/**
 * Route guard. Unauthenticated → /login. Authenticated but wrong portal →
 * bounced to their own role home. RBAC is out of scope (D-note) — this is a
 * coarse 3-role gate, not a permission engine.
 */
export function RequireAuth({
  allow,
  children,
}: {
  allow: Role[]
  children: React.ReactNode
}) {
  const { user, isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isAuthenticated || !user)
    return <Navigate to="/login" replace state={{ from: location }} />

  if (!allow.includes(user.role))
    return <Navigate to={roleHome(user.role)} replace />

  return <>{children}</>
}
