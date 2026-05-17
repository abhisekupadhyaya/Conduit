import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"

// Client-ticking countdown to a SERVER-PROVIDED deadline (AD5: the DB/server
// clock is truth — the displayed remaining time is always measured against the
// `deadline` prop, never a client-recomputed target). The poll re-supplies a
// fresh `deadline` on each cycle; a prop change re-syncs the tick. The local
// interval only advances the displayed "now" — it never derives the deadline
// from client state.
export function Countdown({
  deadline,
  className,
}: {
  // ISO-8601 string, server-provided. The sole source of truth for the target.
  deadline: string
  className?: string
}) {
  const [now, setNow] = useState(() => Date.now())

  // Re-sync on every deadline change (a fresh poll) and tick once a second.
  // Cleanup on unmount and on deadline change so no stale interval survives.
  useEffect(() => {
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [deadline])

  // Target is read straight off the prop on every render — never cached or
  // recomputed from client state (AD5).
  const remainingMs = new Date(deadline).getTime() - now

  if (remainingMs <= 0) {
    return (
      <span className={cn("text-muted-foreground text-sm font-medium", className)}>
        Overdue
      </span>
    )
  }

  return (
    <span className={cn("text-sm tabular-nums", className)}>
      {formatRemaining(remainingMs)}
    </span>
  )
}

// mm:ss under an hour; "Hh Mm" once an hour or more out.
function formatRemaining(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`
}
