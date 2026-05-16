import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { useCreateAccount } from "@/shell/supervisor/hooks/use-accounts"

const schema = z.object({
  username: z.string().min(1),
  display_name: z.string().min(1),
  password: z.string().min(6),
})
type Form = z.infer<typeof schema>

export function AccountFormDialog({ role, label }: { role: string; label: string }) {
  const [open, setOpen] = useState(false)
  const create = useCreateAccount()
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<Form>({ resolver: zodResolver(schema) })

  async function onSubmit(v: Form) {
    try {
      await create.mutateAsync({ role, ...v })
      toast.success(`${label} created`)
      reset(); setOpen(false)
    } catch (e: any) {
      toast.error(e?.status === 409 ? "Username already exists"
        : "Could not create account")
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm">Add {label}</Button></DialogTrigger>
      <DialogContent className="w-[calc(100vw-2rem)] sm:max-w-md">
        <DialogHeader><DialogTitle>Add {label}</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
          {(["username", "display_name", "password"] as const).map((f) => (
            <div key={f} className="space-y-1.5">
              <Label htmlFor={f}>{f.replace("_", " ")}</Label>
              <Input id={f} type={f === "password" ? "password" : "text"}
                     {...register(f)} />
              {errors[f] && (
                <p className="text-destructive text-xs">{errors[f]?.message}</p>
              )}
            </div>
          ))}
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Adding…" : `Add ${label}`}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
