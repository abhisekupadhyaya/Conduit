import {
  ToggleGroup, ToggleGroupItem,
} from "@/components/ui/toggle-group"

// The servicer's one write (D39). Backend contract
// (servicer/schemas/home.py): PUT /servicer/presence {presence}. Off-shift
// the server gates with 409 (the real lock); the UI lock here is the
// "lock taught as care" surface (spec §10) — disabled + a reassuring
// caption, never a silent dead control. The mutation is wired by a later
// task; this component only emits the chosen value.

export type Presence = "working" | "on_break" | "off"

const OPTIONS: { value: Presence; label: string }[] = [
  { value: "working", label: "Working" },
  { value: "on_break", label: "On break" },
  { value: "off", label: "Off" },
]

export function PresenceControl({
  value, locked, onChange,
}: {
  value: Presence
  // Off-shift: the toggle is locked (spec §4 — presence is shift-scoped).
  locked: boolean
  onChange: (next: Presence) => void
}) {
  return (
    <div className="space-y-2">
      <ToggleGroup
        type="single"
        variant="outline"
        value={value}
        disabled={locked}
        onValueChange={(v) => {
          // Radix single toggle-group allows deselect → ""; ignore that so
          // presence always has a value (Working is the default, D39).
          if (v) onChange(v as Presence)
        }}
      >
        {OPTIONS.map((o) => (
          <ToggleGroupItem
            key={o.value}
            value={o.value}
            aria-label={o.label}
            className="flex-1"
          >
            {o.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {locked && (
        <p className="text-muted-foreground text-xs">
          Available when your shift starts
        </p>
      )}
    </div>
  )
}
