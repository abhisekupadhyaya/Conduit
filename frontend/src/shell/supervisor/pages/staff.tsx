import { useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { MoreHorizontalIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { StatusBadge } from "@/components/common/status-badge"
import { Confirm } from "@/components/common/confirm"
import { SkillsField } from "@/components/common/skills-field"
import { StaffPresenceCell } from "@/components/common/staff-presence-cell"
import {
  StaffProfileFormDialog,
} from "@/components/common/staff-profile-form-dialog"
import type { Presence } from "@/components/common/presence-control"
import {
  useStaff, useCreateProfile, usePatchProfile, useSetSkills,
  type StaffRow,
} from "@/shell/supervisor/hooks/use-staff"

// Un-profiled accounts have no presence; the cell's `presence: Presence`
// prop is non-nullable, so render a muted "—" rather than fabricate one
// (mirrors how issue-codes handles absent sub-data). on_shift /
// effective_available are REAL backend derivations — always pass them
// truthfully, never a proxy.
function PresenceColumn({ row }: { row: StaffRow }) {
  if (!row.profile) {
    return <span className="text-muted-foreground">—</span>
  }
  return (
    <StaffPresenceCell
      presence={row.profile.presence as Presence}
      onShift={row.on_shift}
      effectiveAvailable={row.effective_available}
    />
  )
}

function SkillChips({ skills }: { skills: string[] }) {
  if (skills.length === 0) {
    return <span className="text-muted-foreground">—</span>
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {skills.map((s) => (
        <Badge key={s} variant="outline">{s}</Badge>
      ))}
    </div>
  )
}

export function StaffPage() {
  const q = useStaff()
  const createProfile = useCreateProfile()
  const patchProfile = usePatchProfile()
  const setSkills = useSetSkills()
  const [confirm, setConfirm] = useState<StaffRow | null>(null)
  const [editFor, setEditFor] = useState<StaffRow | null>(null)
  const [skillsFor, setSkillsFor] = useState<StaffRow | null>(null)
  const [draftSkills, setDraftSkills] = useState<string[]>([])
  const [savingSkills, setSavingSkills] = useState(false)

  const state = q.isLoading ? "loading" : q.isError ? "error"
    : (q.data?.length ?? 0) === 0 ? "empty" : "ready"

  function openSkills(r: StaffRow) {
    setSkillsFor(r)
    setDraftSkills(r.skills)
  }

  async function saveSkills() {
    if (!skillsFor) return
    setSavingSkills(true)
    try {
      await setSkills.mutateAsync({
        account_id: skillsFor.account_id, skills: draftSkills,
      })
      toast.success("Skills updated")
      setSkillsFor(null)
    } catch {
      toast.error("Could not save skills")
    } finally {
      setSavingSkills(false)
    }
  }

  async function toggle(r: StaffRow) {
    if (!r.profile) return
    const next = r.profile.status === "active" ? "disabled" : "active"
    try {
      await patchProfile.mutateAsync({ account_id: r.account_id, status: next })
      toast.success(`${r.display_name} ${next}`)
    } catch {
      toast.error("Update failed")
    }
  }

  const actions = (r: StaffRow) => {
    // Un-profiled rows have no menu actions — the only affordance is the
    // inline Class-column "Create profile". Mirror issue-codes, which never
    // renders an empty menu (its rows always carry >=1 action), by omitting
    // the ⋯ trigger entirely when there is nothing to show.
    if (!r.profile) return null
    return (
      <DropdownMenu key={r.account_id}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="size-11 sm:size-9">
            <MoreHorizontalIcon className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setEditFor(r)}>
            Edit profile
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => openSkills(r)}>
            Edit skills
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setConfirm(r)}>
            {r.profile.status === "active" ? "Disable" : "Enable"}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    )
  }

  function classCell(r: StaffRow) {
    if (r.profile) {
      return (
        <span className="capitalize">
          {r.profile.staff_class.replace(/_/g, " ")}
        </span>
      )
    }
    return (
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">Not profiled</span>
        <StaffProfileFormDialog
          accountId={r.account_id}
          displayName={r.display_name}
          onCreate={(v) => createProfile.mutateAsync(v)}
        />
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Staff"
        description={`${q.data?.length ?? 0} servicer(s)`}
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No servicers yet"
        emptyHint="Provision servicer accounts to staff the operation."
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Class</TableHead>
                <TableHead>Skills</TableHead>
                <TableHead>Presence</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data?.map((r) => (
                <TableRow key={r.account_id}>
                  <TableCell className="font-medium">
                    {r.display_name}
                  </TableCell>
                  <TableCell>{classCell(r)}</TableCell>
                  <TableCell><SkillChips skills={r.skills} /></TableCell>
                  <TableCell><PresenceColumn row={r} /></TableCell>
                  <TableCell>
                    {r.profile
                      ? <StatusBadge status={r.profile.status} />
                      : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="text-right">{actions(r)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={q.data?.map((r) => (
          <div key={r.account_id}
               className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-1">
              <div className="text-sm font-medium">{r.display_name}</div>
              <div className="text-muted-foreground text-xs">
                {classCell(r)}
              </div>
              <PresenceColumn row={r} />
              <SkillChips skills={r.skills} />
            </div>
            <div className="flex items-center gap-2">
              {r.profile
                ? <StatusBadge status={r.profile.status} />
                : <span className="text-muted-foreground">—</span>}
              {actions(r)}
            </div>
          </div>
        ))}
      />
      {editFor?.profile && (
        <StaffProfileFormDialog
          key={editFor.account_id}
          edit={{
            account_id: editFor.account_id,
            display_name: editFor.display_name,
            staff_class: editFor.profile.staff_class,
            status: editFor.profile.status,
          }}
          onPatch={(v) => patchProfile.mutateAsync(v)}
          open={editFor !== null}
          onOpenChange={(o) => { if (!o) setEditFor(null) }}
        />
      )}
      <Confirm
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm?.profile?.status === "active"
            ? "Disable staff profile?" : "Enable staff profile?"
        }
        description={confirm?.display_name}
        confirmLabel={
          confirm?.profile?.status === "active" ? "Disable" : "Enable"
        }
        onConfirm={() => { if (confirm) toggle(confirm); setConfirm(null) }}
      />
      <Dialog
        open={skillsFor !== null}
        onOpenChange={(o) => { if (!o) { setSkillsFor(null); setDraftSkills([]) } }}
      >
        <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              Edit skills{skillsFor ? ` — ${skillsFor.display_name}` : ""}
            </DialogTitle>
          </DialogHeader>
          <SkillsField value={draftSkills} onChange={setDraftSkills} />
          <DialogFooter>
            <Button onClick={saveSkills} disabled={savingSkills}>
              {savingSkills ? "Saving…" : "Save skills"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
