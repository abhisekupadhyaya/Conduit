import { HomeIcon } from "lucide-react"
import type { NavConfig } from "@/components/layout/nav-config"

// Servicer portal — one calm home. The restraint is the design (spec §10).
export const servicerNav: NavConfig = {
  brand: "Conduit",
  roleLabel: "Servicer",
  groupLabel: "Work",
  items: [{ title: "Home", url: "/servicer", icon: <HomeIcon /> }],
}
