import { useEffect, useRef, type ReactNode } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"

// Scrollable conversation column that pins to the bottom whenever its
// content grows (new message / instant-ack / status change).
export function ChatScroll({
  children,
  className,
  pinKey,
}: {
  children: ReactNode
  className?: string
  // Change this to re-pin (e.g. message count + pending flag).
  pinKey?: unknown
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const viewport = containerRef.current?.querySelector<HTMLElement>(
      '[data-slot="scroll-area-viewport"]'
    )
    if (!viewport) return
    viewport.scrollTop = viewport.scrollHeight
  }, [pinKey])

  return (
    <ScrollArea ref={containerRef} className={cn("flex-1", className)}>
      <div className="flex flex-col gap-3 py-2">{children}</div>
    </ScrollArea>
  )
}
