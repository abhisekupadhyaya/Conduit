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
  const glyph = effectiveAvailable ? "●" : "○"
  const presenceLabel = presence.replace(/_/g, " ")
  const shiftLabel = onShift ? "On shift" : "Off shift"
  return (
    <span
      className={
        effectiveAvailable
          ? "inline-flex items-center gap-1.5 text-sm font-medium"
          : "inline-flex items-center gap-1.5 text-sm text-muted-foreground"
      }
    >
      <span aria-hidden>{glyph}</span>
      <span className="capitalize">{presenceLabel}</span>
      <span className="text-muted-foreground">· {shiftLabel}</span>
    </span>
  )
}
