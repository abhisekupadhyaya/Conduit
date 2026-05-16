import { Outlet } from "react-router-dom"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"
import { AppSidebar } from "@/components/layout/app-sidebar"
import type { NavConfig } from "@/components/layout/nav-config"

// The shared portal frame. Every portal renders this; the page renders
// through <Outlet/>. The only per-portal input is `nav`.
export function AppShell({ nav }: { nav: NavConfig }) {
  return (
    <SidebarProvider>
      <AppSidebar nav={nav} />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4" />
          <span className="text-sm font-medium">{nav.roleLabel}</span>
        </header>
        <div className="flex flex-1 flex-col gap-4 p-4">
          <Outlet />
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
