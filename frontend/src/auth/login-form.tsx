import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"

// Adapted from shadcn login-02 for Conduit: guests are supervisor-provisioned
// (D3a) — username/password only, no self-register, no social login.
export function LoginForm({
  className,
  onSubmit,
  loading,
  ...props
}: Omit<React.ComponentProps<"form">, "onSubmit"> & {
  onSubmit?: (username: string, password: string) => void
  loading?: boolean
}) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")

  return (
    <form
      className={cn("flex flex-col gap-6", className)}
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit?.(username, password)
      }}
      {...props}
    >
      <FieldGroup>
        <div className="flex flex-col items-center gap-1 text-center">
          <h1 className="text-2xl font-bold">Sign in to Conduit</h1>
          <p className="text-sm text-balance text-muted-foreground">
            Use the credentials issued at check-in.
          </p>
        </div>
        <Field>
          <FieldLabel htmlFor="username">Username</FieldLabel>
          <Input
            id="username"
            type="text"
            autoComplete="username"
            required
            className="bg-background"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            className="bg-background"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Field>
          <Button type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
          <FieldDescription className="text-center">
            No account? Your supervisor provisions access.
          </FieldDescription>
        </Field>
      </FieldGroup>
    </form>
  )
}
