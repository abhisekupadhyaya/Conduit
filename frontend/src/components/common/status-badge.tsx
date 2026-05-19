import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

// Spec §10 (relocation) — ONE unified MONOCHROME taxonomy for every
// child / work-order / escalation / glitch state + priority P1–P4. No
// chromatic color anywhere: severity is expressed by WEIGHT, never by red.
//   - tone "muted"  : calm / terminal-benign / informational
//   - tone "normal" : in-flight, the default
//   - tone "strong" : needs attention — heavier weight, NOT a color
//   - tone "p1"     : the single highest signal — font-weight + a 2px left
//                     rule. Deliberately NOT chromatic (decision 6a / §10).
export type StatusTone = "muted" | "normal" | "strong" | "p1"

type Entry = { label: string; tone: StatusTone }

// Every known state across the surfaces, normalized to one vocabulary. Keys
// are the raw server tokens (snake_case); unknown tokens fall back to a
// humanized label at "normal" tone so the badge always renders.
const TAXONOMY: Record<string, Entry> = {
  // --- child / work-order / dispatch lifecycle ---
  routing: { label: "Routing", tone: "normal" },
  pushed: { label: "Assigned", tone: "normal" },
  broadcast: { label: "Broadcasting", tone: "normal" },
  accepted: { label: "Accepted", tone: "normal" },
  in_progress: { label: "In progress", tone: "normal" },
  done_pending_confirm: { label: "Awaiting confirm", tone: "strong" },
  closed: { label: "Resolved", tone: "muted" },
  resolved: { label: "Resolved", tone: "muted" },
  reopened: { label: "Reopened", tone: "strong" },
  cancelled: { label: "Cancelled", tone: "muted" },
  answered: { label: "Answered", tone: "muted" },
  logged: { label: "Logged", tone: "muted" },
  active: { label: "Active", tone: "normal" },
  pending: { label: "Pending", tone: "normal" },
  // --- escalation / glitch ---
  open: { label: "Open", tone: "strong" },
  triage_flag: { label: "Triage flagged", tone: "strong" },
  stall: { label: "Stalled", tone: "strong" },
  servicer_raised: { label: "Servicer raised", tone: "strong" },
  glitch: { label: "Needs attention", tone: "strong" },
  duty_manager: { label: "Duty manager", tone: "strong" },
  non_time_boxed: { label: "Not time-boxed", tone: "strong" },
  relocation_move: { label: "Guest move", tone: "normal" },
  // --- priority P1–P4 (weight, never chroma) ---
  p1: { label: "P1", tone: "p1" },
  p2: { label: "P2", tone: "strong" },
  p3: { label: "P3", tone: "normal" },
  p4: { label: "P4", tone: "muted" },
}

function humanize(raw: string): string {
  return raw.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
}

export function resolveStatus(raw: string): Entry {
  const key = raw.trim().toLowerCase()
  return TAXONOMY[key] ?? { label: humanize(raw), tone: "normal" }
}

const TONE_VARIANT: Record<
  StatusTone,
  "default" | "secondary" | "outline"
> = {
  muted: "outline",
  normal: "outline",
  strong: "secondary",
  p1: "secondary",
}

const TONE_CLASS: Record<StatusTone, string> = {
  muted: "text-muted-foreground font-normal",
  normal: "font-normal",
  strong: "font-medium",
  // P1 — the single highest signal: heavier weight + a 2px left rule.
  // Monochrome by construction (border-foreground, not destructive).
  p1: "font-semibold border-l-2 border-l-foreground pl-1.5 rounded-l-none",
}

// Back-compat: the original API is `{ status }` and existing callers across
// guest receipt / servicer queue / decision queue / awareness / task-explorer
// keep working unchanged. An optional `label` override is additive.
export function StatusBadge({
  status,
  label,
  className,
}: {
  status: string
  label?: string
  className?: string
}) {
  const entry = resolveStatus(status)
  return (
    <Badge
      variant={TONE_VARIANT[entry.tone]}
      className={cn(TONE_CLASS[entry.tone], className)}
    >
      {label ?? entry.label}
    </Badge>
  )
}
