// Shaped to the real ServicerHomeOut (servicer/schemas/home.py):
// `current_shift` is null off-shift, otherwise
// {shift_start, shift_end, section_label|null, role}; `next_shift` has the
// same shape. on_shift/availability are derived server-side and never
// stored (spec §4 anti-cache discipline) — this card only renders them.

export type Shift = {
  shift_start: string
  shift_end: string
  section_label: string | null
  role: string
}

const timeFmt = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })

function relative(toIso: string, now: Date): string {
  const ms = new Date(toIso).getTime() - now.getTime()
  if (ms <= 0) return "now"
  const mins = Math.round(ms / 60000)
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function derivedLine(
  current: Shift | null,
  next: Shift | null,
  now: Date,
): string {
  if (current) return `On shift · ends in ${relative(current.shift_end, now)}`
  if (next) return `Off shift · next ${timeFmt(next.shift_start)}`
  return "No upcoming shift"
}

export function ShiftCard({
  currentShift, nextShift, now = new Date(),
}: {
  currentShift: Shift | null
  nextShift: Shift | null
  now?: Date
}) {
  const shift = currentShift ?? nextShift
  return (
    <div className="space-y-1.5 rounded-lg border p-4">
      {shift ? (
        <div className="text-sm font-medium">
          {shift.section_label ?? "No section"} · {shift.role} ·{" "}
          {timeFmt(shift.shift_start)}–{timeFmt(shift.shift_end)}
        </div>
      ) : (
        <div className="text-sm font-medium">No shift assigned</div>
      )}
      <p className="text-muted-foreground text-xs">
        {derivedLine(currentShift, nextShift, now)}
      </p>
    </div>
  )
}
