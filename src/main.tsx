import React from "react"
import ReactDOM from "react-dom/client"
import { RouterProvider } from "react-router"
import { QueryClientProvider } from "@tanstack/react-query"
import { router } from "./app/router"
import { createQueryClient } from "./app/queryClient"
import { useAuthStore } from "./stores/useAuthStore"
import "./index.css"

// Exchange the refresh cookie for an access token before the first paint of a
// guarded route. Not awaited: the public site must not wait on an auth call it
// does not need, and `RequireAuth` already renders a checking state until this
// settles.
void useAuthStore.getState().bootstrap()

// One client for the process. Created here rather than at module scope in
// `queryClient.ts` so tests and the snapshot harness can build their own with
// retries disabled.
const queryClient = createQueryClient()

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
)
