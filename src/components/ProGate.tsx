import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'

/** Hook: true when the signed-in user is on the Pro plan. */
export function useIsPro(): boolean {
  return useAuthStore((s) => s.user?.plan === 'pro')
}

/**
 * Wraps Pro-only content. Pro users see it normally; everyone else sees it
 * blurred behind an "Upgrade to Pro" overlay.
 *
 * Note: this is a UX gate, not a security boundary — anything that must be
 * truly protected is gated on the backend (see auth.require_pro).
 */
export default function ProGate({
  children,
  label = 'Pro feature',
}: {
  children: ReactNode
  label?: string
}) {
  const isPro = useIsPro()
  if (isPro) return <>{children}</>

  return (
    <div className="relative overflow-hidden rounded-3xl">
      <div aria-hidden className="pointer-events-none select-none blur-[6px] opacity-40">
        {children}
      </div>
      <div className="absolute inset-0 grid place-items-center bg-slate-950/50 p-6">
        <div className="max-w-sm rounded-2xl border border-cyan-500/30 bg-slate-900/95 p-6 text-center shadow-glow">
          <div className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-cyan-500/15 text-xl">
            🔒
          </div>
          <h3 className="mt-3 text-base font-semibold text-white">{label}</h3>
          <p className="mt-1 text-sm text-slate-400">
            Upgrade to Pro to unlock {label.toLowerCase()}.
          </p>
          <Link
            to="/pricing"
            className="mt-4 inline-block rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
          >
            Upgrade to Pro
          </Link>
        </div>
      </div>
    </div>
  )
}
