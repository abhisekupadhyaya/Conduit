import { SettingsView } from "@/components/common/settings-view"
import { ManageAccounts } from "@/shell/supervisor/pages/manage-accounts"

export function SupervisorSettings() {
  return (
    <SettingsView team={<ManageAccounts role="supervisor" label="Supervisor" />} />
  )
}
