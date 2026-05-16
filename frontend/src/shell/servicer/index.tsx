import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/common/error-state"
import { ShiftCard } from "@/components/common/shift-card"
import { PresenceControl } from "@/components/common/presence-control"
import { ApiError } from "@/lib/api-client"
import { useAuth } from "@/auth/use-auth"
import { useServicerHome, usePresence } from "@/shell/servicer/hooks/use-servicer"

// Servicer home (spec §10) — one calm screen, centered and framed: who you
// are, your shift, the one presence control. The restraint is the design.

const initials = (name?: string) =>
  (name ?? "S")
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4 py-10">
      <div className="bg-card w-full max-w-sm space-y-6 rounded-lg border p-6">
        {children}
      </div>
    </div>
  )
}

export function ServicerHome() {
  const { user } = useAuth()
  const home = useServicerHome()
  const presence = usePresence()

  if (home.isLoading) {
    return (
      <Frame>
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="space-y-1.5">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-4 w-20" />
          </div>
        </div>
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-10 w-full rounded-md" />
      </Frame>
    )
  }

  if (home.isError || !home.data) {
    return (
      <Frame>
        <ErrorState
          title="Couldn’t load your home."
          onRetry={() => home.refetch()}
        />
      </Frame>
    )
  }

  const h = home.data

  const onPresenceChange = (next: typeof h.presence) => {
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

  return (
    <Frame>
      {/* Identity — one human touch (the monogram) in a monochrome UI. */}
      <div className="flex items-center gap-3">
        <div className="bg-muted text-foreground flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
          {initials(user?.name)}
        </div>
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-xl font-semibold tracking-tight">
              {user?.name ?? "Servicer"}
            </h1>
            {h.profile && (
              <Badge
                variant="outline"
                className="text-muted-foreground shrink-0 capitalize"
              >
                {h.profile.class.replace(/_/g, " ")}
              </Badge>
            )}
          </div>
          {h.profile === null ? (
            <p className="text-muted-foreground text-sm">
              Profile pending — your supervisor will set this up.
            </p>
          ) : h.skills.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {h.skills.map((s) => (
                <span
                  key={s}
                  className="text-muted-foreground bg-muted/60 rounded px-1.5 py-0.5 text-xs"
                >
                  {s}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <ShiftCard currentShift={h.current_shift} nextShift={h.next_shift} />

      <div className="space-y-2">
        <PresenceControl
          value={h.presence}
          locked={h.presence_locked}
          onChange={onPresenceChange}
        />
        <p className="text-muted-foreground text-xs">
          On break and off pause new task routing.
        </p>
      </div>
    </Frame>
  )
}
