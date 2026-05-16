import { ConciergeBellIcon } from "lucide-react"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"

// Static brand block (replaces sidebar-07's team-switcher — Conduit is a
// single product, not multi-tenant).
export function AppBrand({
  brand,
  roleLabel,
}: {
  brand: string
  roleLabel: string
}) {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton size="lg" className="cursor-default">
          <div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
            <ConciergeBellIcon className="size-4" />
          </div>
          <div className="grid flex-1 text-left text-sm leading-tight">
            <span className="truncate font-medium">{brand}</span>
            <span className="text-muted-foreground truncate text-xs">
              {roleLabel}
            </span>
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
