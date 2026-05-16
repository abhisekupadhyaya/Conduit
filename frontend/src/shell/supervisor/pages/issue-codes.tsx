import { useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip"
import { Button } from "@/components/ui/button"
import { MoreHorizontalIcon, LockIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { StatusBadge } from "@/components/common/status-badge"
import { Confirm } from "@/components/common/confirm"
import { IssueCodeFormDialog } from "@/components/common/issue-code-form-dialog"
import {
  useIssueCodes, useUpdateIssueCode, type IssueCode,
} from "@/shell/supervisor/hooks/use-issue-codes"

function MutationCell({ on }: { on: boolean }) {
  if (!on) return <span className="text-muted-foreground">—</span>
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <LockIcon className="text-muted-foreground size-3.5" />
        </TooltipTrigger>
        <TooltipContent>
          System-owned — governs the always-flag policy, D24
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

export function IssueCodesPage() {
  const q = useIssueCodes()
  const upd = useUpdateIssueCode()
  const [confirm, setConfirm] = useState<IssueCode | null>(null)

  const state = q.isLoading ? "loading" : q.isError ? "error"
    : (q.data?.length ?? 0) === 0 ? "empty" : "ready"

  async function toggle(c: IssueCode) {
    const next = c.status === "active" ? "disabled" : "active"
    try {
      await upd.mutateAsync({ id: c.id, status: next })
      toast.success(`${c.code} ${next}`)
    } catch {
      toast.error("Update failed")
    }
  }

  const actions = (c: IssueCode) => (
    <DropdownMenu key={c.id}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 sm:size-9">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <div><IssueCodeFormDialog edit={c} /></div>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setConfirm(c)}>
          {c.status === "active" ? "Disable" : "Enable"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div>
      <PageHeader
        title="Issue Codes"
        description={`${q.data?.length ?? 0} code(s)`}
        actions={<IssueCodeFormDialog />}
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No issue codes yet"
        emptyHint="Create the first issue code."
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Label</TableHead>
                <TableHead>Department</TableHead>
                <TableHead>Mode</TableHead>
                <TableHead>Intent</TableHead>
                <TableHead>Mutation</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data?.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-mono tabular-nums">{c.code}</TableCell>
                  <TableCell className="font-medium">{c.label}</TableCell>
                  <TableCell className="text-muted-foreground">{c.department}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {c.fulfilment_mode.replace(/_/g, " ")}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {c.intent_kind.replace(/_/g, " ")}
                  </TableCell>
                  <TableCell><MutationCell on={c.is_reservation_mutation} /></TableCell>
                  <TableCell><StatusBadge status={c.status} /></TableCell>
                  <TableCell className="text-right">{actions(c)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={q.data?.map((c) => (
          <div key={c.id}
               className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2 text-sm font-medium">
                <span className="font-mono tabular-nums">{c.code}</span>
                {c.label}
                <MutationCell on={c.is_reservation_mutation} />
              </div>
              <div className="text-muted-foreground text-xs">
                {c.department} · {c.fulfilment_mode.replace(/_/g, " ")} · {c.intent_kind.replace(/_/g, " ")}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={c.status} />{actions(c)}
            </div>
          </div>
        ))}
      />
      <Confirm
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm?.status === "active" ? "Disable issue code?" : "Enable issue code?"}
        description={confirm?.label}
        confirmLabel={confirm?.status === "active" ? "Disable" : "Enable"}
        onConfirm={() => { if (confirm) toggle(confirm); setConfirm(null) }}
      />
    </div>
  )
}
