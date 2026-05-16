// The at-a-glance presence+availability glyph for the supervisor Staff
// table (spec §10). Monochrome discipline: weight/fill-differentiated
// ONLY — a filled ● when effective-available, a hollow ○ otherwise.
// NEVER a colour alarm (red/green), per spec §10. Composes
// `presence` + `current_shift`-derived on-shift into one calm line.

import { type Presence } from "@/components/common/presence-control"

export function StaffPresenceCell({
  presence, onShift, effectiveAvailable,
}: {
  presence: Presence
  onShift: boolean
  effectiveAvailable: boolean
}) {
  // Read as a status, never two flags that look contradictory:
  //  • available        → ● Available
  //  • on shift, paused → ○ On break · on shift   (state, then context)
  //  • off shift        → ○ Off shift   (presence is not actionable here)
  const glyph = effectiveAvailable ? "●" : "○"
  let primary: string
  let context: string | null = null
  if (effectiveAvailable) {
    primary = "Available"
  } else if (onShift) {
    primary = presence.replace(/_/g, " ")
    context = "on shift"
  } else {
    primary = "Off shift"
  }
  return (
    <span
      className={
        effectiveAvailable
          ? "inline-flex items-center gap-1.5 text-sm font-medium"
          : "text-muted-foreground inline-flex items-center gap-1.5 text-sm"
      }
    >
      <span aria-hidden>{glyph}</span>
      <span className="capitalize">{primary}</span>
      {context && (
        <span className="text-muted-foreground">· {context}</span>
      )}
    </span>
  )
}
