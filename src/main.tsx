import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from 'react-router'
import { router } from './app/router'
import { useAuthStore } from './stores/useAuthStore'
import './index.css'

// Exchange the refresh cookie for an access token before the first paint of a
// guarded route. Not awaited: the public site must not wait on an auth call it
// does not need, and `RequireAuth` already renders a checking state until this
// settles.
void useAuthStore.getState().bootstrap()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
)
