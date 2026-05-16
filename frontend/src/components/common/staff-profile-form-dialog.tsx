import { useState } from "react"
import { useForm, Controller } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { toast } from "sonner"

// Backend contract (supervisor/schemas/staff.py): create = POST profile
// {staff_class}; edit = PATCH {staff_class?,status?}. Hooks are wired by a
// later task — this dialog takes the create/patch callbacks as props.
const STAFF_CLASSES = [
  "housekeeping", "engineering", "room_service", "concierge", "runner",
] as const

const schema = z.object({
  staff_class: z.enum(STAFF_CLASSES),
})
type Form = z.infer<typeof schema>

export type StaffProfileEdit = {
  account_id: string
  display_name: string
  staff_class: string
  status: string
}

export function StaffProfileFormDialog({
  edit, accountId, displayName, onCreate, onPatch,
}: {
  // Edit path: an existing profile on a servicer account.
  edit?: StaffProfileEdit
  // Create path: the un-profiled servicer account ("provisioned, not yet
  // profiled" — a first-class state, spec §8).
  accountId?: string
  displayName?: string
  onCreate?: (v: { account_id: string; staff_class: string }) => Promise<unknown>
  onPatch?: (v: {
    account_id: string; staff_class?: string; status?: string
  }) => Promise<unknown>
}) {
  const [open, setOpen] = useState(false)
  const isEdit = !!edit
  const acct = edit?.account_id ?? accountId
  const name = edit?.display_name ?? displayName
  const { handleSubmit, reset, control,
    formState: { isSubmitting } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: edit
      ? { staff_class: edit.staff_class as Form["staff_class"] }
      : { staff_class: "housekeeping" },
  })

  async function onSubmit(v: Form) {
    if (!acct) return
    try {
      if (isEdit) {
        await onPatch?.({ account_id: acct, staff_class: v.staff_class })
        toast.success("Profile updated")
      } else {
        await onCreate?.({ account_id: acct, staff_class: v.staff_class })
        toast.success("Profile created")
      }
      reset(); setOpen(false)
    } catch (e: any) {
      toast.error(
        e?.status === 409 ? "Profile already exists"
          : e?.status === 422 ? "Account is not a servicer"
            : "Could not save profile"
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {isEdit
          ? <Button variant="ghost" size="sm" className="w-full justify-start font-normal">Edit profile</Button>
          : <Button size="sm">Create profile</Button>}
      </DialogTrigger>
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit staff profile" : "Create staff profile"}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          {name && (
            <div className="space-y-1.5">
              <Label>servicer</Label>
              <p className="text-sm font-medium">{name}</p>
            </div>
          )}
          <div className="space-y-1.5">
            <Label>staff class</Label>
            <Controller
              control={control}
              name="staff_class"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STAFF_CLASSES.map((opt) => (
                      <SelectItem key={opt} value={opt}>
                        {opt.replace(/_/g, " ")}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting
              ? "Saving…"
              : isEdit ? "Save changes" : "Create profile"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
