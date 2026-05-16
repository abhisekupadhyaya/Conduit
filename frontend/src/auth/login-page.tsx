import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { LoginForm } from "@/auth/login-form"
import { useAuth } from "@/auth/use-auth"
import { roleHome } from "@/lib/role-routing"

// login-02 layout: a centered card on a muted background.
export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center gap-6 p-6 md:p-10">
      <div className="w-full max-w-sm">
        <LoginForm
          loading={loading}
          onSubmit={async (username, password) => {
            setLoading(true)
            try {
              await login(username, password)
              const stored = localStorage.getItem("conduit-auth")
              const role = stored ? JSON.parse(stored).role : "guest"
              navigate(roleHome(role), { replace: true })
            } finally {
              setLoading(false)
            }
          }}
        />
      </div>
    </div>
  )
}
