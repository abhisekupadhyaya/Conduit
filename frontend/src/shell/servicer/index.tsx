// Task Queue — the working screen (sitemap 2.2): pushed + claimable tasks.
export function ServicerQueue() {
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Task Queue</h1>
      <p className="text-muted-foreground text-sm">
        Pushed (owned) and claimable (claim-fallback) tasks, each with an
        accept-window and SLA countdown (D12/D23). Wiring pending.
      </p>
      <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
        No tasks yet.
      </div>
    </div>
  )
}
