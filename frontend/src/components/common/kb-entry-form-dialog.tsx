import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import {
  useCreateKBEntry, useUpdateKBEntry, type KBEntry,
} from "@/shell/supervisor/hooks/use-kb"

const schema = z.object({
  topic: z.string().min(1),
  content: z.string().min(1),
})
type Form = z.infer<typeof schema>

export function KbEntryFormDialog({ edit }: { edit?: KBEntry }) {
  const [open, setOpen] = useState(false)
  const create = useCreateKBEntry()
  const update = useUpdateKBEntry()
  const isEdit = !!edit
  const { register, handleSubmit, reset,
    formState: { errors, isSubmitting } } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: edit
      ? { topic: edit.topic, content: edit.content }
      : undefined,
  })

  async function onSubmit(v: Form) {
    try {
      if (isEdit) {
        await update.mutateAsync({ id: edit.id, ...v })
        toast.success("Entry updated")
      } else {
        await create.mutateAsync(v)
        toast.success("Entry created")
      }
      reset(); setOpen(false)
    } catch {
      toast.error("Could not save entry")
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {isEdit
          ? <Button variant="ghost" size="sm" className="w-full justify-start font-normal">Edit</Button>
          : <Button size="sm">New entry</Button>}
      </DialogTrigger>
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit entry" : "New entry"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="topic">topic</Label>
            <Input id="topic" {...register("topic")} />
            {errors.topic && (
              <p className="text-destructive text-xs">{errors.topic.message}</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="content">content</Label>
            <Textarea id="content" rows={6} {...register("content")} />
            {errors.content && (
              <p className="text-destructive text-xs">{errors.content.message}</p>
            )}
          </div>
          <p className="text-muted-foreground text-xs">
            Answers are grounded only in active entries (D26).
          </p>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting
              ? "Saving…"
              : isEdit ? "Save changes" : "Create entry"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
