import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert } from "@/components/ui/alert"
import { useAuth } from "@/auth/use-auth"

const schema = z.object({ username: z.string().min(1), password: z.string().min(1) })
type Form = z.infer<typeof schema>

export function LoginForm() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [err, setErr] = useState<string | null>(null)
  const { register, handleSubmit, formState: { isSubmitting } } =
    useForm<Form>({ resolver: zodResolver(schema) })

  async function onSubmit(v: Form) {
    setErr(null)
    try { await login(v.username, v.password); nav("/", { replace: true }) }
    catch { setErr("Incorrect username or password") }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {err && (
        <Alert variant="destructive" className="text-sm">{err}</Alert>
      )}
      <div className="space-y-1.5">
        <Label htmlFor="username">Username</Label>
        <Input id="username" autoFocus {...register("username")} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="password">Password</Label>
        <Input id="password" type="password" {...register("password")} />
      </div>
      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
      <p className="text-muted-foreground text-center text-xs">
        Accounts are created by your administrator.
      </p>
    </form>
  )
}
