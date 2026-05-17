import { useEffect, useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { MoreHorizontalIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { StatusBadge } from "@/components/common/status-badge"
import { Confirm } from "@/components/common/confirm"
import { ComboboxField } from "@/components/common/combobox-field"
import { useAccounts } from "@/shell/supervisor/hooks/use-accounts"
import {
  useEscalationLadder,
  useCreateEscalationLadder,
  useUpdateEscalationLadder,
  type EscalationLadderOut,
} from "@/shell/supervisor/hooks/use-escalation-ladder"

// Escalation Ladder — Spec §8 "Supervisor SLA/ladder CONFIG" (D21: the
// duty-manager backstop + cycle bound). Same merged
// `issue-code-form-dialog` CONFIG idiom as SLA presets: create/edit Dialog
// + row dropdown; disable-not-delete via the merged `confirm` (NO delete
// UI). Fields mirror backend setup.EscalationLadderCreate/Patch verbatim.

// `open`/`onOpenChange` make this controllable. Edit-from-row is rendered
// CONTROLLED and OUTSIDE the row DropdownMenu — a Dialog nested in
// DropdownMenuContent unmounts (flickers) when the menu closes. The "New"
// header usage stays uncontrolled (self-triggered).
function LadderFormDialog({
  edit,
  open: openProp,
  onOpenChange,
}: {
  edit?: EscalationLadderOut
  open?: boolean
  onOpenChange?: (o: boolean) => void
}) {
  const controlled = onOpenChange !== undefined
  const [openUncontrolled, setOpenUncontrolled] = useState(false)
  const open = controlled ? !!openProp : openUncontrolled
  const setOpen = controlled ? onOpenChange : setOpenUncontrolled
  const create = useCreateEscalationLadder()
  const update = useUpdateEscalationLadder()
  const isEdit = !!edit

  const [dutyManagerId, setDutyManagerId] = useState(
    edit?.duty_manager_account_id ?? "",
  )
  const [nCycleBound, setNCycleBound] = useState(
    String(edit?.n_cycle_bound ?? ""),
  )
  // D21: the backstop must be a non-time-boxed human — a supervisor or
  // duty_manager account. Picker, not a raw UUID (single-property UX).
  const accounts = useAccounts()
  const dutyManagerOptions = (accounts.data ?? [])
    .filter((a) => a.role === "supervisor" || a.role === "duty_manager")
    .map((a) => ({ value: a.id, label: `${a.username} (${a.role})` }))

  // Stays MOUNTED (open toggled, never conditionally unmounted — an
  // unmounted-while-open Radix Dialog leaks the body pointer-events lock
  // and makes the whole app unclickable). Re-sync fields from `edit` on
  // row change / (re)open instead of remounting.
  useEffect(() => {
    if (!open) return
    setDutyManagerId(edit?.duty_manager_account_id ?? "")
    setNCycleBound(String(edit?.n_cycle_bound ?? ""))
  }, [edit?.id, open])

  async function submit() {
    try {
      if (isEdit) {
        await update.mutateAsync({
          id: edit.id,
          duty_manager_account_id: dutyManagerId.trim(),
          n_cycle_bound: Number(nCycleBound),
        })
        toast.success("Escalation ladder updated")
      } else {
        await create.mutateAsync({
          duty_manager_account_id: dutyManagerId.trim(),
          n_cycle_bound: Number(nCycleBound),
        })
        toast.success("Escalation ladder created")
      }
      setOpen(false)
    } catch (e: any) {
      toast.error(
        e?.status === 409
          ? "An active ladder for this property already exists"
          : e?.status === 422
            ? "Incoherent escalation ladder"
            : "Could not save escalation ladder",
      )
    }
  }

  const pending = create.isPending || update.isPending

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {!controlled && (
        <DialogTrigger asChild>
          {isEdit ? (
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start font-normal"
            >
              Edit
            </Button>
          ) : (
            <Button size="sm">New escalation ladder</Button>
          )}
        </DialogTrigger>
      )}
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit escalation ladder" : "New escalation ladder"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="duty_manager_account_id">duty manager</Label>
            <ComboboxField
              options={dutyManagerOptions}
              value={dutyManagerId || null}
              onChange={setDutyManagerId}
              placeholder="Select duty manager"
              emptyText="No supervisor / duty-manager accounts"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="n_cycle_bound">n cycle bound</Label>
            <Input
              id="n_cycle_bound"
              type="number"
              value={nCycleBound}
              onChange={(e) => setNCycleBound(e.target.value)}
            />
          </div>
          <Button onClick={submit} className="w-full" disabled={pending}>
            {pending
              ? "Saving…"
              : isEdit
                ? "Save changes"
                : "Create escalation ladder"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function EscalationLadderPage() {
  const q = useEscalationLadder()
  const upd = useUpdateEscalationLadder()
  const accounts = useAccounts()
  const nameFor = (id: string) => {
    const a = (accounts.data ?? []).find((x) => x.id === id)
    return a ? `${a.username} (${a.role})` : "—"
  }
  const [confirm, setConfirm] = useState<EscalationLadderOut | null>(null)
  const [editing, setEditing] = useState<EscalationLadderOut | null>(null)

  const rows = q.data ?? []
  const state = q.isLoading
    ? "loading"
    : q.isError
      ? "error"
      : rows.length === 0
        ? "empty"
        : "ready"

  async function toggle(l: EscalationLadderOut) {
    const next = l.status === "active" ? "disabled" : "active"
    try {
      await upd.mutateAsync({ id: l.id, status: next })
      toast.success(`Ladder ${next}`)
    } catch {
      toast.error("Update failed")
    }
  }

  const actions = (l: EscalationLadderOut) => (
    <DropdownMenu key={l.id}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 sm:size-9">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => setEditing(l)}>
          Edit
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setConfirm(l)}>
          {l.status === "active" ? "Disable" : "Enable"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div>
      <PageHeader
        title="Escalation Ladder"
        description={`${rows.length} ladder(s)`}
        actions={<LadderFormDialog />}
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No escalation ladders yet"
        emptyHint="Create the first escalation ladder."
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Duty manager</TableHead>
                <TableHead>Cycle bound</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((l) => (
                <TableRow key={l.id}>
                  <TableCell className="font-medium">
                    {nameFor(l.duty_manager_account_id)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {l.n_cycle_bound}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={l.status} />
                  </TableCell>
                  <TableCell className="text-right">{actions(l)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={rows.map((l) => (
          <div
            key={l.id}
            className="flex items-center justify-between rounded-lg border p-3"
          >
            <div className="space-y-0.5">
              <div className="text-sm font-medium">
                {nameFor(l.duty_manager_account_id)}
              </div>
              <div className="text-muted-foreground text-xs">
                bound {l.n_cycle_bound}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={l.status} />
              {actions(l)}
            </div>
          </div>
        ))}
      />
      <LadderFormDialog
        edit={editing ?? undefined}
        open={editing !== null}
        onOpenChange={(o) => {
          if (!o) setEditing(null)
        }}
      />
      <Confirm
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm?.status === "active"
            ? "Disable escalation ladder?"
            : "Enable escalation ladder?"
        }
        description={
          confirm ? nameFor(confirm.duty_manager_account_id) : undefined
        }
        confirmLabel={confirm?.status === "active" ? "Disable" : "Enable"}
        onConfirm={() => {
          if (confirm) toggle(confirm)
          setConfirm(null)
        }}
      />
    </div>
  )
}
