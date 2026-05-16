import { Button } from "@/components/ui/button"
import {
  useTaskQueue,
  useAcceptWorkOrder,
  useEscalateWorkOrder,
} from "@/shell/servicer/hooks/use-servicer"

// Task Queue: pushed + claimable tasks. Data via TanStack Query.
export function ServicerQueue() {
  const queue = useTaskQueue()
  const accept = useAcceptWorkOrder()
  const escalate = useEscalateWorkOrder()

  const tasks = queue.data?.tasks ?? []

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Task Queue</h1>
      <p className="text-muted-foreground text-sm">
        Pushed (owned) and claimable (claim-fallback) tasks, each with an
        accept-window and SLA countdown (D12/D23).
      </p>

      {queue.isLoading && (
        <p className="text-muted-foreground text-sm">Loading queue…</p>
      )}
      {queue.isError && (
        <p className="text-destructive text-sm">
          Couldn’t load the queue. Retrying…
        </p>
      )}
      {!queue.isLoading && !queue.isError && tasks.length === 0 && (
        <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
          No tasks right now.
        </div>
      )}

      <div className="space-y-2">
        {tasks.map((t) => (
          <div
            key={t.workOrderId}
            className="bg-card text-card-foreground flex items-center justify-between rounded-xl border p-3"
          >
            <div>
              <div className="text-sm font-medium">{t.title}</div>
              <div className="text-muted-foreground text-xs">
                {t.kind} · SLA {t.slaSecondsLeft}s
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={accept.isPending}
                onClick={() => accept.mutate(t.workOrderId)}
              >
                Accept
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={escalate.isPending}
                onClick={() => escalate.mutate(t.workOrderId)}
              >
                Escalate
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
