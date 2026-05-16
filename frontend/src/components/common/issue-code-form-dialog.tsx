import { useState } from "react"
import { useForm, Controller } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { LockIcon } from "lucide-react"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip"
import { toast } from "sonner"
import {
  useCreateIssueCode, useUpdateIssueCode, type IssueCode,
} from "@/shell/supervisor/hooks/use-issue-codes"

const schema = z.object({
  code: z.string().min(1),
  label: z.string().min(1),
  department: z.string().min(1),
  fulfilment_mode: z.enum(["dispatch", "no_dispatch"]),
  routing_model: z.enum(["section_pooled", "skill_matched", "none"]),
  intent_kind: z.enum(["service", "problem_report"]),
})
type Form = z.infer<typeof schema>

const ENUMS = {
  fulfilment_mode: ["dispatch", "no_dispatch"],
  routing_model: ["section_pooled", "skill_matched", "none"],
  intent_kind: ["service", "problem_report"],
} as const

export function IssueCodeFormDialog({ edit }: { edit?: IssueCode }) {
  const [open, setOpen] = useState(false)
  const create = useCreateIssueCode()
  const update = useUpdateIssueCode()
  const isEdit = !!edit
  const { register, handleSubmit, reset, control,
    formState: { errors, isSubmitting } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: edit
      ? {
          code: edit.code, label: edit.label, department: edit.department,
          fulfilment_mode: edit.fulfilment_mode,
          routing_model: edit.routing_model, intent_kind: edit.intent_kind,
        }
      : { fulfilment_mode: "no_dispatch", routing_model: "section_pooled",
          intent_kind: "service" },
  })

  async function onSubmit(v: Form) {
    try {
      if (isEdit) {
        // code is immutable; is_reservation_mutation is system-owned (D24)
        await update.mutateAsync({
          id: edit.id,
          label: v.label, department: v.department,
          fulfilment_mode: v.fulfilment_mode,
          routing_model: v.routing_model, intent_kind: v.intent_kind,
        })
        toast.success("Issue code updated")
      } else {
        await create.mutateAsync(v)
        toast.success("Issue code created")
      }
      reset(); setOpen(false)
    } catch (e: any) {
      toast.error(e?.status === 409 ? "Code already exists"
        : "Could not save issue code")
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {isEdit
          ? <Button variant="ghost" size="sm" className="w-full justify-start font-normal">Edit</Button>
          : <Button size="sm">New issue code</Button>}
      </DialogTrigger>
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit issue code" : "New issue code"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="code">code</Label>
            <Input id="code" disabled={isEdit} {...register("code")} />
            {errors.code && (
              <p className="text-destructive text-xs">{errors.code.message}</p>
            )}
          </div>
          {(["label", "department"] as const).map((f) => (
            <div key={f} className="space-y-1.5">
              <Label htmlFor={f}>{f}</Label>
              <Input id={f} {...register(f)} />
              {errors[f] && (
                <p className="text-destructive text-xs">{errors[f]?.message}</p>
              )}
            </div>
          ))}
          {(["fulfilment_mode", "routing_model", "intent_kind"] as const).map((f) => (
            <div key={f} className="space-y-1.5">
              <Label>{f.replace(/_/g, " ")}</Label>
              <Controller
                control={control}
                name={f}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ENUMS[f].map((opt) => (
                        <SelectItem key={opt} value={opt}>
                          {opt.replace(/_/g, " ")}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          ))}
          <div className="space-y-1.5">
            <Label className="flex items-center gap-1.5">
              reservation mutation
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <LockIcon className="text-muted-foreground size-3.5" />
                  </TooltipTrigger>
                  <TooltipContent>
                    System-owned — governs the always-flag policy (D24)
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </Label>
            <Input
              disabled
              readOnly
              value={
                isEdit
                  ? (edit.is_reservation_mutation ? "Yes" : "No")
                  : "System-determined"
              }
            />
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting
              ? "Saving…"
              : isEdit ? "Save changes" : "Create issue code"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
