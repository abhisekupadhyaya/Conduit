import type { Child } from "@/shell/guest/hooks/use-conversation"
import { ClosureLite } from "@/components/common/closure-lite"

// The terminal state of one decomposed thing.
//  - answered: the grounded answer, then a light closure prompt (D8) while
//    the child is still awaiting confirmation.
//  - logged: a calm, muted line — a human has it, nothing for the guest to do.
export function ChildStatusCard({ child }: { child: Child }) {
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
