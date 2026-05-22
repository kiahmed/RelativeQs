import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'

/**
 * Landing page after Stripe Checkout. The Stripe webhook updates the plan
 * server-side asynchronously, so this page polls the profiles table for a
 * few seconds until the plan flips to 'pro'.
 */
export default function BillingSuccess() {
  const user = useAuthStore((s) => s.user)
  const refreshPlan = useAuthStore((s) => s.refreshPlan)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let cancelled = false
    let tries = 0

    const poll = async () => {
      tries += 1
      await refreshPlan()
      if (cancelled) return
      const plan = useAuthStore.getState().user?.plan
      if (plan === 'pro' || tries >= 8) {
        setChecking(false)
        return
      }
      setTimeout(poll, 2000)
    }
    poll()

    return () => {
      cancelled = true
    }
  }, [refreshPlan])

  const isPro = user?.plan === 'pro'

  return (
    <div className="mx-auto max-w-xl rounded-3xl border border-slate-800 bg-slate-900/90 p-8 text-center shadow-glow">
      {checking ? (
        <>
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-2 border-slate-700 border-t-cyan-400" />
          <h1 className="mt-6 text-2xl font-semibold text-white">Confirming your subscription…</h1>
          <p className="mt-2 text-slate-400">
            Payment received. We&apos;re activating your Pro access — this only takes a moment.
          </p>
        </>
      ) : isPro ? (
        <>
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-emerald-500/15 text-3xl">
            🎉
          </div>
          <h1 className="mt-6 text-2xl font-semibold text-white">You&apos;re on Pro</h1>
          <p className="mt-2 text-slate-400">
            Your subscription is active. Thanks for supporting Price Flow Tracker.
          </p>
          <Link
            to="/dashboard"
            className="mt-6 inline-block rounded-full bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
          >
            Go to dashboard
          </Link>
        </>
      ) : (
        <>
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-amber-500/15 text-3xl">
            ⏳
          </div>
          <h1 className="mt-6 text-2xl font-semibold text-white">Payment received</h1>
          <p className="mt-2 text-slate-400">
            Your Pro access is taking a little longer than usual to activate. It will appear
            shortly — refresh the dashboard in a minute.
          </p>
          <Link
            to="/dashboard"
            className="mt-6 inline-block rounded-full border border-slate-700 px-5 py-2.5 text-sm font-semibold text-slate-200 transition hover:bg-slate-800"
          >
            Go to dashboard
          </Link>
        </>
      )}
    </div>
  )
}
