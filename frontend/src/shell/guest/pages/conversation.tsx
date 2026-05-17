// src/shell/guest/pages/conversation.tsx
import { useAuth } from "@/auth/use-auth"
import { Skeleton } from "@/components/ui/skeleton"
import { ChatScroll } from "@/components/common/chat-scroll"
import { Message } from "@/components/common/message"
import { ChildStatusCard } from "@/components/common/child-status-card"
import { Composer } from "@/components/common/composer"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import {
  useDispatchCards,
  useSubmitRequest,
} from "@/shell/guest/hooks/use-conversation"

// The conversation IS the guest portal: ask + status + confirm.
// Trust beat: the ambient is read from the auth context (useAuth), never
// the query cache (the stay/binding rule). Instant-ack (Resolution C) is the
// submit mutation's pending state.
//
// F2 (Spec §10 Guest): GET /guest/requests serves the E1 dispatch status
// cards (list[DispatchCardOut] — the dispatch router wins the path match).
// The status surface is POLLED (AD7) via useDispatchCards on the merged
// ['guest','requests'] key; ChildStatusCard renders the dispatch lifecycle
// (states / named servicer D17 / revised_eta countdown D22 / glitch badge)
// with the confirm/reopen/cancel control. Submit stays the instant-ack
// no-dispatch path; the poll then reflects any dispatched child.
export function GuestConversation() {
  const { user } = useAuth()
  const cards = useDispatchCards()
  const submit = useSubmitRequest()

  const items = cards.data ?? []

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

      {cards.isLoading ? (
        <div className="flex-1 space-y-3 py-2">
          <Skeleton className="h-12 w-2/3" />
          <Skeleton className="ml-auto h-10 w-1/2" />
          <Skeleton className="h-16 w-3/4" />
        </div>
      ) : cards.isError ? (
        <div className="flex-1 py-2">
          <ErrorState
            title="Couldn’t load your conversation."
            onRetry={cards.refetch}
          />
        </div>
      ) : items.length === 0 && !submit.isPending ? (
        <div className="flex-1 py-2">
          <EmptyState
            title="No requests yet"
            hint="Ask for anything — in plain words. Room and stay are already known."
          />
        </div>
      ) : (
        <ChatScroll pinKey={`${items.length}:${submit.isPending}`}>
          {items.map((c) => (
            <div key={c.child_id} className="space-y-1">
              {c.issue_label && (
                <Message from="system">{c.issue_label}</Message>
              )}
              <ChildStatusCard card={c} />
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
