import { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'

type ProtectedRouteProps = {
  children: ReactNode
}

export default function ProtectedRoute({ children }: ProtectedRouteProps) {
  const user = useAuthStore((state) => state.user)
  const ready = useAuthStore((state) => state.ready)

  // Wait for the persisted session to be validated before deciding —
  // otherwise a logged-in user is briefly bounced to /login on refresh.
  if (!ready) {
    return (
      <div className="grid min-h-[40vh] place-items-center text-sm text-slate-400">
        <span className="animate-pulse">Restoring session…</span>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}
