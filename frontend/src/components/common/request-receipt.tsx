import { StatusBadge } from "@/components/common/status-badge"
import type { Child } from "@/shell/guest/hooks/use-conversation"

// D36 split-echo: when one ask decomposed into more than one thing, show a
// calm "Logged N things:" receipt listing each part — per child the
// server-decided issue_label (echoed text as fallback) and a live monochrome
// StatusBadge chip. A single child needs no receipt — the status card alone
// tells the story. Gate on `split` (server-decided): the existing ≤1
// early-return is the equivalent gate by construction (split === children
// ≥ 2), kept so the existing caller — which passes only `children` — is
// unchanged. Spec §10: one calm, capped, monochrome moment — no alarm.
export function RequestReceipt({
  children,
  split,
}: {
  children: Child[]
  split?: boolean
}) {
  if (split === false) return null
  if (children.length <= 1) return null
  return (
    <div className="bg-muted text-foreground rounded-lg px-3 py-2 text-sm">
      <p className="text-muted-foreground text-xs font-medium">
        Logged {children.length} things:
      </p>
      <ul className="mt-1 space-y-1">
        {children.map((c) => (
          <li
            key={c.child_id}
            className="flex items-start justify-between gap-2 text-sm"
          >
            <span>
              · {c.issue_label?.trim() || c.text}
            </span>
            <StatusBadge status={c.outcome || c.state || c.terminal} />
          </li>
        ))}
      </ul>
    </div>
  )
}
