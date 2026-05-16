import { useLayoutEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

// Mobile-first message composer. Auto-grows 1→5 rows, Enter sends /
// Shift+Enter newlines, ≥16px font (no iOS zoom), 44px touch target, and
// it sticks to the bottom respecting the safe-area inset.
export function Composer({
  onSend,
  pending,
}: {
  onSend: (text: string) => void
  pending: boolean
}) {
  const [text, setText] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    const lineHeight = 24
    const maxH = lineHeight * 5
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`
    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden"
  }, [text])

  function send() {
    const v = text.trim()
    if (!v || pending) return
    onSend(v)
    setText("")
  }

  return (
    <div
      className="bg-background sticky bottom-0 flex items-end gap-2 border-t pt-3"
      style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
    >
      <Textarea
        ref={ref}
        rows={1}
        value={text}
        placeholder="Ask for anything — in plain words."
        className="max-h-[7.5rem] min-h-11 resize-none text-base"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault()
            send()
          }
        }}
      />
      <Button
        size="lg"
        className="h-11"
        disabled={pending || !text.trim()}
        onClick={send}
      >
        {pending ? "Sending…" : "Send"}
      </Button>
    </div>
  )
}
