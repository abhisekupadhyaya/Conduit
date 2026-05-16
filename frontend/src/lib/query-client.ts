import { QueryClient } from "@tanstack/react-query"

// Convention: every backend call goes through TanStack Query — useQuery for
// reads, useMutation for writes — EXCEPT auth (login/logout live in
// auth-provider as direct api-client calls). The product's real-time model is
// polling-first (AD7), so live surfaces (awareness stream, decision queue,
// guest status, servicer queue) set `refetchInterval` per-hook rather than
// using websockets.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: 0,
    },
  },
})
