import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/common/empty-state"
import { useDecisionQueue } from "@/shell/supervisor/hooks/use-supervisor"

// Awareness Stream — watch, no action (D2). The decision-queue count is a
// required, available API and is wired through TanStack Query (polled, AD7).
// The per-panel event-stream feed is a later endpoint, still a placeholder.
export function SupervisorHome() {
  const decisions = useDecisionQueue()
  const pending = decisions.data?.items.length

  return (
    <div className="space-y-2">
      <PageHeader
        title="Awareness Stream"
        description="Live oversight of all requests, tasks, and glitches. No action here — the decision queue is where the supervisor acts (D2/D9)."
        actions={
          <span className="text-muted-foreground text-xs">
            {decisions.isLoading
              ? "decisions…"
              : decisions.isError
                ? "decisions: unavailable"
                : `${pending ?? 0} pending decision(s)`}
          </span>
        }
      />
      <EmptyState
        title="Telemetry stream"
        hint="Incoming · Task delegation · Recent work — to be wired to the event log."
      />
    </div>
  )
}
