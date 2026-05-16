import { useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Button } from "@/components/ui/button"
import { MoreHorizontalIcon, ChevronDownIcon } from "lucide-react"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { StatusBadge } from "@/components/common/status-badge"
import { Confirm } from "@/components/common/confirm"
import { KbEntryFormDialog } from "@/components/common/kb-entry-form-dialog"
import {
  useKB, useUpdateKBEntry, type KBEntry,
} from "@/shell/supervisor/hooks/use-kb"

function ContentCell({ content }: { content: string }) {
  const [open, setOpen] = useState(false)
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="flex items-start gap-1.5">
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="icon" className="size-6 shrink-0">
            <ChevronDownIcon
              className={"size-3.5 transition-transform " + (open ? "rotate-180" : "")} />
          </Button>
        </CollapsibleTrigger>
        <div className="min-w-0">
          {!open && (
            <span className="text-muted-foreground line-clamp-1">{content}</span>
          )}
          <CollapsibleContent>
            <span className="text-muted-foreground whitespace-pre-wrap">{content}</span>
          </CollapsibleContent>
        </div>
      </div>
    </Collapsible>
  )
}

export function KnowledgeBasePage() {
  const q = useKB()
  const upd = useUpdateKBEntry()
  const [confirm, setConfirm] = useState<KBEntry | null>(null)

  const state = q.isLoading ? "loading" : q.isError ? "error"
    : (q.data?.length ?? 0) === 0 ? "empty" : "ready"

  async function toggle(e: KBEntry) {
    const next = e.status === "active" ? "disabled" : "active"
    try {
      await upd.mutateAsync({ id: e.id, status: next })
      toast.success(`${e.topic} ${next}`)
    } catch {
      toast.error("Update failed")
    }
  }

  const actions = (e: KBEntry) => (
    <DropdownMenu key={e.id}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-11 sm:size-9">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <div><KbEntryFormDialog edit={e} /></div>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setConfirm(e)}>
          {e.status === "active" ? "Disable" : "Enable"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div>
      <PageHeader
        title="Knowledge Base"
        description={`${q.data?.length ?? 0} entry(ies)`}
        actions={<KbEntryFormDialog />}
      />
      <DataTableShell
        state={state}
        onRetry={q.refetch}
        emptyTitle="No entries yet"
        emptyHint="Create the first knowledge-base entry."
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[16rem]">Topic</TableHead>
                <TableHead>Content</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data?.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-medium align-top">{e.topic}</TableCell>
                  <TableCell className="align-top max-w-0">
                    <ContentCell content={e.content} />
                  </TableCell>
                  <TableCell className="align-top"><StatusBadge status={e.status} /></TableCell>
                  <TableCell className="text-right align-top">{actions(e)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={q.data?.map((e) => (
          <div key={e.id}
               className="space-y-2 rounded-lg border p-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium">{e.topic}</div>
              <div className="flex items-center gap-2">
                <StatusBadge status={e.status} />{actions(e)}
              </div>
            </div>
            <ContentCell content={e.content} />
          </div>
        ))}
      />
      <Confirm
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm?.status === "active" ? "Disable entry?" : "Enable entry?"}
        description={confirm?.topic}
        confirmLabel={confirm?.status === "active" ? "Disable" : "Enable"}
        onConfirm={() => { if (confirm) toggle(confirm); setConfirm(null) }}
      />
    </div>
  )
}
