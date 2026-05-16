import { useMemo, useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { MoreHorizontalIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { StatusBadge } from "@/components/common/status-badge"
import { Confirm } from "@/components/common/confirm"
import {
  RosterWindowFormDialog,
} from "@/components/common/roster-window-form-dialog"
import {
  AssignmentEditor,
  type ServicerOption,
  type AssignmentEdit,
} from "@/components/common/assignment-editor"
import type { ComboOption } from "@/components/common/combobox-field"
import { useStaff } from "@/shell/supervisor/hooks/use-staff"
import { useSections } from "@/shell/supervisor/hooks/use-sections"
import {
  useRosters, useCreateRoster, usePatchRoster,
  useAssignments, useCreateAssignment, usePatchAssignment,
  type Roster, type Assignment,
} from "@/shell/supervisor/hooks/use-rosters"

function fmt(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  })
}

// Master-detail body: rendered only when a window is selected so the
// assignments query keys to that roster id (['rosters', id, 'assignments']).
function AssignmentsPanel({
  roster, servicers, sections,
}: {
  roster: Roster
  servicers: ServicerOption[]
  sections: ComboOption[]
}) {
  const q = useAssignments(roster.id)
  const createAssignment = useCreateAssignment(roster.id)
  const patchAssignment = usePatchAssignment(roster.id)
  const [confirm, setConfirm] = useState<Assignment | null>(null)
  const [editRow, setEditRow] = useState<Assignment | null>(null)

  const state = q.isLoading ? "loading" : q.isError ? "error"
    : (q.data?.length ?? 0) === 0 ? "empty" : "ready"

  async function toggle(a: Assignment) {
    const next = a.status === "active" ? "disabled" : "active"
    try {
      await patchAssignment.mutateAsync({ id: a.id, status: next })
      toast.success(`Assignment ${next}`)
    } catch {
      toast.error("Update failed")
    }
  }

  const nameOf = (id: string) =>
    servicers.find((s) => s.value === id)?.label ?? id
  const sectionOf = (id: string | null) =>
    id ? (sections.find((s) => s.value === id)?.label ?? id) : "—"

  const actions = (a: Assignment) => (
    <DropdownMenu key={a.id}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 sm:size-9">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setEditRow(a)}>
          Edit
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setConfirm(a)}>
          {a.status === "active" ? "Disable" : "Enable"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  const editValue: AssignmentEdit | undefined = editRow
    ? {
        id: editRow.id,
        account_id: editRow.account_id,
        section_id: editRow.section_id,
        assignment: editRow.assignment,
      }
    : undefined

  return (
    <div className="space-y-4">
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No assignments yet"
        emptyHint="Add the first servicer to this window."
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Servicer</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Section</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data?.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">
                    {nameOf(a.account_id)}
                  </TableCell>
                  <TableCell className="capitalize text-muted-foreground">
                    {a.assignment}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {sectionOf(a.section_id)}
                  </TableCell>
                  <TableCell><StatusBadge status={a.status} /></TableCell>
                  <TableCell className="text-right">{actions(a)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={q.data?.map((a) => (
          <div key={a.id}
               className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <div className="text-sm font-medium">
                {nameOf(a.account_id)}
              </div>
              <div className="text-muted-foreground text-xs capitalize">
                {a.assignment} · {sectionOf(a.section_id)}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={a.status} />{actions(a)}
            </div>
          </div>
        ))}
      />

      <div className="rounded-lg border p-3">
        <div className="mb-2 text-sm font-medium">
          {editRow ? "Edit assignment" : "Add assignment"}
        </div>
        <AssignmentEditor
          key={editRow?.id ?? "new"}
          servicers={servicers}
          sections={sections}
          edit={editValue}
          onCreate={(p) => createAssignment.mutateAsync(p)}
          onPatch={async (p) => {
            const r = await patchAssignment.mutateAsync(p)
            setEditRow(null)
            return r
          }}
        />
        {editRow && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-2"
            onClick={() => setEditRow(null)}
          >
            Cancel edit
          </Button>
        )}
      </div>

      <Confirm
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm?.status === "active"
            ? "Disable assignment?" : "Enable assignment?"
        }
        description={confirm ? nameOf(confirm.account_id) : undefined}
        confirmLabel={confirm?.status === "active" ? "Disable" : "Enable"}
        onConfirm={() => { if (confirm) toggle(confirm); setConfirm(null) }}
      />
    </div>
  )
}

export function RostersPage() {
  const q = useRosters()
  const createRoster = useCreateRoster()
  const patchRoster = usePatchRoster()
  const staff = useStaff()
  const sectionsQ = useSections()
  const [selected, setSelected] = useState<Roster | null>(null)

  const state = q.isLoading ? "loading" : q.isError ? "error"
    : (q.data?.length ?? 0) === 0 ? "empty" : "ready"

  // Servicers for the assignment-editor picker: reuse useStaff() (role=
  // servicer accounts incl. profile so the editor can detect engineering
  // for the D18 rule). Only profiled rows carry a staff_class.
  const servicers: ServicerOption[] = useMemo(
    () =>
      (staff.data ?? [])
        .filter((s) => s.profile)
        .map((s) => ({
          value: s.account_id,
          label: s.display_name,
          staff_class: s.profile!.staff_class,
        })),
    [staff.data],
  )

  const sections: ComboOption[] = useMemo(
    () =>
      (sectionsQ.data ?? []).map((s) => ({
        value: s.id,
        label: s.label,
      })),
    [sectionsQ.data],
  )

  const actions = (r: Roster) => (
    <DropdownMenu key={r.id}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-11 sm:size-9"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild onSelect={(e) => e.preventDefault()}>
          <div onClick={(e) => e.stopPropagation()}>
            <RosterWindowFormDialog
              edit={{
                id: r.id,
                shift_start: r.shift_start,
                shift_end: r.shift_end,
              }}
              onPatch={(v) => patchRoster.mutateAsync(v)}
            />
          </div>
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={(e) => e.stopPropagation()}
          onSelect={() => setSelected(r)}
        >
          Manage assignments
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div>
      <PageHeader
        title="Rosters"
        description={`${q.data?.length ?? 0} window(s)`}
        actions={
          <RosterWindowFormDialog
            onCreate={(v) => createRoster.mutateAsync(v)}
          />
        }
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No roster windows yet"
        emptyHint="Create the first shift window to staff it."
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Shift start</TableHead>
                <TableHead>Shift end</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data?.map((r) => (
                <TableRow
                  key={r.id}
                  className="cursor-pointer"
                  onClick={() => setSelected(r)}
                >
                  <TableCell className="font-medium tabular-nums">
                    {fmt(r.shift_start)}
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {fmt(r.shift_end)}
                  </TableCell>
                  <TableCell><StatusBadge status={r.status} /></TableCell>
                  <TableCell className="text-right">{actions(r)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={q.data?.map((r) => (
          <div
            key={r.id}
            className="flex cursor-pointer items-center justify-between rounded-lg border p-3"
            onClick={() => setSelected(r)}
          >
            <div className="space-y-0.5">
              <div className="text-sm font-medium tabular-nums">
                {fmt(r.shift_start)}
              </div>
              <div className="text-muted-foreground text-xs tabular-nums">
                → {fmt(r.shift_end)}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={r.status} />{actions(r)}
            </div>
          </div>
        ))}
      />

      <Sheet
        open={selected !== null}
        onOpenChange={(o) => !o && setSelected(null)}
      >
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Roster window</SheetTitle>
            {selected && (
              <SheetDescription className="tabular-nums">
                {fmt(selected.shift_start)} → {fmt(selected.shift_end)}
              </SheetDescription>
            )}
          </SheetHeader>
          {selected && (
            <div className="px-4 pb-4">
              <AssignmentsPanel
                roster={selected}
                servicers={servicers}
                sections={sections}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
