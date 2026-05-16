// src/shell/supervisor/pages/sections.tsx
import { useState } from "react"
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { PageHeader } from "@/components/layout/page-header"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import {
  useSections, useCreateSection, useRenameSection,
} from "@/shell/supervisor/hooks/use-sections"
import { useRooms, useCreateRoom } from "@/shell/supervisor/hooks/use-rooms"

function Rooms({ sectionId }: { sectionId: string }) {
  const rooms = useRooms(sectionId)
  const create = useCreateRoom()
  const [label, setLabel] = useState("")
  if (rooms.isLoading) return <Skeleton className="h-8 w-full" />
  if (rooms.isError) return <ErrorState onRetry={rooms.refetch} />
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {(rooms.data ?? []).map((r) => (
          <span key={r.id}
            className="rounded-md border px-2 py-1 text-xs font-medium">
            {r.label}
          </span>
        ))}
        {rooms.data?.length === 0 && (
          <span className="text-muted-foreground text-xs">No rooms yet.</span>
        )}
      </div>
      <form className="flex gap-2" onSubmit={(e) => {
        e.preventDefault()
        if (label.trim())
          create.mutate({ label: label.trim(), section_id: sectionId },
            { onSuccess: () => setLabel("") })
      }}>
        <Input value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder="Add room (e.g. 304)" className="h-9 max-w-[12rem]" />
        <Button type="submit" size="sm" disabled={create.isPending}>
          {create.isPending ? "Adding…" : "Add room"}
        </Button>
      </form>
    </div>
  )
}

function SectionLabel({ id, label }: { id: string; label: string }) {
  const rename = useRenameSection()
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(label)
  if (!editing)
    return (
      <span className="font-medium"
        onClick={(e) => { e.stopPropagation(); setEditing(true) }}>
        {label}
      </span>
    )
  return (
    <Input autoFocus value={val} className="h-7 max-w-[14rem]"
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setVal(e.target.value)}
      onBlur={() => {
        setEditing(false)
        if (val.trim() && val !== label)
          rename.mutate({ id, label: val.trim() })
      }} />
  )
}

export function SectionsPage() {
  const sections = useSections()
  const create = useCreateSection()
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState("")
  const total = sections.data?.length ?? 0
  const rooms = (sections.data ?? []).reduce((n, s) => n + s.room_count, 0)
  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader title="Sections"
        description={`${total} sections · ${rooms} rooms`}
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild><Button>New section</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New section</DialogTitle>
              </DialogHeader>
              <Input value={label} onChange={(e) => setLabel(e.target.value)}
                placeholder="Section label (e.g. North Wing)" />
              <DialogFooter>
                <Button disabled={create.isPending || !label.trim()}
                  onClick={() => create.mutate(label.trim(), {
                    onSuccess: () => { setLabel(""); setOpen(false) },
                  })}>
                  {create.isPending ? "Creating…" : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        } />
      {sections.isLoading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
        </div>
      )}
      {sections.isError && <ErrorState onRetry={sections.refetch} />}
      {sections.data?.length === 0 && (
        <EmptyState title="No sections yet"
          hint="Create a section to start mapping rooms." />
      )}
      {!!sections.data?.length && (
        <Accordion type="multiple" className="w-full">
          {sections.data.map((s) => (
            <AccordionItem key={s.id} value={s.id}>
              <AccordionTrigger className="text-sm">
                <span className="flex w-full items-center justify-between pr-3">
                  <SectionLabel id={s.id} label={s.label} />
                  <span className="text-muted-foreground text-xs">
                    {s.room_count} rooms
                  </span>
                </span>
              </AccordionTrigger>
              <AccordionContent>
                <Rooms sectionId={s.id} />
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      )}
    </div>
  )
}
