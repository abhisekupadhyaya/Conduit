import { Badge } from "@/components/ui/badge"

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={status === "active" ? "default" : "outline"}>
      {status}
    </Badge>
  )
}
