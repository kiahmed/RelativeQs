import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'

const features = [
  {
    icon: '🧭',
    iconBg: 'bg-cyan-500/15',
    iconText: 'text-cyan-300',
    title: 'Trend regime',
    desc: 'See at a glance whether the market is risk-on or risk-off — driven by QQQ’s position relative to its 200-day trend.',
  },
  {
    icon: '📊',
    iconBg: 'bg-indigo-500/15',
    iconText: 'text-indigo-300',
    title: 'Sector leadership',
    desc: 'Relative strength, divergence, and rolling correlations across the ETFs that actually move the Nasdaq-100.',
  },
  {
    icon: '🔔',
    iconBg: 'bg-emerald-500/15',
    iconText: 'text-emerald-300',
    title: 'Regime alerts',
    desc: 'Get an email the moment the market flips between risk-on and risk-off — no screen-watching required.',
  },
  {
    icon: '⚠️',
    iconBg: 'bg-amber-500/15',
    iconText: 'text-amber-300',
    title: 'Fragility & breadth',
    desc: 'Tell whether a rally is broad and healthy or narrow and fragile — before the difference shows up in price.',
  },
]

const etfs = [
  { s: 'QQQ', n: 'Nasdaq-100' },
  { s: 'XLK', n: 'Technology' },
  { s: 'SMH', n: 'Semiconductors' },
  { s: 'XLY', n: 'Consumer Disc.' },
  { s: 'XLF', n: 'Financials' },
  { s: 'XLI', n: 'Industrials' },
  { s: 'XLE', n: 'Energy' },
  { s: 'IWM', n: 'Russell 2000' },
]

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
      {children}
    </p>
  )
}

export default function Landing() {
  const user = useAuthStore((s) => s.user)

  return (
    <div className="space-y-8">
      {/* ---- hero ---- */}
      <section className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-cyan-950/40 p-8 shadow-glow sm:p-12">
        <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-64 w-64 rounded-full bg-indigo-500/10 blur-3xl" />

        <div className="relative max-w-3xl animate-fade-up">
          <SectionLabel>Market-regime intelligence</SectionLabel>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight text-white sm:text-5xl">
            Know whether the market is{' '}
            <span className="text-emerald-400">risk-on</span> — or{' '}
            <span className="text-rose-400">risk-off</span>.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
            Price Flow Tracker watches the sector ETFs behind the Nasdaq-100 and
            distils them into one clear read: the market’s trend regime, plus the
            leadership, breadth, and fragility behind it.
          </p>

          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            {!user ? (
              <>
                <Link
                  to="/register"
                  className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-cyan-400 to-indigo-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:opacity-90"
                >
                  Get started — it’s free
                </Link>
                <Link
                  to="/login"
                  className="inline-flex items-center justify-center rounded-full border border-slate-700 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:border-slate-500 hover:bg-slate-800"
                >
                  Log in
                </Link>
              </>
            ) : (
              <Link
                to="/dashboard"
                className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-cyan-400 to-indigo-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:opacity-90"
              >
                Open dashboard →
              </Link>
            )}
          </div>

          <div className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" /> 200-day trend model
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" /> 8 sector ETFs
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Backtested 2014–2026
            </span>
          </div>
        </div>
      </section>

      {/* ---- features ---- */}
      <section>
        <div className="mb-5">
          <SectionLabel>What you get</SectionLabel>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            The whole market, read in one glance
          </h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-card transition hover:-translate-y-0.5 hover:border-slate-700"
            >
              <span
                className={`grid h-10 w-10 place-items-center rounded-xl text-lg ${f.iconBg} ${f.iconText}`}
              >
                {f.icon}
              </span>
              <h3 className="mt-4 text-base font-semibold text-white">{f.title}</h3>
              <p className="mt-1.5 text-sm leading-6 text-slate-400">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---- proof + ETF universe ---- */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="rounded-3xl border border-emerald-800/40 bg-gradient-to-br from-slate-900 to-emerald-950/30 p-8 shadow-glow">
          <SectionLabel>Backed by a backtest</SectionLabel>
          <h2 className="mt-3 text-2xl font-semibold text-white">
            A signal that held up over 12 years
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-7 text-slate-300">
            Over 2014–2026, following the trend regime matched buy-and-hold’s
            return with a <strong className="text-emerald-300">~13-point shallower
            maximum drawdown</strong> (−22% vs −35%). We don’t claim to predict
            the market — we make its current posture legible.
          </p>
          <p className="mt-4 text-xs text-slate-500">
            Market-internals analytics and education — not investment advice. Past
            performance does not guarantee future results.
          </p>
        </section>

        <aside className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-glow">
          <SectionLabel>ETF universe</SectionLabel>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            The instruments continuously monitored behind every signal.
          </p>
          <div className="mt-5 grid grid-cols-2 gap-2">
            {etfs.map((e) => (
              <div
                key={e.s}
                className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2.5"
              >
                <p className="text-sm font-bold tracking-tight text-white">{e.s}</p>
                <p className="truncate text-xs text-slate-500">{e.n}</p>
              </div>
            ))}
          </div>
        </aside>
      </div>

      {/* ---- final CTA ---- */}
      <section className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900 to-indigo-950/40 p-8 text-center shadow-glow sm:p-10">
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-indigo-500/10 blur-3xl" />
        <div className="relative">
          <h2 className="text-2xl font-semibold text-white sm:text-3xl">
            Start tracking the market regime
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-slate-400">
            Free to use — create an account and open the live dashboard in seconds.
          </p>
          <div className="mt-6 flex justify-center">
            <Link
              to={user ? '/dashboard' : '/register'}
              className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-cyan-400 to-indigo-500 px-7 py-3 text-sm font-semibold text-slate-950 transition hover:opacity-90"
            >
              {user ? 'Open dashboard →' : 'Create your free account'}
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}
