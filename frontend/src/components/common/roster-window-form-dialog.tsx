import { useState } from "react"
import { useForm, Controller } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { DateRangeField } from "@/components/common/date-range-field"
import { toast } from "sonner"

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
          <div className="space-y-1.5">
            <Label>shift window</Label>
            <Controller
              control={control}
              name="shift_start"
              render={({ field: start }) => (
                <Controller
                  control={control}
                  name="shift_end"
                  render={({ field: end }) => (
                    <DateRangeField
                      value={{ from: start.value, to: end.value }}
                      onChange={(r) => {
                        start.onChange(r.from)
                        end.onChange(r.to)
                      }}
                    />
                  )}
                />
              )}
            />
            {errors.shift_end && (
              <p className="text-destructive text-xs">
                {errors.shift_end.message}
              </p>
            )}
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
