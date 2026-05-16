// Awareness Stream — watch, no action (D2). Scaffolding placeholder.
export function SupervisorHome() {
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Awareness Stream</h1>
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
