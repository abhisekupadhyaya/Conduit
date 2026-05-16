import { useAuth } from "@/auth/use-auth"

export function AppBootSplash({ children }: { children: React.ReactNode }) {
  const { loading } = useAuth()
  if (loading)
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-muted-foreground animate-pulse text-sm">
          Conduit
        </span>
      </div>
    )
  return <>{children}</>
}
