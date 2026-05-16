import { Routes, Route, Navigate } from "react-router-dom"
import { RequireAuth } from "@/auth/require-auth"
import { LoginPage } from "@/auth/login-page"
import { Landing } from "@/public/landing"
import { AppShell } from "@/components/layout/app-shell"
import { guestNav } from "@/shell/guest/nav"
import { servicerNav } from "@/shell/servicer/nav"
import { supervisorNav } from "@/shell/supervisor/nav"
import { GuestConversation } from "@/shell/guest"
import { ServicerQueue } from "@/shell/servicer"
import { SupervisorHome } from "@/shell/supervisor"

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
      </Route>

      <Route
        path="/servicer"
        element={
          <RequireAuth allow={["servicer"]}>
            <AppShell nav={servicerNav} />
          </RequireAuth>
        }
      >
        <Route index element={<ServicerQueue />} />
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
        {/* Remaining supervisor pages render here as they are built. */}
        <Route path="*" element={<SupervisorHome />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
