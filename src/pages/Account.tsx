import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { supabase } from '../services/supabase'
import { openBillingPortal } from '../services/billing'

const inputCls =
  'mt-2 w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 ' +
  'text-slate-100 outline-none transition focus:border-cyan-400'

export default function Account() {
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)

  const [fullName, setFullName] = useState(user?.fullName ?? '')
  const [savingName, setSavingName] = useState(false)
  const [nameMsg, setNameMsg] = useState('')
  const [billingBusy, setBillingBusy] = useState(false)
  const [billingErr, setBillingErr] = useState('')

  // ProtectedRoute guarantees a user, but keep TypeScript + safety happy
  if (!user) return null

  const isPro = user.plan === 'pro'

  const saveName = async () => {
    setNameMsg('')
    setSavingName(true)
    const { error } = await supabase.auth.updateUser({
      data: { full_name: fullName.trim() },
    })
    setSavingName(false)
    setNameMsg(error ? error.message : '✓ Saved.')
  }

  const manageBilling = async () => {
    if (!token) return
    setBillingErr('')
    setBillingBusy(true)
    try {
      await openBillingPortal(token) // redirects to Stripe on success
    } catch (e) {
      setBillingErr((e as Error).message)
      setBillingBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold text-white">Account</h1>
        <p className="mt-2 text-slate-400">Manage your profile and subscription.</p>
      </div>

      {/* ---- profile ---- */}
      <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-glow">
        <h2 className="text-lg font-semibold text-white">Profile</h2>

        <div className="mt-5">
          <label className="block text-sm font-medium text-slate-200" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            value={user.email}
            readOnly
            disabled
            className={`${inputCls} cursor-not-allowed opacity-70`}
          />
          <p className="mt-1 text-xs text-slate-500">
            Email changes aren&apos;t supported here yet.
          </p>
        </div>

        <div className="mt-4">
          <label className="block text-sm font-medium text-slate-200" htmlFor="fullName">
            Full name
          </label>
          <input
            id="fullName"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className={inputCls}
            placeholder="Your name"
          />
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={saveName}
            disabled={savingName}
            className="rounded-2xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-60"
          >
            {savingName ? 'Saving…' : 'Save changes'}
          </button>
          {nameMsg && <span className="text-sm text-slate-400">{nameMsg}</span>}
        </div>
      </div>

      {/* ---- subscription ---- */}
      <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-glow">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Subscription</h2>
          <span
            className={`rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${
              isPro ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-700/50 text-slate-300'
            }`}
          >
            {isPro ? 'Pro' : 'Free'}
          </span>
        </div>

        {isPro ? (
          <>
            <p className="mt-3 text-sm text-slate-400">
              You&apos;re on the <strong className="text-emerald-300">Pro</strong> plan —
              regime-change alerts, full sector analytics, and CSV export are unlocked.
            </p>
            <button
              onClick={manageBilling}
              disabled={billingBusy}
              className="mt-4 rounded-2xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-cyan-500/50 hover:bg-slate-800 disabled:opacity-60"
            >
              {billingBusy ? 'Opening…' : 'Manage subscription'}
            </button>
            {billingErr && <p className="mt-2 text-sm text-rose-400">{billingErr}</p>}
          </>
        ) : (
          <>
            <p className="mt-3 text-sm text-slate-400">
              You&apos;re on the <strong className="text-slate-200">Free</strong> plan.
              Upgrade to Pro for regime-change email alerts, full sector analytics, and
              data export.
            </p>
            <Link
              to="/pricing"
              className="mt-4 inline-block rounded-2xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
            >
              Upgrade to Pro
            </Link>
          </>
        )}
      </div>
    </div>
  )
}
