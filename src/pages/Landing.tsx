import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'

const themes = [
  'Technology sector flow',
  'Semiconductor momentum',
  'AI concentration dynamics',
  'Liquidity regime signals',
  'Market breadth and divergence',
]

const tickers = [
  'Technology Select Sector SPDR Fund',
  'VanEck Semiconductor ETF',
  'Roundhill Magnificent Seven ETF',
  'Consumer Discretionary Select Sector SPDR Fund',
  'Financial Select Sector SPDR Fund',
  'Industrial Select Sector SPDR Fund',
  'Energy Select Sector SPDR Fund',
  'iShares Russell 2000 ETF',
]

export default function Landing() {
  const user = useAuthStore((s) => s.user)
  return (
    <section className="space-y-10">
      <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-8 shadow-glow">
        <div className="max-w-3xl space-y-6">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">Market intelligence</p>
          <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl">
            Watch sector leadership, breadth, liquidity, and AI concentration in one dashboard.
          </h1>
          <p className="text-slate-300 sm:text-lg">
            Instead of looking at QQQ alone, your app continuously watches the leading sector ETFs and computes leadership,
            breadth, divergence, momentum, fragility, liquidity regime, and AI concentration level.
          </p>

          <div className="flex flex-col gap-3 sm:flex-row">
            {!user ? (
              <>
                <Link
                  to="/register"
                  className="inline-flex items-center justify-center rounded-full bg-cyan-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
                >
                  Create account
                </Link>
                <Link
                  to="/login"
                  className="inline-flex items-center justify-center rounded-full border border-slate-700 bg-slate-900 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:border-slate-500"
                >
                  Login
                </Link>
              </>
            ) : (
              <Link
                to="/dashboard"
                className="inline-flex items-center justify-center rounded-full bg-cyan-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
              >
                Open Dashboard
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-6 rounded-3xl border border-slate-800 bg-slate-900/80 p-8 shadow-glow">
          <h2 className="text-2xl font-semibold text-white">What the dashboard tracks</h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {themes.map((theme) => (
              <li key={theme} className="rounded-3xl border border-slate-800 bg-slate-950/80 p-5">
                <p className="text-sm text-slate-300">{theme}</p>
              </li>
            ))}
          </ul>
        </div>

        <aside className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-glow">
          <h3 className="text-xl font-semibold text-white">ETF universe</h3>
          <p className="mt-3 text-sm leading-6 text-slate-300">
            Continuous monitoring of the underlying instruments behind your model.
          </p>
          <ul className="mt-6 space-y-3 text-slate-200">
            {tickers.map((ticker) => (
              <li key={ticker} className="rounded-2xl bg-slate-950/80 px-4 py-3">
                {ticker}
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </section>
  )
}
