import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import { fetchAIDependency } from '../services/marketApi'
import type { AIDependency } from '../data/marketSignals'

const features = [
  {
    icon: '🧠',
    iconBg: 'bg-fuchsia-500/15',
    iconText: 'text-fuchsia-300',
    title: 'AI build-out dependency',
    desc: 'See how much of QQQ’s move is really an AI-infrastructure trade — memory, optics, networking, power, grid — and how that dependency is trending.',
  },
  {
    icon: '📊',
    iconBg: 'bg-indigo-500/15',
    iconText: 'text-indigo-300',
    title: 'Sector leadership',
    desc: 'Relative strength, divergence, and rolling correlations across the sector ETFs that actually move the Nasdaq-100.',
  },
  {
    icon: '🔔',
    iconBg: 'bg-emerald-500/15',
    iconText: 'text-emerald-300',
    title: 'Breadth-shift alerts',
    desc: 'Get an email the moment Nasdaq-100 participation flips between broad, mixed and narrow — no screen-watching required.',
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
  const [aiDep, setAiDep] = useState<AIDependency | null>(null)

  useEffect(() => {
    let alive = true
    fetchAIDependency()
      .then((d) => {
        if (alive && d && d.status === 'ok') setAiDep(d)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  const depPct = aiDep ? Math.round(aiDep.dependency_now * 100) : null
  const depChange = aiDep ? Math.round(aiDep.change * 100) : 0
  const depThemes = (aiDep?.themes ?? []).filter((t) => t.corr_now != null).slice(0, 5)

  return (
    <div className="space-y-8">
      {/* ---- hero ---- */}
      <section className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-cyan-950/40 p-8 shadow-glow sm:p-12">
        <div className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-64 w-64 rounded-full bg-indigo-500/10 blur-3xl" />

        <div className="relative max-w-3xl animate-fade-up">
          <SectionLabel>Tech-regime intelligence · QQQ / Nasdaq-100</SectionLabel>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight text-white sm:text-5xl">
            Plan a better tech trade — know whether tech is{' '}
            <span className="text-emerald-400">risk-on</span> or{' '}
            <span className="text-rose-400">risk-off</span> right now.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
            RelativeQs reads the Nasdaq-100 (QQQ) and the sector ETFs that drive it,
            and distils them into one clear call: is tech risk-on or risk-off — plus
            the leadership, breadth, and fragility behind the move.
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
              <span className="h-1.5 w-1.5 rounded-full bg-fuchsia-400" /> AI-dependency index
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" /> Sector ETF rotation
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Live Nasdaq-100 breadth
            </span>
          </div>
        </div>
      </section>

      {/* ---- flagship: AI build-out dependency ---- */}
      <section className="relative overflow-hidden rounded-3xl border border-fuchsia-500/25 bg-gradient-to-br from-slate-900 via-slate-900 to-fuchsia-950/30 p-8 shadow-glow sm:p-10">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-fuchsia-500/10 blur-3xl" />
        <div className="relative grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,360px)] lg:items-center">
          <div>
            <SectionLabel>The AI-dependency lens</SectionLabel>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
              How much of the Nasdaq is now an AI build-out trade?
            </h2>
            <p className="mt-4 max-w-xl text-sm leading-7 text-slate-300 sm:text-base">
              Over the last couple of years the Nasdaq’s gains have leaned ever harder on the
              AI-capex supply chain — memory, optics/EUV, servers &amp; networking, power and the
              grid. RelativeQs puts a measured number on that dependency and tracks how it has
              evolved, so you can see what’s really carrying tech — not just guess.
            </p>
            <p className="mt-4 text-xs text-slate-500">
              Structural, daily read — deliberately separate from the intraday signals. Basket is
              configurable as new bottleneck funds and companies emerge.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-6">
            {depPct != null ? (
              <>
                <p className="text-[0.65rem] uppercase tracking-[0.2em] text-fuchsia-300/80">
                  QQQ explained by the AI complex
                </p>
                <div className="mt-2 flex items-end gap-3">
                  <p className="text-5xl font-bold tracking-tight text-white">{depPct}%</p>
                  <span
                    className={`mb-1.5 text-sm font-semibold ${
                      depChange > 0
                        ? 'text-emerald-300'
                        : depChange < 0
                          ? 'text-rose-300'
                          : 'text-slate-400'
                    }`}
                  >
                    {depChange >= 0 ? '▲' : '▼'} {Math.abs(depChange)} pts / mo
                  </span>
                </div>
                <div className="mt-5 space-y-2">
                  {depThemes.map((t) => (
                    <div key={t.key}>
                      <div className="flex items-center justify-between text-xs text-slate-400">
                        <span>{t.label}</span>
                        <span className="font-semibold text-slate-200">
                          {Math.round((t.corr_now ?? 0) * 100)}%
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                        <div
                          className="h-full rounded-full bg-fuchsia-400"
                          style={{ width: `${Math.abs(Math.round((t.corr_now ?? 0) * 100))}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <>
                <p className="text-[0.65rem] uppercase tracking-[0.2em] text-fuchsia-300/80">
                  Tracked bottlenecks
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  {['Memory', 'Optics / EUV', 'Servers / Networking', 'Power', 'Grid build-out'].map(
                    (b) => (
                      <span
                        key={b}
                        className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-slate-300"
                      >
                        {b}
                      </span>
                    ),
                  )}
                </div>
                <p className="mt-4 text-xs text-slate-500">
                  Live dependency index available inside the dashboard.
                </p>
              </>
            )}
          </div>
        </div>
      </section>

      {/* ---- features ---- */}
      <section>
        <div className="mb-5">
          <SectionLabel>What you get</SectionLabel>
          <h2 className="mt-2 text-2xl font-semibold text-white">
            The Nasdaq-100, read in one glance
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
        <section className="rounded-3xl border border-fuchsia-800/40 bg-gradient-to-br from-slate-900 to-fuchsia-950/30 p-8 shadow-glow">
          <SectionLabel>Why it matters</SectionLabel>
          <h2 className="mt-3 text-2xl font-semibold text-white">
            The Nasdaq has become an AI build-out trade
          </h2>
          <p className="mt-3 max-w-xl text-sm leading-7 text-slate-300">
            More and more of QQQ’s daily move now traces back to a handful of AI
            bottlenecks — <strong className="text-fuchsia-300">memory, optics/EUV,
            servers &amp; networking, power and the grid</strong>. Most dashboards
            still treat tech as one block. RelativeQs measures that dependency
            directly and tracks how it’s shifting, so you can see <em>which</em>
            part of the build-out is actually carrying the index right now.
          </p>
          <p className="mt-3 max-w-xl text-sm leading-7 text-slate-300">
            It’s measured from real daily returns — not index weights, not
            guesswork — and the basket is configurable as new bottleneck funds and
            companies emerge.
          </p>
          <p className="mt-4 text-xs text-slate-500">
            Nasdaq-100 internals analytics and education — not investment advice. Past
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
            Start tracking the tech regime
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
