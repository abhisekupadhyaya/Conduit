import { useState } from "react"
import { useForm, Controller } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { toast } from "sonner"

// A roster is a SHIFT (e.g. 08:00–16:00), not a date span — date-only was
// the original defect. datetime-local is wall-clock (no tz): format a Date
// to its YYYY-MM-DDTHH:mm local representation for the input; new Date(value)
// parses it back as local time; submit still .toISOString()s to UTC for the
// API, so the backend contract is unchanged.
const pad = (n: number) => String(n).padStart(2, "0")
const toLocalInput = (d?: Date) =>
  d
    ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}`
    : ""

// Backend contract (supervisor/schemas/roster.py): create = POST
// {shift_start,shift_end}; edit = PATCH {shift_start?,shift_end?,status?}.
// The server rejects shift_end <= shift_start with 422 — the zod refine
// below mirrors that exactly so the client never round-trips a bad window.
const schema = z
  .object({
    shift_start: z.date(),
    shift_end: z.date(),
  })
  .refine((v) => v.shift_end > v.shift_start, {
    message: "Shift end must be after shift start",
    path: ["shift_end"],
  })
type Form = z.infer<typeof schema>

export type RosterWindowEdit = {
  id: string
  shift_start: string
  shift_end: string
}

export function RosterWindowFormDialog({
  edit, onCreate, onPatch,
}: {
  edit?: RosterWindowEdit
  onCreate?: (v: {
    shift_start: string; shift_end: string
  }) => Promise<unknown>
  onPatch?: (v: {
    id: string; shift_start?: string; shift_end?: string
  }) => Promise<unknown>
}) {
  const [open, setOpen] = useState(false)
  const isEdit = !!edit
  const { handleSubmit, reset, control,
    formState: { errors, isSubmitting } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: edit
      ? {
          shift_start: new Date(edit.shift_start),
          shift_end: new Date(edit.shift_end),
        }
      : {},
  })

  async function onSubmit(v: Form) {
    try {
      if (isEdit) {
        await onPatch?.({
          id: edit.id,
          shift_start: v.shift_start.toISOString(),
          shift_end: v.shift_end.toISOString(),
        })
        toast.success("Roster window updated")
      } else {
        await onCreate?.({
          shift_start: v.shift_start.toISOString(),
          shift_end: v.shift_end.toISOString(),
        })
        toast.success("Roster window created")
      }
      reset(); setOpen(false)
    } catch (e: any) {
      toast.error(
        e?.status === 422 ? "Shift end must be after shift start"
          : "Could not save roster window"
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {isEdit
          ? <Button variant="ghost" size="sm" className="w-full justify-start font-normal">Edit window</Button>
          : <Button size="sm">New roster window</Button>}
      </DialogTrigger>
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit roster window" : "New roster window"}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="shift_start">shift start</Label>
              <Controller
                control={control}
                name="shift_start"
                render={({ field }) => (
                  <Input
                    id="shift_start"
                    type="datetime-local"
                    value={toLocalInput(field.value)}
                    onChange={(e) =>
                      field.onChange(
                        e.target.value ? new Date(e.target.value) : undefined
                      )
                    }
                  />
                )}
              />
              {errors.shift_start && (
                <p className="text-destructive text-xs">
                  {errors.shift_start.message}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="shift_end">shift end</Label>
              <Controller
                control={control}
                name="shift_end"
                render={({ field }) => (
                  <Input
                    id="shift_end"
                    type="datetime-local"
                    value={toLocalInput(field.value)}
                    onChange={(e) =>
                      field.onChange(
                        e.target.value ? new Date(e.target.value) : undefined
                      )
                    }
                  />
                )}
              />
              {errors.shift_end && (
                <p className="text-destructive text-xs">
                  {errors.shift_end.message}
                </p>
              )}
            </div>
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting
              ? "Saving…"
              : isEdit ? "Save changes" : "Create window"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
