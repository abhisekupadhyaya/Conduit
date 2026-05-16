import type { ReactNode } from "react"

// The only thing that differs per portal is the nav. Everything else
// (sidebar chrome, header, theme/user menu) is the shared shell.
export type NavItem = {
  title: string
  url: string
  icon?: ReactNode
  items?: { title: string; url: string }[]
}

export type NavConfig = {
  /** Product brand, constant across portals. */
  brand: string
  /** Which portal this is — shown in the brand block + header. */
  roleLabel: string
  /** Sidebar group heading. */
  groupLabel: string
  items: NavItem[]
}
