import { Navigate } from "react-router-dom"
import { useAuth } from "@/auth/use-auth"
import { roleHome } from "@/lib/role-routing"

// Public entry: authenticated users go to their portal, others to login.
export function Landing() {
  const { user, isAuthenticated } = useAuth()
  return (
    <Navigate
      to={isAuthenticated && user ? roleHome(user.role) : "/login"}
      replace
    />
  )
}
