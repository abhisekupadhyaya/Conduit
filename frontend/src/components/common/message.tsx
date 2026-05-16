import type { ReactNode } from "react"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"

// One conversation bubble. Guest messages are right-aligned and filled;
// system messages are left-aligned and quiet. The single "C" mark sits on
// the first bubble of a system group only (set `mark` on the first, omit
// it on the rest) so a multi-part reply reads as one voice.
export function Message({
  from,
  mark = true,
  children,
}: {
  from: "guest" | "system"
  mark?: boolean
  children: ReactNode
}) {
  const isGuest = from === "guest"
  return (
    <div
      className={cn(
        "flex items-end gap-2",
        isGuest ? "flex-row-reverse" : "flex-row"
      )}
    >
      {!isGuest && (
        <div className="w-6 shrink-0">
          {mark && (
            <Avatar size="sm">
              <AvatarFallback className="text-[0.65rem] font-medium">
                C
              </AvatarFallback>
            </Avatar>
          )}
        </div>
      )}
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-3 py-2 text-sm",
          isGuest
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        )}
      >
        {children}
      </div>
    </div>
  )
}
