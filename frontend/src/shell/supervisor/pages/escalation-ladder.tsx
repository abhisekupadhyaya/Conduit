import { useState } from "react"
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

function LadderFormDialog({ edit }: { edit?: EscalationLadderOut }) {
  const [open, setOpen] = useState(false)
  const create = useCreateEscalationLadder()
  const update = useUpdateEscalationLadder()
  const isEdit = !!edit

  const [propertyId, setPropertyId] = useState(edit?.property_id ?? "")
  const [dutyManagerId, setDutyManagerId] = useState(
    edit?.duty_manager_account_id ?? "",
  )
  const [nCycleBound, setNCycleBound] = useState(
    String(edit?.n_cycle_bound ?? ""),
  )

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
          property_id: propertyId.trim(),
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
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit escalation ladder" : "New escalation ladder"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="property_id">property id</Label>
            <Input
              id="property_id"
              disabled={isEdit}
              value={propertyId}
              onChange={(e) => setPropertyId(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="duty_manager_account_id">
              duty manager account id
            </Label>
            <Input
              id="duty_manager_account_id"
              value={dutyManagerId}
              onChange={(e) => setDutyManagerId(e.target.value)}
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
  const [confirm, setConfirm] = useState<EscalationLadderOut | null>(null)

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
        <DropdownMenuItem asChild>
          <div>
            <LadderFormDialog edit={l} />
          </div>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setConfirm(l)}>
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
                <TableHead>Property</TableHead>
                <TableHead>Duty manager</TableHead>
                <TableHead>Cycle bound</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((l) => (
                <TableRow key={l.id}>
                  <TableCell className="font-mono text-xs">
                    {l.property_id}
                  </TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">
                    {l.duty_manager_account_id}
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
              <div className="font-mono text-xs">{l.property_id}</div>
              <div className="text-muted-foreground text-xs">
                dm {l.duty_manager_account_id} · bound {l.n_cycle_bound}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={l.status} />
              {actions(l)}
            </div>
          </div>
        ))}
      />
      <Confirm
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm?.status === "active"
            ? "Disable escalation ladder?"
            : "Enable escalation ladder?"
        }
        description={confirm?.property_id}
        confirmLabel={confirm?.status === "active" ? "Disable" : "Enable"}
        onConfirm={() => {
          if (confirm) toggle(confirm)
          setConfirm(null)
        }}
      />
    </div>
  )
}
