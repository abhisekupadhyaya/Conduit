import { useDecisionQueue } from "@/shell/supervisor/hooks/use-supervisor"

// Awareness Stream — watch, no action (D2). The decision-queue count is a
// required, available API and is wired through TanStack Query (polled, AD7).
// The per-panel event-stream feed is a later endpoint, still a placeholder.
export function SupervisorHome() {
  const decisions = useDecisionQueue()
  const pending = decisions.data?.items.length

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Awareness Stream</h1>
        <span className="text-muted-foreground text-xs">
          {decisions.isLoading
            ? "decisions…"
            : decisions.isError
              ? "decisions: unavailable"
              : `${pending ?? 0} pending decision(s)`}
        </span>
      </div>
      <p className="text-muted-foreground text-sm">
        Live oversight of all requests, tasks, and glitches. No action here —
        the decision queue is where the supervisor acts (D2/D9).
      </p>
      <div className="grid gap-4 pt-4 md:grid-cols-3">
        {["Incoming", "Task delegation", "Recent work"].map((p) => (
          <div
            key={p}
            className="bg-card text-card-foreground rounded-xl border p-4"
          >
            <div className="text-sm font-medium">{p}</div>
            <div className="text-muted-foreground mt-2 text-xs">
              Telemetry stream — to be wired to the event log.
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
