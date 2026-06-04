import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { startCheckout, openBillingPortal } from '../services/billing'

function Tier({
  name,
  price,
  bullets,
  cta,
  onCta,
  ctaDisabled,
  highlight,
}: {
  name: string
  price: string
  bullets: string[]
  cta?: string
  onCta?: () => void
  ctaDisabled?: boolean
  highlight?: boolean
}) {
  return (
    <div
      className={`rounded-3xl border bg-slate-900/80 p-6 ${
        highlight ? 'border-cyan-500/50 shadow-glow' : 'border-slate-800'
      }`}
    >
      <h3 className="text-xl font-semibold text-white">{name}</h3>
      <p className="mt-2 text-3xl font-bold text-white">{price}</p>
      <ul className="mt-4 space-y-2 text-slate-200">
        {bullets.map((b) => (
          <li key={b} className="rounded-2xl bg-slate-950/80 px-3 py-2">
            {b}
          </li>
        ))}
      </ul>
      <div className="mt-4">
        <button
          onClick={onCta}
          disabled={ctaDisabled}
          className="rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {cta || 'Get started'}
        </button>
      </div>
    </div>
  )
}

export default function Pricing() {
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const isPro = user?.plan === 'pro'

  const handleProCta = async () => {
    // not signed in → send them to log in first
    if (!user || !token) {
      navigate('/login')
      return
    }
    setError('')
    setLoading(true)
    try {
      // both calls redirect the browser to Stripe on success and never return
      if (isPro) {
        await openBillingPortal(token)
      } else {
        await startCheckout(token)
      }
    } catch (e) {
      setError((e as Error).message)
      setLoading(false)
    }
  }

  const proCta = loading
    ? 'Loading…'
    : isPro
      ? 'Manage subscription'
      : 'Upgrade to Pro'

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-cyan-950/40 p-8 shadow-glow sm:p-10">
        <div className="pointer-events-none absolute -right-20 -top-20 h-60 w-60 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="relative max-w-2xl">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
            Pricing
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Simple, honest pricing
          </h1>
          <p className="mt-4 text-base leading-7 text-slate-300">
            Start free with the live tech-regime dashboard (QQQ / Nasdaq-100). Upgrade
            to Pro for regime alerts, full sector analytics, and data export.
          </p>
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-3">
        <Tier
          name="Starter"
          price="Free"
          bullets={['Live tech-regime dashboard', 'Community support', '1 watchlist']}
          cta="Sign up"
          onCta={() => navigate(user ? '/dashboard' : '/register')}
        />
        <Tier
          name="Pro"
          price="$29/mo"
          bullets={['Regime-change alerts', 'Full history & exports', 'Priority data refresh']}
          cta={proCta}
          onCta={handleProCta}
          ctaDisabled={loading}
          highlight
        />
        <Tier
          name="Team"
          price="$99/mo"
          bullets={['Priority support', 'Team seats', 'API access']}
          cta="Contact sales"
        />
      </div>

      {error && (
        <p className="rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </p>
      )}

      <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
        <h2 className="text-2xl font-semibold text-white">Feature comparison</h2>
        <p className="mt-3 text-slate-300">Compare features across plans to pick the right fit.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full table-auto text-left text-sm text-slate-200">
            <thead>
              <tr>
                <th className="px-3 py-2">Feature</th>
                <th className="px-3 py-2">Starter</th>
                <th className="px-3 py-2">Pro</th>
                <th className="px-3 py-2">Team</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-3 py-2">Regime-change alerts</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2">✓</td>
                <td className="px-3 py-2">✓</td>
              </tr>
              <tr>
                <td className="px-3 py-2">Full history &amp; exports</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2">✓</td>
                <td className="px-3 py-2">✓</td>
              </tr>
              <tr>
                <td className="px-3 py-2">API access</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2">✓</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
        <h2 className="text-2xl font-semibold text-white">Frequently asked questions</h2>
        <div className="mt-4 space-y-3 text-slate-200">
          <details className="rounded-2xl bg-slate-950/80 p-3">
            <summary className="cursor-pointer">Can I cancel anytime?</summary>
            <p className="mt-2 text-slate-300">
              Yes — manage or cancel your subscription at any time; Pro stays active until the
              end of the billing period.
            </p>
          </details>
          <details className="rounded-2xl bg-slate-950/80 p-3">
            <summary className="cursor-pointer">Is there an enterprise option?</summary>
            <p className="mt-2 text-slate-300">
              We offer custom enterprise plans with SSO, dedicated SLAs, and API access.
            </p>
          </details>
        </div>
      </section>
    </div>
  )
}
