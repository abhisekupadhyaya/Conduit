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
// F4 (Spec §10 Supervisor): Decision Queue (act) + Awareness Stream
// (watch) are DISTINCT routes (D2); Task Explorer is the D6 god-mode;
// SLA/ladder Setup on the merged issue-code-form-dialog CONFIG idiom.
import { DecisionsPage } from "@/shell/supervisor/pages/decisions"
import { AwarenessPage } from "@/shell/supervisor/pages/awareness"
import { TaskExplorerPage } from "@/shell/supervisor/pages/task-explorer"
import { SlaPresetsPage } from "@/shell/supervisor/pages/sla-presets"
import { EscalationLadderPage } from "@/shell/supervisor/pages/escalation-ladder"

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
        {/* F4: the index IS the Awareness Stream — watch-only, D2. The
            old SupervisorHome placeholder is retained as the catch-all
            below so no prior surface 404s. */}
        <Route index element={<AwarenessPage />} />
        <Route path="settings" element={<SupervisorSettings />} />
        <Route path="accounts/servicers" element={<ManageServicers />} />
        <Route path="accounts/guests" element={<ManageGuests />} />
        <Route path="setup/sections" element={<SectionsPage />} />
        <Route path="setup/issue-codes" element={<IssueCodesPage />} />
        <Route path="setup/staff" element={<StaffPage />} />
        <Route path="setup/rosters" element={<RostersPage />} />
        <Route path="knowledge-base" element={<KnowledgeBasePage />} />
        <Route path="provisioning" element={<ProvisioningPage />} />
        {/* F4 additive routes — Decisions (act) is DISTINCT from the
            index Awareness (watch) per D2; Task Explorer is D6 god-mode;
            SLA/ladder Setup on the CONFIG idiom. */}
        <Route path="decisions" element={<DecisionsPage />} />
        <Route path="tasks" element={<TaskExplorerPage />} />
        <Route path="setup/sla" element={<SlaPresetsPage />} />
        <Route path="setup/escalation" element={<EscalationLadderPage />} />
        {/* Remaining supervisor pages render here as they are built. */}
        <Route path="*" element={<SupervisorHome />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
