import { useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { MoreHorizontalIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { StatusBadge } from "@/components/common/status-badge"
import { Confirm } from "@/components/common/confirm"
import { AccountFormDialog } from "@/components/common/account-form-dialog"
import {
  useAccounts, useUpdateAccount, type Account,
} from "@/shell/supervisor/hooks/use-accounts"

export function ManageAccounts({ role, label }: { role: string; label: string }) {
  const q = useAccounts(role)
  const upd = useUpdateAccount()
  const [confirm, setConfirm] = useState<Account | null>(null)

  const state = q.isLoading ? "loading" : q.isError ? "error"
    : (q.data?.length ?? 0) === 0 ? "empty" : "ready"

  async function toggle(a: Account) {
    const next = a.status === "active" ? "disabled" : "active"
    try {
      await upd.mutateAsync({ id: a.id, status: next })
      toast.success(`${a.display_name} ${next}`)
    } catch (e: any) {
      toast.error(e?.status === 409
        ? "Cannot disable the last supervisor or yourself"
        : "Update failed")
    }
  }

  const rows = (a: Account) => (
    <DropdownMenu key={a.id}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 sm:size-9">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setConfirm(a)}>
          {a.status === "active" ? "Disable" : "Enable"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div>
      <PageHeader
        title={`${label}s`}
        description={`${q.data?.length ?? 0} account(s)`}
        actions={<AccountFormDialog role={role} label={label} />}
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle={`No ${label.toLowerCase()}s yet`}
        emptyHint={`Add the first ${label.toLowerCase()}.`}
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead><TableHead>Username</TableHead>
                <TableHead>Status</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data?.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">{a.display_name}</TableCell>
                  <TableCell className="text-muted-foreground">{a.username}</TableCell>
                  <TableCell><StatusBadge status={a.status} /></TableCell>
                  <TableCell className="text-right">{rows(a)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={q.data?.map((a) => (
          <div key={a.id}
               className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <div className="text-sm font-medium">{a.display_name}</div>
              <div className="text-muted-foreground text-xs">{a.username}</div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge status={a.status} />{rows(a)}
            </div>
          </div>
        ))}
      />
      <Confirm
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm?.status === "active" ? "Disable account?" : "Enable account?"}
        description={confirm?.display_name}
        confirmLabel={confirm?.status === "active" ? "Disable" : "Enable"}
        onConfirm={() => { if (confirm) toggle(confirm); setConfirm(null) }}
      />
    </div>
  )
}
