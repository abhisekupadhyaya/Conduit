import { useState } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import {
  useGuestThread,
  useSubmitRequest,
  useConfirmChild,
} from "@/shell/guest/hooks/use-guest"

// The conversation IS the portal: ask + status + confirm.
// All data flows through TanStack Query (auth is the only direct exception).
export function GuestConversation() {
  const [text, setText] = useState("")
  const thread = useGuestThread()
  const submit = useSubmitRequest()
  const confirm = useConfirmChild()

  const children = thread.data?.children ?? []

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex-1 space-y-2 overflow-y-auto py-2">
        {thread.isLoading && (
          <p className="text-muted-foreground text-center text-sm">Loading…</p>
        )}
        {thread.isError && (
          <p className="text-destructive text-center text-sm">
            Couldn’t load your requests. Retrying…
          </p>
        )}
        {!thread.isLoading && !thread.isError && children.length === 0 && (
          <p className="text-muted-foreground text-center text-sm">
            Ask for anything — in plain words. Room and stay are already known.
          </p>
        )}
        {children.map((c) => (
          <div
            key={c.id}
            className="bg-card text-card-foreground flex items-center justify-between rounded-xl border p-3"
          >
            <div>
              <div className="text-sm font-medium">{c.title}</div>
              <div className="text-muted-foreground text-xs">
                {c.state}
                {c.servicer ? ` · ${c.servicer}` : ""}
                {c.revisedEta ? ` · ETA ${c.revisedEta}` : ""}
              </div>
            </div>
            {c.state === "done_pending_confirm" && (
              <Button
                size="sm"
                variant="outline"
                disabled={confirm.isPending}
                onClick={() => confirm.mutate(c.id)}
              >
                Confirm
              </Button>
            )}
          </div>
        ))}
      </div>
      <form
        className="flex gap-2 pt-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (!text.trim()) return
          submit.mutate(text, { onSuccess: () => setText("") })
        }}
      >
        <Input
          placeholder="e.g. can I get 2 extra bath towels"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button type="submit" disabled={submit.isPending}>
          {submit.isPending ? "Sending…" : "Send"}
        </Button>
      </form>
    </div>
  )
}
