import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

// The conversation IS the portal (sitemap 1.2): ask + status + confirm.
export function GuestConversation() {
  return (
    <div className="flex flex-1 flex-col">
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <p className="text-muted-foreground text-sm">
          Ask for anything — in plain words. Room and stay are already known.
        </p>
      </div>
      <form className="flex gap-2 pt-4">
        <Input placeholder="e.g. can I get 2 extra bath towels" />
        <Button type="submit">Send</Button>
      </form>
    </div>
  )
}
