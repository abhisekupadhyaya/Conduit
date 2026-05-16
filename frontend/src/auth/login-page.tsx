import { Card } from "@/components/ui/card"
import { LoginForm } from "@/auth/login-form"

export function LoginPage() {
  return (
    <div className="bg-background flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-[380px] p-6">
        <div className="mb-6 text-center">
          <div className="text-lg font-semibold tracking-tight">Conduit</div>
        </div>
        <LoginForm />
      </Card>
    </div>
  )
}
