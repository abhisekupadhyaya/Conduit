import type { Role } from "@/auth/use-auth"

// Where each role lands after login. The duty manager backstop (D21) shares
// the supervisor surface in v1.
export function roleHome(role: Role): string {
  switch (role) {
    case "supervisor":
    case "duty_manager":
      return "/supervisor"
    case "servicer":
      return "/servicer"
    case "guest":
    default:
      return "/guest"
  }
}
