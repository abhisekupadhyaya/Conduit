import { useEffect, useState } from "react"
import { toast } from "sonner"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { Countdown } from "@/components/common/countdown"
import { ApiError } from "@/lib/api-client"
import {
  useClaim,
  useAccept,
  useStart,
  useComplete,
  useRaise,
  type Task,
} from "@/shell/servicer/hooks/use-tasks"

// F3 (Spec §10 Servicer) — the Task Detail drill-in. A controlled `Sheet`
// (the merged primitive) over ONE work order: claim / accept / start /
// complete{notes} / raise{reason}, each wired to the use-tasks mutations
// which invalidate ['servicer','tasks'] so the queue re-derives on the next
// poll. Mobile-first (bottom sheet) + monochrome. Live deadlines reuse the
// F1 `Countdown` (server-truth target, AD5/D23).

function fail(err: unknown, fallback: string) {
  if (err instanceof ApiError) {
    if (err.status === 409) return toast.error("That action isn’t available right now")
    if (err.status === 403) return toast.error("This task isn’t in your zone")
  }
  toast.error(fallback)
}

export function TaskDetail({
  task,
  open,
  onOpenChange,
}: {
  // null when nothing is selected — the Sheet stays closed.
  task: Task | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const claim = useClaim()
  const accept = useAccept()
  const start = useStart()
  const complete = useComplete()
  const raise = useRaise()

  const [notes, setNotes] = useState("")
  const [reason, setReason] = useState("")

  // Reset the per-task draft fields whenever the selected work order changes.
  useEffect(() => {
    setNotes("")
    setReason("")
  }, [task?.work_order_id])

  const busy =
    claim.isPending ||
    accept.isPending ||
    start.isPending ||
    complete.isPending ||
    raise.isPending

  if (!task) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" />
      </Sheet>
    )
  }

  const wo = task.work_order_id

  // Action gating mirrors the WorkOrder state machine (spec §6/§7): a
  // claimable (broadcast in-zone) task must be claimed before accept;
  // accept only pre-acceptance; start only when accepted; complete only
  // when in_progress. Rendering just the valid next action means a stale
  // re-click is impossible (was the 409 source).
  const canClaim = task.kind === "claimable"
  const canAccept =
    task.kind === "pushed" &&
    ["created", "pushed", "broadcast"].includes(task.state)
  const canStart = task.state === "accepted"
  const canComplete = task.state === "in_progress"

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="max-h-[90vh] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>{task.issue_label ?? "Work order"}</SheetTitle>
          <SheetDescription>
            {task.state} · {task.priority_tier}
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-5 px-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={task.kind === "pushed" ? "default" : "secondary"}>
              {task.kind === "pushed" ? "Assigned to you" : "Claimable"}
            </Badge>
          </div>

          {(task.accept_window_deadline || task.fulfilment_sla_deadline) && (
            <div className="space-y-1.5 rounded-lg border p-4">
              {task.accept_window_deadline && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Accept window</span>
                  <Countdown deadline={task.accept_window_deadline} />
                </div>
              )}
              {task.fulfilment_sla_deadline && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Fulfilment SLA</span>
                  <Countdown deadline={task.fulfilment_sla_deadline} />
                </div>
              )}
            </div>
          )}

          {/* Lifecycle actions (D12/D23/D14). Only the valid next action
              for the CURRENT state renders — the sheet re-derives from the
              live queue after each mutation, so the action advances
              (claim → accept → start → complete) and a stale re-click can
              no longer 409. */}
          {(canClaim || canAccept || canStart) && (
            <div className="flex flex-wrap gap-2">
              {canClaim && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    claim.mutate(wo, {
                      onError: (e) => fail(e, "Couldn’t claim this task"),
                    })
                  }
                >
                  Claim
                </Button>
              )}
              {canAccept && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    accept.mutate(wo, {
                      onError: (e) => fail(e, "Couldn’t accept this task"),
                    })
                  }
                >
                  Accept
                </Button>
              )}
              {canStart && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    start.mutate(wo, {
                      onError: (e) => fail(e, "Couldn’t start this task"),
                    })
                  }
                >
                  Start
                </Button>
              )}
            </div>
          )}

          {canComplete && (
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="task-notes">
                Completion notes
              </label>
              <Textarea
                id="task-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optional — what was done"
                rows={3}
              />
              <Button
                className="w-full"
                disabled={busy}
                onClick={() =>
                  complete.mutate(
                    { woId: wo, notes: notes.trim() || undefined },
                    {
                      onSuccess: () => {
                        toast.success("Task completed")
                        onOpenChange(false)
                      },
                      onError: (e) => fail(e, "Couldn’t complete this task"),
                    },
                  )
                }
              >
                Complete
              </Button>
            </div>
          )}

          <div className="space-y-2 border-t pt-4">
            <label className="text-sm font-medium" htmlFor="task-reason">
              Raise an escalation
            </label>
            <Textarea
              id="task-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why this needs escalating"
              rows={2}
            />
            <Button
              variant="secondary"
              className="w-full"
              disabled={busy || !reason.trim()}
              onClick={() =>
                raise.mutate(
                  { woId: wo, reason: reason.trim() },
                  {
                    onSuccess: () => {
                      toast.success("Escalation raised")
                      setReason("")
                    },
                    onError: (e) => fail(e, "Couldn’t raise an escalation"),
                  },
                )
              }
            >
              Raise escalation
            </Button>
          </div>
        </div>

        <SheetFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
