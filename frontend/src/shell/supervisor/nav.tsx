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
// F4 (Spec §10): the Awareness Stream (index, watch), Decision Queue
// (/decisions, act) — DISTINCT entries per D2 — plus Task Explorer
// (/tasks, D6) and the SLA Presets / Escalation Ladder Setup children
// are now backed by real pages. Entries are additive and unchanged in
// shape; only their destinations are now live (no nav restructuring).
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
        { title: "Sections", url: "/supervisor/setup/sections" },
        { title: "Issue Codes", url: "/supervisor/setup/issue-codes" },
        { title: "Staff", url: "/supervisor/setup/staff" },
        { title: "Rosters", url: "/supervisor/setup/rosters" },
        { title: "SLA Presets", url: "/supervisor/setup/sla" },
        { title: "Escalation Ladder", url: "/supervisor/setup/escalation" },
      ],
    },
    {
      title: "Knowledge Base",
      url: "/supervisor/knowledge-base",
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
