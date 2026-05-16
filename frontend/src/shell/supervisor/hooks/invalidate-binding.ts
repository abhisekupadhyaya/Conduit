// src/shell/supervisor/hooks/invalidate-binding.ts
import type { QueryClient } from "@tanstack/react-query"
export function invalidateBinding(
  qc: QueryClient, keys: Array<"sections" | "rooms" | "stays">,
) { for (const k of keys) qc.invalidateQueries({ queryKey: [k] }) }
