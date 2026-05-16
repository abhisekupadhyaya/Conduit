// src/shell/guest/pages/conversation.tsx
import { useAuth } from "@/auth/use-auth"
import { Skeleton } from "@/components/ui/skeleton"
import { ChatScroll } from "@/components/common/chat-scroll"
import { Message } from "@/components/common/message"
import { RequestReceipt } from "@/components/common/request-receipt"
import { ChildStatusCard } from "@/components/common/child-status-card"
import { Composer } from "@/components/common/composer"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import {
  useConversation,
  useSubmitRequest,
} from "@/shell/guest/hooks/use-conversation"

// The conversation IS the guest portal: ask + status + confirm.
// Trust beat: the ambient is read from the auth context (useAuth), never
// the query cache (the stay/binding rule). Instant-ack (Resolution C) is the
// submit mutation's pending state — no polling, no extra endpoint.
export function GuestConversation() {
  const { user } = useAuth()
  const conversation = useConversation()
  const submit = useSubmitRequest()

  const reqs = conversation.data ?? []

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col">
      <div className="pb-2">
        <h1 className="text-lg font-semibold tracking-tight">
          {user ? `Hi ${user.name}` : "Conversation"}
        </h1>
        <p className="text-muted-foreground text-sm">
          Your room and stay are already known — just ask.
        </p>
      </div>

      {conversation.isLoading ? (
        <div className="flex-1 space-y-3 py-2">
          <Skeleton className="h-12 w-2/3" />
          <Skeleton className="ml-auto h-10 w-1/2" />
          <Skeleton className="h-16 w-3/4" />
        </div>
      ) : conversation.isError ? (
        <div className="flex-1 py-2">
          <ErrorState
            title="Couldn’t load your conversation."
            onRetry={conversation.refetch}
          />
        </div>
      ) : reqs.length === 0 && !submit.isPending ? (
        <div className="flex-1 py-2">
          <EmptyState
            title="No requests yet"
            hint="Ask for anything — in plain words. Room and stay are already known."
          />
        </div>
      ) : (
        <ChatScroll pinKey={`${reqs.length}:${submit.isPending}`}>
          {reqs.map((r) => (
            <div key={r.request_id} className="space-y-3">
              <RequestReceipt children={r.children} />
              {r.children.map((c, i) => (
                <div key={c.child_id} className="space-y-1">
                  <Message from="system" mark={i === 0}>
                    {c.text}
                  </Message>
                  <ChildStatusCard child={c} />
                </div>
              ))}
            </div>
          ))}
          {submit.isPending && (
            <Message from="system">
              <span className="text-muted-foreground animate-pulse">
                Looking into that…
              </span>
            </Message>
          )}
        </ChatScroll>
      )}

      <Composer
        onSend={(text) => submit.mutate(text)}
        pending={submit.isPending}
      />
    </div>
  )
}
