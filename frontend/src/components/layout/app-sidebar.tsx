import * as React from "react"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from "@/components/ui/sidebar"
import { AppBrand } from "@/components/layout/app-brand"
import { NavMain } from "@/components/layout/nav-main"
import { NavUser } from "@/components/layout/nav-user"
import type { NavConfig } from "@/components/layout/nav-config"

// One sidebar for every portal. Only `nav` changes per portal.
export function AppSidebar({
  nav,
  ...props
}: { nav: NavConfig } & React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <AppBrand brand={nav.brand} roleLabel={nav.roleLabel} />
      </SidebarHeader>
      <SidebarContent>
        <NavMain groupLabel={nav.groupLabel} items={nav.items} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
