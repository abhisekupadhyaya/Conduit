import { MessageSquareIcon } from "lucide-react"
import type { NavConfig } from "@/components/layout/nav-config"

// Guest portal is deliberately tiny (D3): the conversation is the
// whole portal. It still uses the shared shell, just with a single nav entry.
export const guestNav: NavConfig = {
  brand: "Conduit",
  roleLabel: "Guest",
  groupLabel: "Stay",
  items: [
    { title: "Conversation", url: "/guest", icon: <MessageSquareIcon /> },
  ],
}
