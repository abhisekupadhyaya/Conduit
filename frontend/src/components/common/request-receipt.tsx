import type { Child } from "@/shell/guest/hooks/use-conversation"

// D36 split-echo: when one ask decomposed into more than one thing, show a
// calm "Logged N things:" receipt listing each part. A single child needs no
// receipt — the status card alone tells the story.
export function RequestReceipt({ children }: { children: Child[] }) {
  if (children.length <= 1) return null
  return (
    <div className="bg-muted text-foreground rounded-lg px-3 py-2 text-sm">
      <p className="text-muted-foreground text-xs font-medium">
        Logged {children.length} things:
      </p>
      <ul className="mt-1 space-y-0.5">
        {children.map((c) => (
          <li key={c.child_id} className="text-sm">
            · {c.text}
          </li>
        ))}
      </ul>
    </div>
  )
}
