// src/shell/supervisor/pages/provisioning.tsx
import { useMemo, useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { DataTableShell } from "@/components/common/data-table-shell"
import { Confirm } from "@/components/common/confirm"
import { ComboboxField } from "@/components/common/combobox-field"
import {
  DateRangeField, type DateRange,
} from "@/components/common/date-range-field"
import {
  useStays, useCreateStay, useRelocateStay, useCheckoutStay, type Stay,
} from "@/shell/supervisor/hooks/use-stays"
import { useRooms } from "@/shell/supervisor/hooks/use-rooms"
import { useAccounts } from "@/shell/supervisor/hooks/use-accounts"

export function ProvisioningPage() {
  const [status, setStatus] = useState<"active" | "ended" | "">("active")
  const list = useStays(status || undefined)
  const activeList = useStays("active")           // top-level, once
  const rooms = useRooms()
  const guests = useAccounts("guest")
  const createStay = useCreateStay()
  const relocate = useRelocateStay()
  const checkout = useCheckoutStay()
  const [open, setOpen] = useState(false)
  const [confirmStay, setConfirmStay] = useState<Stay | null>(null)

  const activeGuestIds = useMemo(
    () => new Set((activeList.data ?? []).map((s) => s.guest_account_id)),
    [activeList.data])
  const guestOptions = (guests.data ?? [])
    .filter((g) => !activeGuestIds.has(g.id))
    .map((g) => ({ value: g.id, label: g.display_name }))
  const roomOptions = (rooms.data ?? []).map(
    (r) => ({ value: r.id, label: `${r.label} · ${r.section_label}` }))

  const state = list.isLoading ? "loading" : list.isError ? "error"
    : (list.data?.length ?? 0) === 0 ? "empty" : "ready"

  const actions = (st: Stay) =>
    st.status === "active" ? (
      <RowActions
        roomOptions={roomOptions.filter((o) => o.value !== st.room_id)}
        current={`${st.room_label} · ${st.section_label}`}
        onMove={(rid) => relocate.mutate({ id: st.id, new_room_id: rid },
          { onSuccess: () => toast.success("Guest moved") })}
        onCheckout={() => setConfirmStay(st)} />
    ) : <span className="text-muted-foreground text-xs">ended</span>

  return (
    <div className="mx-auto w-full max-w-6xl">
      <PageHeader title="Provisioning"
        description={`${list.data?.length ?? 0} ${status || "all"} stays`}
        actions={
          <CheckInDialog open={open} setOpen={setOpen}
            guestOptions={guestOptions} roomOptions={roomOptions}
            pending={createStay.isPending}
            onCreate={(v) => createStay.mutate(v, {
              onSuccess: () => { setOpen(false); toast.success("Checked in") },
            })} />
        } />
      <DataTableShell
        state={state} onRetry={list.refetch}
        emptyTitle="No stays" emptyHint="Check in a guest to begin."
        toolbar={
          <div className="flex gap-2">
            {(["active", "ended", ""] as const).map((sv) => (
              <Button key={sv || "all"} size="sm"
                variant={status === sv ? "default" : "outline"}
                onClick={() => setStatus(sv)}>
                {sv === "" ? "All" : sv[0].toUpperCase() + sv.slice(1)}
              </Button>
            ))}
          </div>
        }
        table={
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Guest</TableHead><TableHead>Room</TableHead>
                <TableHead>Section</TableHead><TableHead>Dates</TableHead>
                <TableHead>Status</TableHead><TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data?.map((st) => (
                <TableRow key={st.id}>
                  <TableCell className="font-medium">
                    {st.guest_display_name}</TableCell>
                  <TableCell>{st.room_label}</TableCell>
                  <TableCell>{st.section_label}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {st.check_in.slice(0, 10)} → {st.check_out.slice(0, 10)}
                  </TableCell>
                  <TableCell>
                    <span className="flex items-center gap-1 text-xs">
                      <span className={st.status === "active"
                        ? "text-foreground" : "text-muted-foreground"}>
                        ●</span>{st.status}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">{actions(st)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        }
        cards={list.data?.map((st) => (
          <div key={st.id}
            className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <div className="text-sm font-medium">
                {st.guest_display_name}</div>
              <div className="text-muted-foreground text-xs">
                {st.room_label} · {st.section_label}
              </div>
            </div>
            {actions(st)}
          </div>
        ))} />
      <Confirm
        open={confirmStay !== null}
        onOpenChange={(o) => !o && setConfirmStay(null)}
        title="Check out?"
        description={confirmStay?.guest_display_name}
        confirmLabel="Check out"
        onConfirm={() => {
          if (confirmStay)
            checkout.mutate(confirmStay.id,
              { onSuccess: () => toast.success("Checked out") })
          setConfirmStay(null)
        }} />
    </div>
  )
}

function CheckInDialog({
  open, setOpen, guestOptions, roomOptions, onCreate, pending,
}: {
  open: boolean; setOpen: (b: boolean) => void
  guestOptions: { value: string; label: string }[]
  roomOptions: { value: string; label: string }[]
  onCreate: (v: { guest_account_id: string; room_id: string
    check_in: string; check_out: string }) => void
  pending: boolean
}) {
  const [guest, setGuest] = useState<string | null>(null)
  const [room, setRoom] = useState<string | null>(null)
  const [range, setRange] = useState<DateRange>({})
  const valid = guest && room && range.from && range.to
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button>Check in guest</Button></DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Check in guest</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <ComboboxField options={guestOptions} value={guest}
            onChange={setGuest} placeholder="Select guest"
            emptyText="No guests without an active stay" />
          <ComboboxField options={roomOptions} value={room}
            onChange={setRoom} placeholder="Select room" />
          <DateRangeField value={range} onChange={setRange} />
        </div>
        <DialogFooter>
          <Button disabled={!valid || pending} onClick={() => onCreate({
            guest_account_id: guest!, room_id: room!,
            check_in: range.from!.toISOString(),
            check_out: range.to!.toISOString(),
          })}>{pending ? "Checking in…" : "Check in"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RowActions({
  roomOptions, current, onMove, onCheckout,
}: {
  roomOptions: { value: string; label: string }[]
  current: string
  onMove: (roomId: string) => void
  onCheckout: () => void
}) {
  const [moveOpen, setMoveOpen] = useState(false)
  const [target, setTarget] = useState<string | null>(null)
  return (
    <div className="flex justify-end gap-2">
      <Dialog open={moveOpen} onOpenChange={setMoveOpen}>
        <DialogTrigger asChild>
          <Button size="sm" variant="outline">Move</Button>
        </DialogTrigger>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Move guest</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <div className="text-muted-foreground">
              {current} <span className="px-1">▶</span> new room
            </div>
            <ComboboxField options={roomOptions} value={target}
              onChange={setTarget} placeholder="Select new room" />
            <p className="text-muted-foreground text-xs">
              Re-binds the guest's room immediately. They see it on next
              refresh — no re-login.
            </p>
          </div>
          <DialogFooter>
            <Button disabled={!target} onClick={() => {
              onMove(target!); setMoveOpen(false)
            }}>Move</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Button size="sm" variant="ghost" onClick={onCheckout}>Check out</Button>
    </div>
  )
}
