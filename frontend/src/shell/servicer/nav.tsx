import { ListChecksIcon } from "lucide-react"
import type { NavConfig } from "@/components/layout/nav-config"

// Servicer portal — lean operational (sitemap 2.x).
export const servicerNav: NavConfig = {
  brand: "Conduit",
  roleLabel: "Servicer",
  groupLabel: "Work",
  items: [
    { title: "Task Queue", url: "/servicer", icon: <ListChecksIcon /> },
  ],
}
