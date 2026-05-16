import { Badge } from "@/components/ui/badge"

export function RoleBadge({ role }: { role: string }) {
  return <Badge variant="secondary">{role.replace("_", " ")}</Badge>
}
