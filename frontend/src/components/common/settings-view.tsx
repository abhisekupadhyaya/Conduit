import type { ReactNode } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { PageHeader } from "@/components/layout/page-header"
import { useAuth } from "@/auth/use-auth"
import { useUpdateSelf } from "@/auth/use-update-self"

const pwSchema = z.object({
  current_password: z.string().min(1),
  new_password: z.string().min(6),
}).refine((d) => d.current_password !== d.new_password, {
  message: "New password must differ", path: ["new_password"],
})

export function SettingsView({ team }: { team?: ReactNode }) {
  const { user } = useAuth()
  const save = useUpdateSelf()
  const name = useForm<{ display_name: string }>({
    defaultValues: { display_name: user?.name ?? "" },
  })
  const pw = useForm<z.infer<typeof pwSchema>>({ resolver: zodResolver(pwSchema) })

  return (
    <div>
      <PageHeader title="Settings" />
      <Tabs defaultValue="profile" className="max-w-2xl">
        <TabsList className="overflow-x-auto">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="password">Password</TabsTrigger>
          {team && <TabsTrigger value="team">Team</TabsTrigger>}
        </TabsList>

        <TabsContent value="profile" className="space-y-3 pt-4">
          <form
            onSubmit={name.handleSubmit(async (v) => {
              try { await save.mutateAsync(v); toast.success("Profile updated") }
              catch { toast.error("Update failed") }
            })}
            className="space-y-3">
            <div className="space-y-1.5">
              <Label>Display name</Label>
              <Input {...name.register("display_name", { required: true })} />
            </div>
            <div className="space-y-1.5">
              <Label>Username</Label>
              <Input value={user?.username ?? ""} disabled />
            </div>
            <Button type="submit" disabled={name.formState.isSubmitting}>
              Save
            </Button>
          </form>
        </TabsContent>

        <TabsContent value="password" className="space-y-3 pt-4">
          <form
            onSubmit={pw.handleSubmit(async (v) => {
              try {
                await save.mutateAsync(v); pw.reset()
                toast.success("Password changed")
              } catch { toast.error("Current password incorrect") }
            })}
            className="space-y-3">
            <div className="space-y-1.5">
              <Label>Current password</Label>
              <Input type="password" {...pw.register("current_password")} />
            </div>
            <div className="space-y-1.5">
              <Label>New password</Label>
              <Input type="password" {...pw.register("new_password")} />
              {pw.formState.errors.new_password && (
                <p className="text-destructive text-xs">
                  {pw.formState.errors.new_password.message}
                </p>
              )}
            </div>
            <Button type="submit" disabled={pw.formState.isSubmitting}>
              Change password
            </Button>
          </form>
        </TabsContent>

        {team && (
          <TabsContent value="team" className="pt-4">{team}</TabsContent>
        )}
      </Tabs>
    </div>
  )
}
