import type { ReactNode } from "react"

export function EmptyState({
  title, hint, action,
}: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
      {action}
    </div>
  )
}
