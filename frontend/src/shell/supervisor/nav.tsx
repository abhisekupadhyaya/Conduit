import {
  ActivityIcon,
  InboxIcon,
  SearchIcon,
  Settings2Icon,
  BookOpenIcon,
  UsersIcon,
  BarChart3Icon,
} from "lucide-react"
import type { NavConfig } from "@/components/layout/nav-config"

// Supervisor portal — the widest surface, all 8 pages in v1 (D33).
export const supervisorNav: NavConfig = {
  brand: "Conduit",
  roleLabel: "Supervisor",
  groupLabel: "Operations",
  items: [
    { title: "Awareness Stream", url: "/supervisor", icon: <ActivityIcon /> },
    {
      title: "Decision Queue",
      url: "/supervisor/decisions",
      icon: <InboxIcon />,
    },
    { title: "Task Explorer", url: "/supervisor/tasks", icon: <SearchIcon /> },
    {
      title: "Setup",
      url: "/supervisor/setup",
      icon: <Settings2Icon />,
      items: [
        { title: "Sections & Rosters", url: "/supervisor/setup/rosters" },
        { title: "Issue Codes", url: "/supervisor/setup/issue-codes" },
        { title: "SLA Presets", url: "/supervisor/setup/sla" },
        { title: "Escalation Ladder", url: "/supervisor/setup/escalation" },
      ],
    },
    {
      title: "Knowledge Base",
      url: "/supervisor/kb",
      icon: <BookOpenIcon />,
    },
    {
      title: "Guest Provisioning",
      url: "/supervisor/provisioning",
      icon: <UsersIcon />,
    },
    { title: "Servicers", url: "/supervisor/accounts/servicers", icon: <UsersIcon /> },
    { title: "Guests", url: "/supervisor/accounts/guests", icon: <UsersIcon /> },
    { title: "Settings", url: "/supervisor/settings", icon: <Settings2Icon /> },
    {
      title: "Analytics",
      url: "/supervisor/analytics",
      icon: <BarChart3Icon />,
    },
  ],
}
