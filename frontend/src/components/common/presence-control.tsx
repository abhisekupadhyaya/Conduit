import {
  ToggleGroup, ToggleGroupItem,
} from "@/components/ui/toggle-group"

// The servicer's one write (D39). Backend contract
// (servicer/schemas/home.py): PUT /servicer/presence {presence}. Off-shift
// the server gates with 409 (the real lock); the UI lock here is the
// "lock taught as care" surface (spec §10) — disabled + a reassuring
// caption, never a silent dead control.

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
      {/* Recessed track + raised selected pill — a calm monochrome
          segmented control, not three bordered buttons jammed together. */}
      <ToggleGroup
        type="single"
        value={value}
        disabled={locked}
        onValueChange={(v) => {
          // Radix single toggle-group allows deselect → ""; ignore that so
          // presence always has a value (Working is the default, D39).
          if (v) onChange(v as Presence)
        }}
        className="bg-muted/60 grid w-full grid-cols-3 gap-1 rounded-md border p-1"
      >
        {OPTIONS.map((o) => (
          <ToggleGroupItem
            key={o.value}
            value={o.value}
            aria-label={o.label}
            className="text-muted-foreground hover:text-foreground h-8 rounded-[5px] border-0 bg-transparent text-sm font-normal data-[state=on]:bg-background data-[state=on]:font-medium data-[state=on]:text-foreground data-[state=on]:shadow-sm"
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
