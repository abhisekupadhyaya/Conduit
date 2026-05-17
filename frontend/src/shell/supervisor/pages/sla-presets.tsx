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
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { MoreHorizontalIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { StatusBadge } from "@/components/common/status-badge"
import { Confirm } from "@/components/common/confirm"
import {
  useSlaPresets,
  useCreateSlaPreset,
  useUpdateSlaPreset,
  type SLAPresetOut,
} from "@/shell/supervisor/hooks/use-sla-presets"

// SLA Presets — Spec §8 "Supervisor SLA/ladder CONFIG" (D15). The merged
// `issue-code-form-dialog` CONFIG idiom: a create/edit Dialog + a row
// dropdown; disable-not-delete via the merged `confirm` (NO delete UI —
// "remove" is PATCH status='disabled'). Fields mirror the backend
// setup.SLAPresetCreate/Patch schema verbatim.

// property_id is resolved server-side (single-property v1, AD9) — never an
// operator input, identical to the sections/rosters CONFIG forms. Create
// requires only tier + the durations.
// `open`/`onOpenChange` make this controllable. Edit-from-row is rendered
// CONTROLLED and OUTSIDE the row DropdownMenu — a Dialog nested in
// DropdownMenuContent unmounts (flickers) when the menu closes. The "New"
// header usage stays uncontrolled (self-triggered).
function SlaPresetFormDialog({
  edit,
  open: openProp,
  onOpenChange,
}: {
  edit?: SLAPresetOut
  open?: boolean
  onOpenChange?: (o: boolean) => void
}) {
  const controlled = onOpenChange !== undefined
  const [openUncontrolled, setOpenUncontrolled] = useState(false)
  const open = controlled ? !!openProp : openUncontrolled
  const setOpen = controlled ? onOpenChange : setOpenUncontrolled
  const create = useCreateSlaPreset()
  const update = useUpdateSlaPreset()
  const isEdit = !!edit

  const [tier, setTier] = useState(edit?.tier ?? "")
  const [acceptWindow, setAcceptWindow] = useState(
    String(edit?.accept_window_seconds ?? ""),
  )
  const [fulfilmentSla, setFulfilmentSla] = useState(
    String(edit?.fulfilment_sla_seconds ?? ""),
  )
  const [supervisorSla, setSupervisorSla] = useState(
    String(edit?.supervisor_sla_seconds ?? ""),
  )

  // The dialog stays MOUNTED (open is toggled, never conditionally
  // unmounted — unmounting a Radix Dialog while open leaks the body
  // pointer-events/scroll lock and makes the whole app unclickable).
  // So fields are re-synced from `edit` when the edited row changes or
  // the dialog (re)opens, instead of relying on remount.
  useEffect(() => {
    if (!open) return
    setTier(edit?.tier ?? "")
    setAcceptWindow(String(edit?.accept_window_seconds ?? ""))
    setFulfilmentSla(String(edit?.fulfilment_sla_seconds ?? ""))
    setSupervisorSla(String(edit?.supervisor_sla_seconds ?? ""))
  }, [edit?.id, open])

  async function submit() {
    try {
      if (isEdit) {
        await update.mutateAsync({
          id: edit.id,
          tier: tier.trim(),
          accept_window_seconds: Number(acceptWindow),
          fulfilment_sla_seconds: Number(fulfilmentSla),
          supervisor_sla_seconds: Number(supervisorSla),
        })
        toast.success("SLA preset updated")
      } else {
        await create.mutateAsync({
          tier: tier.trim(),
          accept_window_seconds: Number(acceptWindow),
          fulfilment_sla_seconds: Number(fulfilmentSla),
          supervisor_sla_seconds: Number(supervisorSla),
        })
        toast.success("SLA preset created")
      }
      setOpen(false)
    } catch (e: any) {
      toast.error(
        e?.status === 409
          ? "An active preset for this tier already exists"
          : e?.status === 422
            ? "Incoherent SLA preset"
            : "Could not save SLA preset",
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
            <Button size="sm">New SLA preset</Button>
          )}
        </DialogTrigger>
      )}
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit SLA preset" : "New SLA preset"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="tier">tier</Label>
            <Select value={tier} onValueChange={setTier}>
              <SelectTrigger id="tier" className="w-full">
                <SelectValue placeholder="Select tier" />
              </SelectTrigger>
              <SelectContent>
                {(["P1", "P2", "P3", "P4"] as const).map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="accept_window_seconds">
              accept window seconds
            </Label>
            <Input
              id="accept_window_seconds"
              type="number"
              value={acceptWindow}
              onChange={(e) => setAcceptWindow(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fulfilment_sla_seconds">
              fulfilment sla seconds
            </Label>
            <Input
              id="fulfilment_sla_seconds"
              type="number"
              value={fulfilmentSla}
              onChange={(e) => setFulfilmentSla(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="supervisor_sla_seconds">
              supervisor sla seconds
            </Label>
            <Input
              id="supervisor_sla_seconds"
              type="number"
              value={supervisorSla}
              onChange={(e) => setSupervisorSla(e.target.value)}
            />
          </div>
          <Button onClick={submit} className="w-full" disabled={pending}>
            {pending
              ? "Saving…"
              : isEdit
                ? "Save changes"
                : "Create SLA preset"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function SlaPresetsPage() {
  const q = useSlaPresets()
  const upd = useUpdateSlaPreset()
  const [confirm, setConfirm] = useState<SLAPresetOut | null>(null)
  const [editing, setEditing] = useState<SLAPresetOut | null>(null)

  const rows = q.data ?? []
  const state = q.isLoading
    ? "loading"
    : q.isError
      ? "error"
      : rows.length === 0
        ? "empty"
        : "ready"

  async function toggle(p: SLAPresetOut) {
    const next = p.status === "active" ? "disabled" : "active"
    try {
      await upd.mutateAsync({ id: p.id, status: next })
      toast.success(`${p.tier} ${next}`)
    } catch {
      toast.error("Update failed")
    }
  }

  const actions = (p: SLAPresetOut) => (
    <DropdownMenu key={p.id}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 sm:size-9">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => setEditing(p)}>
          Edit
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setConfirm(p)}>
          {p.status === "active" ? "Disable" : "Enable"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div>
      <PageHeader
        title="SLA Presets"
        description={`${rows.length} preset(s)`}
        actions={<SlaPresetFormDialog />}
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No SLA presets yet"
        emptyHint="Create the first SLA preset."
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tier</TableHead>
                <TableHead>Accept (s)</TableHead>
                <TableHead>Fulfilment (s)</TableHead>
                <TableHead>Supervisor (s)</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">{p.tier}</TableCell>
                  <TableCell className="tabular-nums">
                    {p.accept_window_seconds}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {p.fulfilment_sla_seconds}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {p.supervisor_sla_seconds}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={p.status} />
                  </TableCell>
                  <TableCell className="text-right">{actions(p)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={rows.map((p) => (
          <div
            key={p.id}
            className="flex items-center justify-between rounded-lg border p-3"
          >
            <div className="space-y-0.5">
              <div className="text-sm font-medium">{p.tier}</div>
              <div className="text-muted-foreground text-xs">
                accept {p.accept_window_seconds}s · ful{" "}
                {p.fulfilment_sla_seconds}s · sup{" "}
                {p.supervisor_sla_seconds}s
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={p.status} />
              {actions(p)}
            </div>
          </div>
        ))}
      />
      <SlaPresetFormDialog
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
            ? "Disable SLA preset?"
            : "Enable SLA preset?"
        }
        description={confirm?.tier}
        confirmLabel={confirm?.status === "active" ? "Disable" : "Enable"}
        onConfirm={() => {
          if (confirm) toggle(confirm)
          setConfirm(null)
        }}
      />
    </div>
  )
}
