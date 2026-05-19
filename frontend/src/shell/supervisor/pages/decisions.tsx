import { useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { Countdown } from "@/components/common/countdown"
import { RelocationDecision } from "@/components/common/relocation-decision"
import {
  useDecisions,
  useResolveDecision,
  type DecisionOut,
  type ResolveAction,
} from "@/shell/supervisor/hooks/use-decisions"

// Decision Queue — the D9 time-boxed checkpoint surface (Spec §8 / §7.4).
// ACT-only: distinct route from the watch-only Awareness Stream (D2). The
// supervisor-SLA countdown is the server-truth deadline; silence →
// auto-proceed is the ENGINE path (not an API call here) — this screen
// surfaces the deadline (AD5) and offers the explicit resolve.

// The typed `ck_rec_action` vocabulary and its per-action params, mirroring
// the backend `rec_*` detail rows verbatim (dal/decisions.py):
//   reassign  -> target_account_id
//   relocate  -> target_room_id
//   extend_sla-> extend_seconds
//   apply_reservation_mutation -> requested_value
//   broadcast/approve/deny -> no params
const REC_ACTIONS = [
  "reassign",
  "relocate",
  "extend_sla",
  "apply_reservation_mutation",
  "broadcast",
  "approve",
  "deny",
] as const
type RecAction = (typeof REC_ACTIONS)[number]

function paramValue(detail: Record<string, unknown>, k: string): string {
  const v = detail[k]
  return v === undefined || v === null ? "" : String(v)
}

// The per-action editable form. `approve` runs the STORED rec verbatim (no
// payload); `edit`/`override` send `{ action, ...params }` where params
// mirror the rec detail keys exactly (services/decisions.py contract).
function ResolveDialog({ d }: { d: DecisionOut }) {
  const [open, setOpen] = useState(false)
  const resolve = useResolveDecision()
  const rec = d.recommendation

  const [resolveAction, setResolveAction] = useState<ResolveAction>("approve")
  // The typed recommendation action to apply for edit/override — seeded
  // from the AI rec so "edit" starts as a tweak of the recommendation.
  const [typedAction, setTypedAction] = useState<RecAction>(
    (rec?.action as RecAction) ?? "approve",
  )
  const [targetAccountId, setTargetAccountId] = useState(
    paramValue(rec?.detail ?? {}, "target_account_id"),
  )
  const [targetRoomId, setTargetRoomId] = useState(
    paramValue(rec?.detail ?? {}, "target_room_id"),
  )
  const [extendSeconds, setExtendSeconds] = useState(
    paramValue(rec?.detail ?? {}, "extend_seconds"),
  )
  const [requestedValue, setRequestedValue] = useState(
    paramValue(rec?.detail ?? {}, "requested_value"),
  )

  async function submit() {
    try {
      if (resolveAction === "approve") {
        await resolve.mutateAsync({
          escalationId: d.escalation_id,
          action: "approve",
        })
      } else {
        // edit/override → supervisor-supplied typed action + params.
        const payload: Record<string, unknown> = { action: typedAction }
        if (typedAction === "reassign")
          payload.target_account_id = targetAccountId.trim()
        if (typedAction === "relocate")
          payload.target_room_id = targetRoomId.trim()
        if (typedAction === "extend_sla")
          payload.extend_seconds = Number(extendSeconds)
        if (typedAction === "apply_reservation_mutation")
          payload.requested_value = requestedValue.trim()
        await resolve.mutateAsync({
          escalationId: d.escalation_id,
          action: resolveAction,
          payload,
        })
      }
      toast.success(`Decision ${resolveAction}d`)
      setOpen(false)
    } catch (e: any) {
      toast.error(
        e?.status === 409
          ? "Already resolved"
          : e?.status === 422
            ? "Invalid resolution payload"
            : "Could not resolve decision",
      )
    }
  }

  const editing = resolveAction !== "approve"

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">Resolve</Button>
      </DialogTrigger>
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Resolve decision</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {rec ? (
            <div className="space-y-1 rounded-md border p-3 text-sm">
              <div className="font-medium">
                Recommendation:{" "}
                <span className="font-mono">{rec.action}</span>
              </div>
              <p className="text-muted-foreground text-xs">
                {rec.rationale_text}
              </p>
              {Object.keys(rec.detail).length > 0 && (
                <div className="text-muted-foreground pt-1 text-xs">
                  {Object.entries(rec.detail).map(([k, v]) => (
                    <div key={k}>
                      <span className="font-mono">{k}</span>: {String(v)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">
              No AI recommendation on this escalation.
            </p>
          )}

          <div className="space-y-1.5">
            <Label>resolution</Label>
            <Select
              value={resolveAction}
              onValueChange={(v) => setResolveAction(v as ResolveAction)}
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="approve">
                  approve (run recommendation verbatim)
                </SelectItem>
                <SelectItem value="edit">edit</SelectItem>
                <SelectItem value="override">override</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {editing && (
            <>
              <div className="space-y-1.5">
                <Label>action</Label>
                <Select
                  value={typedAction}
                  onValueChange={(v) => setTypedAction(v as RecAction)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REC_ACTIONS.map((a) => (
                      <SelectItem key={a} value={a}>
                        {a.replace(/_/g, " ")}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {typedAction === "reassign" && (
                <div className="space-y-1.5">
                  <Label htmlFor="target_account_id">target account id</Label>
                  <Input
                    id="target_account_id"
                    value={targetAccountId}
                    onChange={(e) => setTargetAccountId(e.target.value)}
                  />
                </div>
              )}
              {typedAction === "relocate" && (
                <div className="space-y-1.5">
                  <Label htmlFor="target_room_id">target room id</Label>
                  <Input
                    id="target_room_id"
                    value={targetRoomId}
                    onChange={(e) => setTargetRoomId(e.target.value)}
                  />
                </div>
              )}
              {typedAction === "extend_sla" && (
                <div className="space-y-1.5">
                  <Label htmlFor="extend_seconds">extend seconds</Label>
                  <Input
                    id="extend_seconds"
                    type="number"
                    value={extendSeconds}
                    onChange={(e) => setExtendSeconds(e.target.value)}
                  />
                </div>
              )}
              {typedAction === "apply_reservation_mutation" && (
                <div className="space-y-1.5">
                  <Label htmlFor="requested_value">requested value</Label>
                  <Input
                    id="requested_value"
                    type="datetime-local"
                    value={requestedValue}
                    onChange={(e) => setRequestedValue(e.target.value)}
                  />
                </div>
              )}
            </>
          )}
        </div>
        <DialogFooter>
          <Button
            onClick={submit}
            disabled={resolve.isPending}
            className="w-full"
          >
            {resolve.isPending ? "Resolving…" : `Confirm ${resolveAction}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function DecisionsPage() {
  const q = useDecisions()
  const rows = q.data ?? []

  const state = q.isLoading
    ? "loading"
    : q.isError
      ? "error"
      : rows.length === 0
        ? "empty"
        : "ready"

  // Spec §10 — the `relocate` action gets the hero card; EVERY other action
  // keeps the existing compact row/dialog UNCHANGED.
  const isRelocate = (d: DecisionOut) =>
    d.recommendation?.action === "relocate"

  const slaCell = (d: DecisionOut) => {
    if (d.non_time_boxed)
      return (
        <Badge variant="outline" className="font-normal">
          duty manager · not time-boxed
        </Badge>
      )
    if (!d.supervisor_sla_deadline)
      return <span className="text-muted-foreground">—</span>
    // F1 Countdown — server-truth deadline; the poll re-supplies a fresh
    // deadline each cycle (AD5). Silence → auto-proceed is the engine path.
    return <Countdown deadline={d.supervisor_sla_deadline} />
  }

  return (
    <div>
      <PageHeader
        title="Decision Queue"
        description={`${rows.length} open decision(s) — act here (D2/D9). Silence auto-proceeds at the deadline.`}
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No open decisions"
        emptyHint="Time-boxed checkpoints land here as they open."
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Trigger</TableHead>
                <TableHead>Request</TableHead>
                <TableHead>Recommendation</TableHead>
                <TableHead>Cycle</TableHead>
                <TableHead>Supervisor SLA</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((d) =>
                isRelocate(d) ? (
                  // The hero relocate card spans the row; all other actions
                  // keep the compact row below, unchanged.
                  <TableRow key={d.escalation_id}>
                    <TableCell colSpan={6} className="p-2">
                      <RelocationDecision d={d} />
                    </TableCell>
                  </TableRow>
                ) : (
                  <TableRow key={d.escalation_id}>
                    <TableCell className="font-medium">
                      {d.trigger.replace(/_/g, " ")}
                    </TableCell>
                    <TableCell>
                      {d.issue_label ?? "Uncategorized"}
                    </TableCell>
                    <TableCell>
                      {d.recommendation ? (
                        <span className="font-mono text-xs">
                          {d.recommendation.action}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {d.cycle_count}
                    </TableCell>
                    <TableCell>{slaCell(d)}</TableCell>
                    <TableCell className="text-right">
                      <ResolveDialog d={d} />
                    </TableCell>
                  </TableRow>
                ),
              )}
            </TableBody>
          </Table>
        }
        cards={rows.map((d) =>
          isRelocate(d) ? (
            <RelocationDecision key={d.escalation_id} d={d} />
          ) : (
            <div
              key={d.escalation_id}
              className="space-y-2 rounded-lg border p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  {d.trigger.replace(/_/g, " ")}
                </span>
                {slaCell(d)}
              </div>
              <div className="text-sm">
                {d.issue_label ?? "Uncategorized"}
              </div>
              <div className="text-muted-foreground text-xs">
                {d.recommendation
                  ? `rec: ${d.recommendation.action} · cycle ${d.cycle_count}`
                  : `no rec · cycle ${d.cycle_count}`}
              </div>
              <ResolveDialog d={d} />
            </div>
          ),
        )}
      />
    </div>
  )
}
