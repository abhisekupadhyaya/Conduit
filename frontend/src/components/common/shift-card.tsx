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
  new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })

// Calm + human: under an hour → "in 47m"; same-day → "in 6h"; further out →
// an absolute "Fri 5:00 PM". Never a raw "71h 47m".
function humane(toIso: string, now: Date): string {
  const then = new Date(toIso)
  const ms = then.getTime() - now.getTime()
  if (ms <= 0) return "now"
  const mins = Math.round(ms / 60000)
  if (mins < 60) return `in ${mins}m`
  const sameDay = then.toDateString() === now.toDateString()
  if (sameDay) {
    const h = Math.round(mins / 60)
    return `in ${h}h`
  }
  return then.toLocaleString([], {
    weekday: "short", hour: "numeric", minute: "2-digit",
  })
}

export function ShiftCard({
  currentShift, nextShift, now = new Date(),
}: {
  currentShift: Shift | null
  nextShift: Shift | null
  now?: Date
}) {
  const shift = currentShift ?? nextShift
  const onShift = currentShift !== null

  return (
    <div className="bg-muted/40 space-y-3 rounded-lg border p-4">
      {shift ? (
        <>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-base font-semibold tracking-tight">
              {shift.section_label ?? "No section"}
            </span>
            <span className="text-muted-foreground text-xs capitalize">
              {shift.role}
            </span>
          </div>
          <div className="text-foreground text-sm tabular-nums">
            {timeFmt(shift.shift_start)} – {timeFmt(shift.shift_end)}
          </div>
        </>
      ) : (
        <div className="text-sm font-medium">No shift assigned</div>
      )}

      <div className="flex items-center gap-2 border-t pt-3">
        <span
          className={
            onShift
              ? "bg-foreground size-1.5 rounded-full"
              : "border-muted-foreground size-1.5 rounded-full border"
          }
        />
        <span className="text-muted-foreground text-xs">
          {currentShift
            ? `On shift · ends ${humane(currentShift.shift_end, now)}`
            : nextShift
              ? `Off shift · next ${humane(nextShift.shift_start, now)}`
              : "No upcoming shift"}
        </span>
      </div>
    </div>
  )
}
