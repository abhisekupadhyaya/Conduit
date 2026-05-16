import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/common/error-state"
import { RoleBadge } from "@/components/common/role-badge"
import { ShiftCard } from "@/components/common/shift-card"
import { PresenceControl } from "@/components/common/presence-control"
import { ApiError } from "@/lib/api-client"
import { useAuth } from "@/auth/use-auth"
import { useServicerHome, usePresence } from "@/shell/servicer/hooks/use-servicer"

// Servicer home (spec §10) — one calm mobile-first screen: identity, the
// derived shift card, the one presence control, one consequence line. The
// restraint is the design. Bound to the real ServicerHomeOut.
export function ServicerHome() {
  const { user } = useAuth()
  const home = useServicerHome()
  const presence = usePresence()

  if (home.isLoading) {
    return (
      <div className="mx-auto max-w-md space-y-4">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (home.isError || !home.data) {
    return (
      <div className="mx-auto max-w-md">
        <ErrorState
          title="Couldn’t load your home."
          onRetry={() => home.refetch()}
        />
      </div>
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
        // Re-sync to the authoritative server state.
        home.refetch()
      },
    })
  }

  return (
    <div className="mx-auto max-w-md space-y-5">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold tracking-tight">
            {user?.name ?? "Servicer"}
          </h1>
          {h.profile && <RoleBadge role={h.profile.class} />}
        </div>

        {h.profile === null ? (
          <p className="text-muted-foreground text-sm">
            Profile pending — a supervisor will set up your class and skills.
          </p>
        ) : h.skills.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {h.skills.map((s) => (
              <Badge key={s} variant="secondary">
                {s}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>

      <ShiftCard
        currentShift={h.current_shift}
        nextShift={h.next_shift}
      />

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
    </div>
  )
}
