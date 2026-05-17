import { Routes, Route, Navigate } from "react-router-dom"
import { RequireAuth } from "@/auth/require-auth"
import { LoginPage } from "@/auth/login-page"
import { Landing } from "@/public/landing"
import { AppShell } from "@/components/layout/app-shell"
import { guestNav } from "@/shell/guest/nav"
import { servicerNav } from "@/shell/servicer/nav"
import { supervisorNav } from "@/shell/supervisor/nav"
import { GuestConversation } from "@/shell/guest/pages/conversation"
import { ServicerHome } from "@/shell/servicer"
import { SupervisorHome } from "@/shell/supervisor"
import { GuestSettings } from "@/shell/guest/settings"
import { ServicerSettings } from "@/shell/servicer/settings"
import { SupervisorSettings } from "@/shell/supervisor/pages/settings"
import { ManageServicers } from "@/shell/supervisor/pages/manage-servicers"
import { ManageGuests } from "@/shell/supervisor/pages/manage-guests"
import { SectionsPage } from "@/shell/supervisor/pages/sections"
import { IssueCodesPage } from "@/shell/supervisor/pages/issue-codes"
import { StaffPage } from "@/shell/supervisor/pages/staff"
import { RostersPage } from "@/shell/supervisor/pages/rosters"
import { KnowledgeBasePage } from "@/shell/supervisor/pages/knowledge-base"
import { ProvisioningPage } from "@/shell/supervisor/pages/provisioning"

// One SPA, one shared shell, role-routed. Only the nav config differs.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/guest"
        element={
          <RequireAuth allow={["guest"]}>
            <AppShell nav={guestNav} />
          </RequireAuth>
        }
      >
        <Route index element={<GuestConversation />} />
        <Route path="settings" element={<GuestSettings />} />
      </Route>

      <Route
        path="/servicer"
        element={
          <RequireAuth allow={["servicer"]}>
            <AppShell nav={servicerNav} />
          </RequireAuth>
        }
      >
        <Route index element={<ServicerHome />} />
        {/* F3: task-detail is a drill-in Sheet composed into the queue
            index; this additive deep-link route renders the same Task
            Queue screen so a /servicer/tasks/:woId URL resolves. Existing
            servicer routes (index, settings) are untouched. */}
        <Route path="tasks/:woId" element={<ServicerHome />} />
        <Route path="settings" element={<ServicerSettings />} />
      </Route>

      <Route
        path="/supervisor"
        element={
          <RequireAuth allow={["supervisor", "duty_manager"]}>
            <AppShell nav={supervisorNav} />
          </RequireAuth>
        }
      >
        <Route index element={<SupervisorHome />} />
        <Route path="settings" element={<SupervisorSettings />} />
        <Route path="accounts/servicers" element={<ManageServicers />} />
        <Route path="accounts/guests" element={<ManageGuests />} />
        <Route path="setup/sections" element={<SectionsPage />} />
        <Route path="setup/issue-codes" element={<IssueCodesPage />} />
        <Route path="setup/staff" element={<StaffPage />} />
        <Route path="setup/rosters" element={<RostersPage />} />
        <Route path="knowledge-base" element={<KnowledgeBasePage />} />
        <Route path="provisioning" element={<ProvisioningPage />} />
        {/* Remaining supervisor pages render here as they are built. */}
        <Route path="*" element={<SupervisorHome />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
