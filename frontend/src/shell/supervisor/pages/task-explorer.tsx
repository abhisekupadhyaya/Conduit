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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { MoreHorizontalIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { Confirm } from "@/components/common/confirm"
import { ComboboxField } from "@/components/common/combobox-field"
import { useAccounts } from "@/shell/supervisor/hooks/use-accounts"
import {
  useChildren,
  useTakeover,
  useReassignChild,
  useCancelChild,
  type ChildExplorerOut,
} from "@/shell/supervisor/hooks/use-children"

// Task Explorer / Override — the D6 god-mode (Spec §8 "Supervisor
// children/override"). Global by role: ANY child in ANY state + its
// WorkOrder / Escalation / Glitch, searchable by child id / state.
// takeover / reassign / cancel are the dedicated D6 ACTION endpoints.

function TargetDialog({
  open,
  onOpenChange,
  title,
  required,
  onSubmit,
  pending,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  required: boolean
  onSubmit: (targetServicerId: string) => void
  pending: boolean
}) {
  const [val, setVal] = useState("")
  const accounts = useAccounts("servicer")
  const servicerOptions = [
    // Optional (takeover): the empty sentinel = the acting supervisor
    // becomes the assignee. Reassign is required → no sentinel.
    ...(required
      ? []
      : [{ value: "", label: "Me (I take it over)" }]),
    ...(accounts.data ?? []).map((a) => ({
      value: a.id,
      label: `${a.username} (${a.role})`,
    })),
  ]
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setVal("")
        onOpenChange(o)
      }}
    >
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="target_servicer_id">
            {required ? "Servicer" : "Servicer (optional)"}
          </Label>
          <ComboboxField
            options={servicerOptions}
            value={val}
            onChange={setVal}
            placeholder={
              required ? "Select servicer" : "Select servicer or take it over"
            }
            emptyText="No servicer accounts"
          />
        </div>
        <DialogFooter>
          <Button
            className="w-full"
            disabled={pending || (required && !val.trim())}
            onClick={() => onSubmit(val.trim())}
          >
            {pending ? "Working…" : "Confirm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function TaskExplorerPage() {
  const [childId, setChildId] = useState("")
  const [stateFilter, setStateFilter] = useState("")
  // Applied filters drive the polled query (server is global by role).
  const [applied, setApplied] = useState<{
    child_id?: string
    state?: string
  }>({})

  const q = useChildren(applied)
  const takeover = useTakeover()
  const reassign = useReassignChild()
  const cancel = useCancelChild()

  const [takeoverFor, setTakeoverFor] = useState<ChildExplorerOut | null>(null)
  const [reassignFor, setReassignFor] = useState<ChildExplorerOut | null>(null)
  const [cancelFor, setCancelFor] = useState<ChildExplorerOut | null>(null)

  const rows = q.data ?? []
  const state = q.isLoading
    ? "loading"
    : q.isError
      ? "error"
      : rows.length === 0
        ? "empty"
        : "ready"

  function applyFilters() {
    setApplied({
      ...(childId.trim() ? { child_id: childId.trim() } : {}),
      ...(stateFilter.trim() ? { state: stateFilter.trim() } : {}),
    })
  }

  async function doTakeover(target: string) {
    if (!takeoverFor) return
    try {
      await takeover.mutateAsync({
        childId: takeoverFor.child_id,
        ...(target ? { target_servicer_id: target } : {}),
      })
      toast.success("Taken over")
      setTakeoverFor(null)
    } catch (e: any) {
      toast.error(e?.status === 409 ? "Not actionable" : "Takeover failed")
    }
  }

  async function doReassign(target: string) {
    if (!reassignFor) return
    try {
      await reassign.mutateAsync({
        childId: reassignFor.child_id,
        target_servicer_id: target,
      })
      toast.success("Reassigned")
      setReassignFor(null)
    } catch (e: any) {
      toast.error(e?.status === 409 ? "Not actionable" : "Reassign failed")
    }
  }

  async function doCancel() {
    if (!cancelFor) return
    try {
      await cancel.mutateAsync({ childId: cancelFor.child_id })
      toast.success("Cancelled")
    } catch (e: any) {
      toast.error(
        e?.status === 409 ? "Already terminal" : "Cancel failed",
      )
    } finally {
      setCancelFor(null)
    }
  }

  const actions = (c: ChildExplorerOut) => (
    <DropdownMenu key={c.child_id}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 sm:size-9">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTakeoverFor(c)}>
          Takeover
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setReassignFor(c)}>
          Reassign
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setCancelFor(c)}>
          Cancel
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div>
      <PageHeader
        title="Task Explorer"
        description="D6 god-mode — any child in any state, global by role."
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No matching children"
        emptyHint="Adjust the child id / state filter."
        toolbar={
          <>
            <Input
              value={childId}
              onChange={(e) => setChildId(e.target.value)}
              placeholder="child id"
              className="h-9 sm:max-w-[16rem]"
            />
            <Input
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              placeholder="state (e.g. open)"
              className="h-9 sm:max-w-[12rem]"
            />
            <Button size="sm" onClick={applyFilters}>
              Search
            </Button>
          </>
        }
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Request</TableHead>
                <TableHead>State</TableHead>
                <TableHead>Work order</TableHead>
                <TableHead>Escalation</TableHead>
                <TableHead>Glitch</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => (
                <TableRow key={c.child_id}>
                  <TableCell>
                    {c.issue_label ?? "Uncategorized"}
                  </TableCell>
                  <TableCell className="font-medium">{c.state}</TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {c.work_order
                      ? `${c.work_order.state}${
                          c.work_order.servicer_name
                            ? ` · ${c.work_order.servicer_name}`
                            : ""
                        }`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {c.escalation
                      ? `${c.escalation.trigger} · ${c.escalation.state}`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {c.glitch ? c.glitch.state : "—"}
                  </TableCell>
                  <TableCell className="text-right">{actions(c)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={rows.map((c) => (
          <div
            key={c.child_id}
            className="flex items-center justify-between rounded-lg border p-3"
          >
            <div className="space-y-0.5">
              <div className="text-sm font-medium">
                {c.issue_label ?? "Uncategorized"}
              </div>
              <div className="text-muted-foreground text-xs">{c.state}</div>
              <div className="text-muted-foreground text-xs">
                {c.work_order ? `wo: ${c.work_order.state}` : "no wo"}
                {c.escalation ? ` · esc: ${c.escalation.state}` : ""}
                {c.glitch ? ` · glitch: ${c.glitch.state}` : ""}
              </div>
            </div>
            {actions(c)}
          </div>
        ))}
      />

      <TargetDialog
        open={takeoverFor !== null}
        onOpenChange={(o) => !o && setTakeoverFor(null)}
        title="Takeover child"
        required={false}
        pending={takeover.isPending}
        onSubmit={doTakeover}
      />
      <TargetDialog
        open={reassignFor !== null}
        onOpenChange={(o) => !o && setReassignFor(null)}
        title="Reassign child"
        required
        pending={reassign.isPending}
        onSubmit={doReassign}
      />
      <Confirm
        open={cancelFor !== null}
        onOpenChange={(o) => !o && setCancelFor(null)}
        title="Cancel request?"
        description={cancelFor?.issue_label ?? "Uncategorized"}
        confirmLabel="Cancel child"
        onConfirm={doCancel}
      />
    </div>
  )
}
