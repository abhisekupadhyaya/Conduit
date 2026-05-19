import { useState } from "react"
import { ArrowRight } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Countdown } from "@/components/common/countdown"
import { RoomPicker } from "@/components/common/room-picker"
import { StatusBadge } from "@/components/common/status-badge"
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card"
import {
  asRelocateDetail,
  useResolveDecision,
  type DecisionOut,
} from "@/shell/supervisor/hooks/use-decisions"

// Spec §10 (relocation) / decision 6a — the HERO relocate decision card.
// Calm, monochrome: no chromatic alarm, severity by weight only. The single
// `--accent-action` job (Approve) is the lone deliberate emphasis on the
// supervisor side (its twin is the guest "All set" — see
// child-status-card.tsx DispatchClosure's "Yes, all set").
//
// Resolve wiring is the EXISTING `useResolveDecision` contract verbatim:
//   - approve  → no payload (run the persisted rec; silence ≡ approve, D2/D3)
//   - edit     → payload = { action: 'relocate', new_room_id }  (spec §8)
//   - override → payload = { action: 'relocate' } (supervisor-supplied
//                typed action; override semantics unchanged)
export function RelocationDecision({ d }: { d: DecisionOut }) {
  const resolve = useResolveDecision()
  const rec = d.recommendation
  const detail = asRelocateDetail(rec?.detail ?? {})

  const current = detail.current_room
  const recommended = detail.recommended_room
  const eligible = detail.eligible_rooms ?? []

  // Edit starts as a tweak of the AI recommendation (its persisted room).
  const [editing, setEditing] = useState(false)
  const [chosenRoomId, setChosenRoomId] = useState<string | null>(
    recommended?.id ?? null,
  )

  const comp =
    detail.recovery_owed != null
      ? `Recovery owed: ${detail.recovery_owed}`
      : detail.recovery_cost != null
        ? `Recovery cost: ${detail.recovery_cost}`
        : null

  async function run(
    action: "approve" | "edit" | "override",
    payload?: Record<string, unknown>,
  ) {
    try {
      await resolve.mutateAsync({
        escalationId: d.escalation_id,
        action,
        ...(payload ? { payload } : {}),
      })
      toast.success(`Relocation ${action}d`)
      setEditing(false)
    } catch (e: any) {
      toast.error(
        e?.status === 409
          ? "Already resolved"
          : e?.status === 422
            ? "That room is unavailable"
            : "Could not resolve relocation",
      )
    }
  }

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Relocate guest</span>
            <StatusBadge status={d.trigger} />
            {d.non_time_boxed && <StatusBadge status="non_time_boxed" />}
          </div>
          <p className="text-muted-foreground text-xs">
            {d.issue_label ?? "Uncategorized"} · cycle {d.cycle_count}
          </p>
        </div>
        {/* Calm-prominent countdown — server-truth deadline (AD5). Silence
            auto-proceeds on the persisted room. */}
        {d.supervisor_sla_deadline && (
          <Countdown
            deadline={d.supervisor_sla_deadline}
            className="text-base font-medium"
          />
        )}
      </div>

      {/* Two-column current → proposed */}
      <div className="flex items-center gap-3 rounded-md border p-3">
        <div className="flex-1">
          <p className="text-muted-foreground text-xs">Current</p>
          <p className="font-medium">{current?.label ?? "—"}</p>
        </div>
        <ArrowRight className="text-muted-foreground size-4 shrink-0" />
        <div className="flex-1">
          <p className="text-muted-foreground text-xs">
            {editing ? "Edited to" : "Proposed"}
          </p>
          <p className="font-medium">
            {editing
              ? (eligible.find((r) => r.id === chosenRoomId)?.label ??
                "Select a room")
              : (recommended?.label ?? "—")}
          </p>
        </div>
      </div>

      {/* Eligible rooms — tight selectable list, only while editing. */}
      {editing && (
        <div className="space-y-1.5">
          <p className="text-muted-foreground text-xs">Eligible rooms</p>
          <RoomPicker
            rooms={eligible}
            value={chosenRoomId}
            onChange={setChosenRoomId}
          />
        </div>
      )}

      {/* Comp note — the manual Glitch recovery field (D19), calm. */}
      {comp && (
        <p className="text-muted-foreground text-xs">{comp}</p>
      )}

      {rec?.rationale_text && (
        <p className="text-muted-foreground text-xs">{rec.rationale_text}</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {!editing ? (
          <>
            {/* The single --accent-action job on the supervisor side. */}
            <Button
              size="xs"
              className="bg-accent-action text-primary-foreground hover:bg-accent-action/90"
              disabled={resolve.isPending}
              onClick={() => run("approve")}
            >
              Approve
            </Button>
            <Button
              size="xs"
              variant="outline"
              disabled={resolve.isPending}
              onClick={() => setEditing(true)}
            >
              Edit room
            </Button>
            <Button
              size="xs"
              variant="ghost"
              disabled={resolve.isPending}
              onClick={() => run("override", { action: "relocate" })}
            >
              Override
            </Button>
          </>
        ) : (
          <>
            <Button
              size="xs"
              disabled={resolve.isPending || !chosenRoomId}
              onClick={() =>
                run("edit", {
                  action: "relocate",
                  new_room_id: chosenRoomId,
                })
              }
            >
              {resolve.isPending ? "Saving…" : "Confirm room"}
            </Button>
            <Button
              size="xs"
              variant="ghost"
              disabled={resolve.isPending}
              onClick={() => {
                setEditing(false)
                setChosenRoomId(recommended?.id ?? null)
              }}
            >
              Cancel
            </Button>
          </>
        )}

        {/* Peek the origin request + slice-7 siblings without leaving the
            queue. Hover-only, calm. */}
        <HoverCard>
          <HoverCardTrigger asChild>
            <Button size="xs" variant="ghost">
              Context
            </Button>
          </HoverCardTrigger>
          <HoverCardContent align="end" className="w-80">
            <p className="font-medium">Origin request</p>
            <p className="text-muted-foreground text-xs">
              {d.issue_label ?? "Uncategorized"} · {d.trigger.replace(
                /_/g,
                " ",
              )}
            </p>
            <p className="text-muted-foreground text-xs">
              Escalation {d.escalation_id}
            </p>
            <p className="pt-1 font-medium">Live siblings</p>
            <p className="text-muted-foreground text-xs">
              Siblings of this request re-resolve to the new room
              automatically — no separate action needed.
            </p>
          </HoverCardContent>
        </HoverCard>
      </div>
    </div>
  )
}
