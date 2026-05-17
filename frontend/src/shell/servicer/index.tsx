import { useState } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/common/error-state"
import { ShiftCard } from "@/components/common/shift-card"
import { PresenceControl } from "@/components/common/presence-control"
import { Countdown } from "@/components/common/countdown"
import { ApiError } from "@/lib/api-client"
import { useServicerHome, usePresence } from "@/shell/servicer/hooks/use-servicer"
import { useTasks, type Task } from "@/shell/servicer/hooks/use-tasks"
import { TaskDetail } from "@/shell/servicer/pages/task-detail"

// F3 (Spec §10 Servicer) — the servicer index becomes the Task Queue (the
// working screen). Staffing's home (shift card + presence control + its
// use-servicer hooks) is NOT discarded: it is ABSORBED into a compact sticky
// header band so shift/presence stay fully functional (back-compat). Below
// it: the polled queue (pushed owned + claimable in-zone) with live deadlines
// (F1 Countdown, server-truth, AD5/D23). Mobile-first, monochrome. The Task
// Detail Sheet drills into one work order.

function TaskRow({
  task,
  onOpen,
}: {
  task: Task
  onOpen: (t: Task) => void
}) {
  // The relevant live deadline: accept-window before acceptance, else the
  // fulfilment SLA. Server-truth target — F1 Countdown ticks the display.
  const deadline = task.accept_window_deadline ?? task.fulfilment_sla_deadline
  return (
    <button
      type="button"
      onClick={() => onOpen(task)}
      className="flex w-full items-center justify-between gap-3 rounded-lg border p-4 text-left transition-colors hover:bg-muted"
    >
      <div className="min-w-0 space-y-1">
        <div className="truncate text-sm font-medium">
          {task.issue_label ?? "Work order"}
        </div>
        <div className="text-muted-foreground text-xs">
          {task.state} · {task.priority_tier}
        </div>
      </div>
      {deadline ? (
        <Countdown deadline={deadline} className="shrink-0" />
      ) : (
        <span className="text-muted-foreground shrink-0 text-xs">—</span>
      )}
    </button>
  )
}

export function ServicerHome() {
  const home = useServicerHome()
  const presence = usePresence()
  const tasks = useTasks()

  const [selected, setSelected] = useState<Task | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const openTask = (t: Task) => {
    setSelected(t)
    setDetailOpen(true)
  }

  // Staffing's one write, preserved verbatim (back-compat with use-servicer).
  const onPresenceChange = (next: NonNullable<typeof home.data>["presence"]) => {
    presence.mutate(next, {
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409) {
          toast.error("Your shift isn’t active right now")
        } else {
          toast.error("Couldn’t update presence")
        }
        home.refetch()
      },
    })
  }

  const h = home.data
  const list = tasks.data ?? []
  const pushed = list.filter((t) => t.kind === "pushed")
  const claimable = list.filter((t) => t.kind === "claimable")

  return (
    <div className="mx-auto max-w-md">
      {/* Compact STICKY HEADER — staffing's home content absorbed here.
          Shift card + presence control keep their use-servicer wiring. */}
      <div className="bg-background sticky top-0 z-10 -mx-4 space-y-3 border-b px-4 pt-2 pb-3">
        {home.isLoading ? (
          <>
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-9 w-full" />
          </>
        ) : home.isError || !h ? (
          <ErrorState
            title="Couldn’t load your shift."
            onRetry={() => home.refetch()}
          />
        ) : (
          <>
            <ShiftCard
              currentShift={h.current_shift}
              nextShift={h.next_shift}
            />
            <PresenceControl
              value={h.presence}
              locked={h.presence_locked}
              onChange={onPresenceChange}
            />
          </>
        )}
      </div>

      {/* The Task Queue — the working screen. */}
      <div className="space-y-6 pt-5">
        {tasks.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : tasks.isError ? (
          <ErrorState
            title="Couldn’t load your queue."
            onRetry={() => tasks.refetch()}
          />
        ) : (
          <>
            <section className="space-y-2">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold tracking-tight">
                  Your tasks
                </h2>
                <Badge variant="secondary">{pushed.length}</Badge>
              </div>
              {pushed.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  No tasks assigned to you.
                </p>
              ) : (
                <div className="space-y-2">
                  {pushed.map((t) => (
                    <TaskRow
                      key={t.work_order_id}
                      task={t}
                      onOpen={openTask}
                    />
                  ))}
                </div>
              )}
            </section>

            <section className="space-y-2">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold tracking-tight">
                  Claimable in your zone
                </h2>
                <Badge variant="secondary">{claimable.length}</Badge>
              </div>
              {claimable.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Nothing to claim right now.
                </p>
              ) : (
                <div className="space-y-2">
                  {claimable.map((t) => (
                    <TaskRow
                      key={t.work_order_id}
                      task={t}
                      onOpen={openTask}
                    />
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>

      <TaskDetail
        task={selected}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />
    </div>
  )
}
