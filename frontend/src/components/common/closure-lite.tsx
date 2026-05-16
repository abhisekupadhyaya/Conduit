import { Button } from "@/components/ui/button"
import { useConfirmChild } from "@/shell/guest/hooks/use-conversation"

// The guest has the final word on closure (D8). Two ghost buttons, no
// modal — a light touch after an answer: did this help?
export function ClosureLite({ childId }: { childId: string }) {
  const confirm = useConfirmChild()
  return (
    <div className="mt-2 flex items-center gap-2">
      <span className="text-muted-foreground text-xs">Did this help?</span>
      <Button
        size="xs"
        variant="ghost"
        disabled={confirm.isPending}
        onClick={() => confirm.mutate({ id: childId, helpful: true })}
      >
        Yes
      </Button>
      <Button
        size="xs"
        variant="ghost"
        disabled={confirm.isPending}
        onClick={() => confirm.mutate({ id: childId, helpful: false })}
      >
        No
      </Button>
    </div>
  )
}
