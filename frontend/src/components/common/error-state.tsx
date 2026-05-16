import { Button } from "@/components/ui/button"

export function ErrorState({
  title = "Something went wrong", onRetry,
}: { title?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
      )}
    </div>
  )
}
