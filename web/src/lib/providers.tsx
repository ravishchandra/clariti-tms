"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Client-side providers — TanStack Query + shadcn TooltipProvider.
 *
 * Lives in a `"use client"` boundary so the root layout (a server component)
 * can still render server-side without dragging React Query into the
 * server bundle.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Most data in this UI is reviewer-facing — staleness matters less
            // than not double-fetching while a reviewer flicks j/k through 200
            // strings. 30s is a defensible default; individual queries override.
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>{children}</TooltipProvider>
      {process.env.NODE_ENV === "development" ? <ReactQueryDevtools initialIsOpen={false} /> : null}
    </QueryClientProvider>
  );
}
