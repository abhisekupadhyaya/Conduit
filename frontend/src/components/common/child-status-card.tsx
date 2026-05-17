import type { Child, DispatchCard } from "@/shell/guest/hooks/use-conversation"
import { ClosureLite } from "@/components/common/closure-lite"
import { Countdown } from "@/components/common/countdown"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  useCancelDispatch,
  useConfirmDispatch,
  useReopenDispatch,
} from "@/shell/guest/hooks/use-conversation"

// The terminal state of one decomposed thing.
//  - answered: the grounded answer, then a light closure prompt (D8) while
//    the child is still awaiting confirmation.
//  - logged: a calm, muted line — a human has it, nothing for the guest to do.
//
// F2 (Spec §10 Guest) extends this card to the dispatch lifecycle WITHOUT
// forking: the component takes a discriminated prop — pass `child` for the
// existing no-dispatch journey (rendered EXACTLY as before — back-compat), or
// `card` for a dispatch child (the new states / named servicer (D17) /
// revised_eta countdown (D22 via the F1 countdown) / glitch badge, with the
// confirm/reopen/cancel control replacing closure-lite for dispatch children).
export function ChildStatusCard(
  props: { child: Child } | { card: DispatchCard },
) {
  if ("card" in props) {
    return <DispatchStatusCard card={props.card} />
  }
  const { child } = props
  if (child.terminal === "answered") {
    return (
      <div className="bg-muted text-foreground rounded-lg px-3 py-2 text-sm">
        <p className="whitespace-pre-wrap">{child.answer}</p>
        {child.closure_prompt && <ClosureLite childId={child.child_id} />}
      </div>
    )
  }
  return (
    <div className="text-muted-foreground rounded-lg border border-dashed px-3 py-2 text-sm">
      Logged — a team member will follow up.
    </div>
  )
}

// Guest-facing dispatch lifecycle labels (Spec §8). The card `state` surfaces
// the WorkOrder leg's progress while one is active, falling back to the child
// state once it advances (E1 DAL note) — phrased for a guest, never internal.
const STATE_LABEL: Record<string, string> = {
  routing: "Finding someone to help",
  pushed: "Assigned",
  broadcast: "Finding someone to help",
  accepted: "On the way",
  in_progress: "In progress",
  done_pending_confirm: "Done — please confirm",
  closed: "Resolved",
  reopened: "Reopened",
  cancelled: "Cancelled",
}

// The guest's final word on dispatched work (D8): confirm closes it, reopen
// says it is not resolved. Only offered once the work is awaiting the guest
// (done_pending_confirm). Cancel is allowed until Closed (D37) — offered for
// any non-terminal, not-yet-pending state. Two ghost buttons, no modal — the
// same light touch as closure-lite, swapped in for dispatch children.
function DispatchClosure({ card }: { card: DispatchCard }) {
  const confirm = useConfirmDispatch()
  const reopen = useReopenDispatch()
  const cancel = useCancelDispatch()
  const busy = confirm.isPending || reopen.isPending || cancel.isPending

  if (card.state === "done_pending_confirm") {
    return (
      <div className="mt-2 flex items-center gap-2">
        <span className="text-muted-foreground text-xs">Is this resolved?</span>
        <Button
          size="xs"
          variant="ghost"
          disabled={busy}
          onClick={() => confirm.mutate(card.child_id)}
        >
          Yes, all set
        </Button>
        <Button
          size="xs"
          variant="ghost"
          disabled={busy}
          onClick={() => reopen.mutate(card.child_id)}
        >
          Not yet
        </Button>
      </div>
    )
  }

  const terminal =
    card.state === "closed" ||
    card.state === "cancelled" ||
    card.state === "reopened"
  if (terminal) return null

  return (
    <div className="mt-2 flex items-center gap-2">
      <Button
        size="xs"
        variant="ghost"
        disabled={busy}
        onClick={() => cancel.mutate(card.child_id)}
      >
        Cancel request
      </Button>
    </div>
  )
}

function DispatchStatusCard({ card }: { card: DispatchCard }) {
  const label = STATE_LABEL[card.state] ?? card.state
  return (
    <div className="bg-muted text-foreground rounded-lg px-3 py-2 text-sm">
      <div className="flex items-center gap-2">
        <Badge variant="outline">{label}</Badge>
        {card.glitch && (
          // An open Glitch — a calm flag, not an alarm (monochrome token).
          <Badge variant="secondary">Needs attention</Badge>
        )}
      </div>
      {card.issue_label && (
        <p className="mt-1.5 font-medium">{card.issue_label}</p>
      )}
      {card.assigned_servicer_name && (
        // D17 — the NAME, never the id.
        <p className="text-muted-foreground mt-1 text-xs">
          {card.assigned_servicer_name} is helping
        </p>
      )}
      {card.revised_eta && (
        // D22 — the revised ETA, ticking against the server deadline (AD5)
        // via the F1 countdown.
        <p className="text-muted-foreground mt-1 flex items-center gap-1 text-xs">
          <span>Updated ETA</span>
          <Countdown deadline={card.revised_eta} />
        </p>
      )}
      <DispatchClosure card={card} />
    </div>
  )
}
