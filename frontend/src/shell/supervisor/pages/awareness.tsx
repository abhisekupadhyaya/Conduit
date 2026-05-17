import type { ReactNode } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { useAwareness } from "@/shell/supervisor/hooks/use-awareness"

// Awareness Stream — the ONE composite event-derived projection (Spec
// §8/§9, E6). WATCH-ONLY and a SEPARATE route from the Decision Queue
// (D2 — watch vs act; the two are never folded together). Polled (AD7);
// there are deliberately NO actions on this surface.

function fmt(at: string): string {
  const d = new Date(at)
  return Number.isNaN(d.getTime()) ? at : d.toLocaleString()
}

function Section<T>({
  title,
  rows,
  columns,
  cells,
  rowKey,
}: {
  title: string
  rows: T[]
  columns: string[]
  cells: (r: T) => ReactNode[]
  rowKey: (r: T) => string
}) {
  const state = rows.length === 0 ? "empty" : "ready"
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold tracking-tight">
        {title}{" "}
        <span className="text-muted-foreground font-normal">
          ({rows.length})
        </span>
      </h2>
      <DataTableShell
        state={state}
        emptyTitle={`No ${title.toLowerCase()}`}
        table={
          <Table>
            <TableHeader>
              <TableRow>
                {columns.map((c) => (
                  <TableHead key={c}>{c}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={rowKey(r)}>
                  {cells(r).map((c, i) => (
                    <TableCell key={i}>{c}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={rows.map((r) => (
          <div
            key={rowKey(r)}
            className="space-y-1 rounded-lg border p-3 text-xs"
          >
            {columns.map((c, i) => (
              <div key={c} className="flex justify-between gap-2">
                <span className="text-muted-foreground">{c}</span>
                <span className="text-right">{cells(r)[i]}</span>
              </div>
            ))}
          </div>
        ))}
      />
    </section>
  )
}

export function AwarenessPage() {
  const q = useAwareness()
  const a = q.data

  if (q.isLoading || q.isError || !a) {
    const state = q.isLoading ? "loading" : "error"
    return (
      <div>
        <PageHeader
          title="Awareness Stream"
          description="Live oversight — watch only (D2/D9). The decision queue is where you act."
        />
        <DataTableShell
          state={state}
          onRetry={q.refetch}
          emptyTitle="No telemetry"
          table={null}
          cards={null}
        />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Awareness Stream"
        description="The composite event projection — watch only (D2). Polled live (AD7). The decision queue is where you act."
      />
      <Section
        title="Incoming"
        rows={a.incoming}
        columns={["Request", "Trigger", "At"]}
        rowKey={(r) => r.escalation_id}
        cells={(r) => [
          r.issue_label ?? "Uncategorized",
          r.trigger.replace(/_/g, " "),
          fmt(r.at),
        ]}
      />
      <Section
        title="Task delegation"
        rows={a.task_delegation}
        columns={["Request", "Servicer", "At"]}
        rowKey={(r) => r.work_order_id}
        cells={(r) => [
          r.issue_label ?? "Uncategorized",
          r.servicer_name ?? "—",
          fmt(r.at),
        ]}
      />
      <Section
        title="Servicer recent work"
        rows={a.servicer_recent_work}
        columns={["Request", "Servicer", "At"]}
        rowKey={(r) => r.work_order_id}
        cells={(r) => [
          r.issue_label ?? "Uncategorized",
          r.servicer_name ?? "—",
          fmt(r.at),
        ]}
      />
      <Section
        title="Open glitches"
        rows={a.open_glitches}
        columns={["Request", "Opened from", "At"]}
        rowKey={(r) => r.glitch_id}
        cells={(r) => [
          r.issue_label ?? "Uncategorized",
          r.opened_from.replace(/_/g, " "),
          fmt(r.at),
        ]}
      />
    </div>
  )
}
