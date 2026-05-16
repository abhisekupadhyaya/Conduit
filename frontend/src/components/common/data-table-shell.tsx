import type { ReactNode } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"

type State = "loading" | "error" | "empty" | "ready"

export function DataTableShell({
  state, toolbar, table, cards, onRetry, emptyTitle, emptyHint,
}: {
  state: State
  toolbar?: ReactNode
  table: ReactNode   // rendered >= md
  cards: ReactNode   // rendered < md
  onRetry?: () => void
  emptyTitle: string
  emptyHint?: string
}) {
  return (
    <div className="space-y-4">
      {toolbar && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          {toolbar}
        </div>
      )}
      {state === "loading" && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      )}
      {state === "error" && <ErrorState onRetry={onRetry} />}
      {state === "empty" && (
        <EmptyState title={emptyTitle} hint={emptyHint} />
      )}
      {state === "ready" && (
        <>
          <div className="hidden md:block">{table}</div>
          <div className="space-y-2 md:hidden">{cards}</div>
        </>
      )}
    </div>
  )
}
