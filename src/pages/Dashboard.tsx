import { useEffect, useState, type ReactNode } from 'react'
import {
  Line,
  LineChart,
  ResponsiveContainer,
  CartesianGrid,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
  AreaChart,
  Area,
} from 'recharts'
import { useAuthStore } from '../store/useAuthStore'
import { useMarketStore } from '../store/useMarketStore'
import { BACKEND_URL, POLL_INTERVAL_MS } from '../config'
import ProGate from '../components/ProGate'
import AlertToggle from '../components/AlertToggle'

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v))

/** semantic colour for a health-style 0-100 score */
function scoreTone(score: number) {
  if (score >= 70) return { text: 'text-emerald-400', bar: 'bg-emerald-400', ring: '#34d399' }
  if (score >= 45) return { text: 'text-amber-400', bar: 'bg-amber-400', ring: '#fbbf24' }
  return { text: 'text-rose-400', bar: 'bg-rose-400', ring: '#fb7185' }
}

/** semantic colour for a directional value (change %, score …) */
function trendTone(value: number) {
  if (value > 0)
    return { text: 'text-emerald-400', bar: 'bg-emerald-400', bg: 'bg-emerald-500/10', ring: 'ring-emerald-500/30' }
  if (value < 0)
    return { text: 'text-rose-400', bar: 'bg-rose-400', bg: 'bg-rose-500/10', ring: 'ring-rose-500/30' }
  return { text: 'text-slate-300', bar: 'bg-slate-400', bg: 'bg-slate-500/10', ring: 'ring-slate-500/30' }
}

function fragilityTone(level: string) {
  const l = (level || '').toLowerCase()
  if (l.includes('high') || l.includes('severe') || l.includes('critical'))
    return { text: 'text-rose-400', dot: 'bg-rose-400', glow: 'shadow-glow-rose' }
  if (l.includes('elevat') || l.includes('moderate') || l.includes('caution'))
    return { text: 'text-amber-400', dot: 'bg-amber-400', glow: 'shadow-glow' }
  return { text: 'text-emerald-400', dot: 'bg-emerald-400', glow: 'shadow-glow-emerald' }
}

/* ------------------------------------------------------------------ */
/* small presentational components                                     */
/* ------------------------------------------------------------------ */

function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-slate-800 bg-slate-900/60 shadow-card backdrop-blur-sm ${className}`}
    >
      {children}
    </div>
  )
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
      {children}
    </p>
  )
}

/** circular progress ring */
function Gauge({ value, color, label }: { value: number; color: string; label: ReactNode }) {
  const r = 32
  const c = 2 * Math.PI * r
  const pct = clamp(value, 0, 100)
  const offset = c - (pct / 100) * c
  return (
    <div className="relative h-[84px] w-[84px] shrink-0">
      <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
        <circle cx="40" cy="40" r={r} fill="none" stroke="#1e293b" strokeWidth="8" />
        <circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">{label}</div>
    </div>
  )
}

/** thin labelled progress bar */
function Meter({ value, max, color }: { value: number; max: number; color: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
      <div
        className={`h-full rounded-full ${color}`}
        style={{ width: `${clamp((value / max) * 100, 2, 100)}%`, transition: 'width 0.6s ease' }}
      />
    </div>
  )
}

/** styled recharts tooltip */
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-950/95 px-3 py-2 shadow-glow">
      <p className="mb-1 text-xs text-slate-400">{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} className="text-sm font-medium" style={{ color: p.color }}>
          {String(p.dataKey).toUpperCase()}: {Number(p.value).toFixed(2)}
        </p>
      ))}
    </div>
  )
}

const axisTick = { fill: '#64748b', fontSize: 11 }

/* ------------------------------------------------------------------ */
/* dashboard                                                            */
/* ------------------------------------------------------------------ */

export default function Dashboard() {
  const user = useAuthStore((state) => state.user)
  const token = useAuthStore((state) => state.token)
  const {
    signals,
    qqqComparison,
    xlyXlpRatio,
    rollingCorrelation,
    breadthHistory,
    qqqHealth,
    qqqScore,
    fragilityMeter,
    leadLag,
    aiConcentration,
    loading,
    wsConnected,
    refresh,
    startRealtime,
    stopRealtime,
  } = useMarketStore()

  const [updatedAt, setUpdatedAt] = useState<Date>(new Date())
  const [exporting, setExporting] = useState(false)

  const highestStrength = signals.reduce(
    (best, item) => (item.relativeStrength > best.relativeStrength ? item : best),
    signals[0],
  )
  const xly = signals.find((item) => item.symbol === 'XLY')
  const xli = signals.find((item) => item.symbol === 'XLI')
  const spreadDivergence = xly && xli ? xly.dailyChange - xli.dailyChange : 0

  useEffect(() => {
    const run = () => {
      refresh()
      setUpdatedAt(new Date())
    }
    run()
    const interval = window.setInterval(run, POLL_INTERVAL_MS)
    startRealtime()
    return () => {
      window.clearInterval(interval)
      stopRealtime()
    }
  }, [refresh, startRealtime, stopRealtime])

  // Pro-only CSV export — backend rejects non-Pro users with 403.
  const handleExport = async () => {
    if (!token) return
    setExporting(true)
    try {
      const res = await fetch(`${BACKEND_URL}/api/export/history.csv`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(`Export failed (${res.status})`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'price-flow-history.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('[dashboard] export failed:', e)
    } finally {
      setExporting(false)
    }
  }

  const healthTone = scoreTone(qqqHealth.score)
  const fragTone = fragilityTone(fragilityMeter.level)
  const dirValue = qqqScore.direction === 'bullish' ? 1 : qqqScore.direction === 'bearish' ? -1 : 0
  const dirTone = trendTone(dirValue)
  const probabilityPct = Math.round((qqqScore.probability + 1) * 50)

  // --- trend regime (200-day SMA engine) — the backtested headline signal ---
  const regime = qqqScore.regime ?? 'unknown'
  const isRiskOn = regime === 'risk-on'
  const isRiskOff = regime === 'risk-off'
  const trendGap = qqqScore.trend_gap ?? qqqScore.raw_score ?? 0
  const regimeStyle = isRiskOn
    ? {
        label: 'RISK-ON',
        accent: 'text-emerald-400',
        dot: 'bg-emerald-400',
        grad: 'from-emerald-950/50 via-slate-900 to-slate-900',
        border: 'border-emerald-800/50',
        chip: 'bg-emerald-500/10 text-emerald-300',
        icon: '▲',
      }
    : isRiskOff
      ? {
          label: 'RISK-OFF',
          accent: 'text-rose-400',
          dot: 'bg-rose-400',
          grad: 'from-rose-950/50 via-slate-900 to-slate-900',
          border: 'border-rose-800/50',
          chip: 'bg-rose-500/10 text-rose-300',
          icon: '▼',
        }
      : {
          label: 'REGIME UNKNOWN',
          accent: 'text-slate-300',
          dot: 'bg-slate-500',
          grad: 'from-slate-900 via-slate-900 to-slate-900',
          border: 'border-slate-800',
          chip: 'bg-slate-500/10 text-slate-300',
          icon: '■',
        }

  return (
    <div className="space-y-6">
      {/* ---------------------------------------------------------- */}
      {/* hero                                                        */}
      {/* ---------------------------------------------------------- */}
      <div className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-cyan-950/40 p-6 shadow-glow sm:p-8">
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span
                  className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                    wsConnected ? 'animate-ping bg-emerald-400' : 'bg-slate-500'
                  }`}
                />
                <span
                  className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                    wsConnected ? 'bg-emerald-400' : 'bg-slate-500'
                  }`}
                />
              </span>
              <SectionLabel>
                {wsConnected ? 'Live · realtime feed' : 'Polling · 12s refresh'}
              </SectionLabel>
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
              QQQ &amp; Sector Leadership Analytics
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Relative strength, divergence, rolling correlations, lead/lag signals, fragility
              and AI concentration — all in one glance.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3">
              <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-500">Signed in</p>
              <p className="mt-0.5 max-w-[12rem] truncate text-sm font-medium text-white">
                {user?.email ?? 'Guest'}
              </p>
              <p className="mt-1 text-[0.7rem] text-slate-500">
                Updated {updatedAt.toLocaleTimeString()}
              </p>
            </div>
            <button
              onClick={() => {
                refresh()
                setUpdatedAt(new Date())
              }}
              disabled={loading}
              className="grid h-12 w-12 place-items-center rounded-2xl border border-slate-700 bg-slate-950/70 text-cyan-300 transition hover:border-cyan-500/50 hover:bg-slate-900 disabled:opacity-50"
              title="Refresh now"
            >
              <span className={`text-lg ${loading ? 'animate-spin' : ''}`}>↻</span>
            </button>
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------- */}
      {/* trend regime banner — the backtested headline signal        */}
      {/* ---------------------------------------------------------- */}
      <div
        className={`relative overflow-hidden rounded-3xl border bg-gradient-to-r p-6 shadow-glow sm:p-7 ${regimeStyle.border} ${regimeStyle.grad}`}
      >
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <span
              className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl text-2xl ${regimeStyle.chip}`}
            >
              {regimeStyle.icon}
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 rounded-full ${regimeStyle.dot} ${
                    isRiskOn || isRiskOff ? 'animate-pulse' : ''
                  }`}
                />
                <SectionLabel>Market trend regime</SectionLabel>
              </div>
              <h2 className={`mt-1 text-3xl font-bold tracking-tight ${regimeStyle.accent}`}>
                {regimeStyle.label}
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                {isRiskOn || isRiskOff ? (
                  <>
                    QQQ is{' '}
                    <strong className={regimeStyle.accent}>
                      {Math.abs(trendGap * 100).toFixed(1)}%{' '}
                      {trendGap >= 0 ? 'above' : 'below'}
                    </strong>{' '}
                    its {qqqScore.trend_window ?? 200}-day trend line.
                  </>
                ) : (
                  'Not enough price history to determine the trend regime.'
                )}
              </p>
            </div>
          </div>

          {(isRiskOn || isRiskOff) && (
            <div className="flex gap-6 rounded-2xl border border-slate-800 bg-slate-950/60 px-5 py-3">
              <div>
                <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-500">
                  QQQ price
                </p>
                <p className="mt-1 text-lg font-semibold text-white">
                  {qqqScore.price ? `$${qqqScore.price.toFixed(2)}` : '—'}
                </p>
              </div>
              <div>
                <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-500">
                  200-day trend
                </p>
                <p className="mt-1 text-lg font-semibold text-slate-300">
                  {qqqScore.sma ? `$${qqqScore.sma.toFixed(2)}` : '—'}
                </p>
              </div>
            </div>
          )}
        </div>

        <p className="relative mt-4 border-t border-slate-800/80 pt-3 text-xs leading-5 text-slate-500">
          Backtested 2014–2026: trading this regime matched buy-and-hold returns
          with a ~13-point shallower max drawdown (−22% vs −35%). It is a risk
          indicator, not a price prediction.
        </p>
      </div>

      {/* regime-change alert toggle (Pro only; renders nothing for free) */}
      <AlertToggle />

      {/* ---------------------------------------------------------- */}
      {/* KPI cards                                                   */}
      {/* ---------------------------------------------------------- */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {/* leadership */}
        <Card className="animate-fade-up p-5 transition hover:-translate-y-0.5 hover:border-slate-700">
          <div className="flex items-start justify-between">
            <SectionLabel>Top relative strength</SectionLabel>
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-cyan-500/10 text-cyan-300">
              ⚡
            </span>
          </div>
          <p className="mt-4 text-3xl font-semibold text-white">
            {highestStrength?.symbol ?? '—'}
          </p>
          <p className="mt-1 text-sm text-slate-400">{highestStrength?.name}</p>
          <div className="mt-4 flex items-center justify-between text-sm">
            <span className="text-slate-500">RS multiple</span>
            <span className="font-semibold text-cyan-300">
              {highestStrength?.relativeStrength.toFixed(2)}x
            </span>
          </div>
        </Card>

        {/* QQQ health */}
        <Card className="animate-fade-up p-5 transition hover:-translate-y-0.5 hover:border-slate-700">
          <div className="flex items-start justify-between">
            <SectionLabel>QQQ internal health</SectionLabel>
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-500/10 text-emerald-300">
              ❤
            </span>
          </div>
          <div className="mt-3 flex items-center gap-4">
            <Gauge
              value={qqqHealth.score}
              color={healthTone.ring}
              label={
                <div>
                  <p className={`text-xl font-bold ${healthTone.text}`}>{qqqHealth.score}</p>
                  <p className="text-[0.6rem] text-slate-500">/ 100</p>
                </div>
              }
            />
            <div className="min-w-0">
              <p className="text-sm font-medium capitalize text-white">{qqqHealth.regime}</p>
              <p className="mt-1 text-xs leading-5 text-slate-400 line-clamp-3">
                {qqqHealth.summary}
              </p>
            </div>
          </div>
        </Card>

        {/* fragility */}
        <Card
          className={`animate-fade-up p-5 transition hover:-translate-y-0.5 hover:border-slate-700`}
        >
          <div className="flex items-start justify-between">
            <SectionLabel>Fragility meter</SectionLabel>
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-amber-500/10 text-amber-300">
              ⚠
            </span>
          </div>
          <div className="mt-4 flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${fragTone.dot}`} />
            <p className={`text-2xl font-semibold capitalize ${fragTone.text}`}>
              {fragilityMeter.level}
            </p>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            {fragilityMeter.warnings.length} active warning
            {fragilityMeter.warnings.length === 1 ? '' : 's'}
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-400 line-clamp-2">
            {fragilityMeter.warnings[0] ?? 'No structural warnings detected.'}
          </p>
        </Card>

        {/* lead-lag */}
        <Card className="animate-fade-up p-5 transition hover:-translate-y-0.5 hover:border-slate-700">
          <div className="flex items-start justify-between">
            <SectionLabel>QQQ lead-lag score</SectionLabel>
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-500/10 text-indigo-300">
              🎯
            </span>
          </div>
          <p className={`mt-4 text-3xl font-semibold capitalize ${dirTone.text}`}>
            {qqqScore.direction}
          </p>
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">Probability</span>
              <span className="font-semibold text-slate-200">{probabilityPct}%</span>
            </div>
            <Meter value={probabilityPct} max={100} color={dirTone.bar} />
            <p className="text-[0.7rem] text-slate-500">
              Score {qqqScore.raw_score.toFixed(2)} · via {qqqScore.provider}
            </p>
          </div>
        </Card>
      </div>

      {/* ---------------------------------------------------------- */}
      {/* charts + sidebar — Pro                                      */}
      {/* ---------------------------------------------------------- */}
      <ProGate label="Sector analytics">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="space-y-6">
          {/* lead-lag + AI concentration */}
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="p-6">
              <SectionLabel>Lead / lag detection</SectionLabel>
              <h3 className="mt-3 text-xl font-semibold text-white">
                {leadLag.leader} <span className="text-slate-500">leads</span> {leadLag.lagger}
              </h3>
              <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-300">
                Confidence: {leadLag.confidence}
              </div>
              <ul className="mt-4 space-y-2">
                {leadLag.details.map((detail) => (
                  <li key={detail} className="flex gap-2 text-sm text-slate-300">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" />
                    <span>{detail}</span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card className="p-6">
              <SectionLabel>AI concentration meter</SectionLabel>
              <h3 className="mt-3 text-xl font-semibold text-white">Top drivers</h3>
              <div className="mt-4 space-y-2">
                {aiConcentration.topDrivers.map((driver, i) => (
                  <div
                    key={driver}
                    className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2.5"
                  >
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-indigo-500/15 text-xs font-bold text-indigo-300">
                      {i + 1}
                    </span>
                    <span className="text-sm text-slate-200">{driver}</span>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-400">{aiConcentration.summary}</p>
            </Card>
          </div>

          {/* QQQ vs sector charts */}
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <SectionLabel>QQQ vs sector leadership</SectionLabel>
                <h3 className="mt-2 text-lg font-semibold text-white">Price trajectory</h3>
              </div>
            </div>
            <div className="mt-6 grid gap-6 lg:grid-cols-2">
              {[
                { key: 'xlk', color: '#38bdf8', title: 'QQQ vs XLK (Technology)' },
                { key: 'smh', color: '#a78bfa', title: 'QQQ vs SMH (Semis)' },
              ].map((cfg) => (
                <div key={cfg.key} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="mb-2 text-xs font-medium text-slate-400">{cfg.title}</p>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={qqqComparison}>
                        <CartesianGrid stroke="#1e293b" strokeDasharray="4 4" />
                        <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={false} />
                        <YAxis tick={axisTick} tickLine={false} axisLine={false} width={40} />
                        <Tooltip content={<ChartTooltip />} />
                        <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
                        <Line
                          type="monotone"
                          dataKey="qqq"
                          stroke="#22d3ee"
                          strokeWidth={2.5}
                          dot={false}
                        />
                        <Line
                          type="monotone"
                          dataKey={cfg.key}
                          stroke={cfg.color}
                          strokeWidth={2.5}
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </section>

        {/* sidebar */}
        <aside className="space-y-6">
          <Card className="bg-gradient-to-br from-slate-900 to-indigo-950/40 p-6">
            <SectionLabel>Market regime analytics</SectionLabel>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              Rolling correlations, the XLY/XLP ratio, and breadth score reveal whether leadership
              is broadening or narrowing.
            </p>
          </Card>

          <Card className="p-5">
            <p className="text-xs font-medium text-slate-400">XLY / XLP ratio</p>
            <div className="mt-3 h-36">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={xlyXlpRatio}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="4 4" />
                  <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={false} />
                  <YAxis tick={axisTick} tickLine={false} axisLine={false} width={36} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="value" stroke="#22d3ee" strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card className="p-5">
            <p className="text-xs font-medium text-slate-400">Rolling correlations</p>
            <div className="mt-3 h-36">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rollingCorrelation}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="4 4" />
                  <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={false} />
                  <YAxis tick={axisTick} tickLine={false} axisLine={false} width={36} domain={[0.6, 1]} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="qqqXlk" stroke="#22d3ee" strokeWidth={2.5} dot={false} />
                  <Line type="monotone" dataKey="qqqSmh" stroke="#a78bfa" strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card className="p-5">
            <p className="text-xs font-medium text-slate-400">Breadth score</p>
            <div className="mt-3 h-36">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={breadthHistory}>
                  <defs>
                    <linearGradient id="breadthGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.7} />
                      <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="4 4" />
                  <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={false} />
                  <YAxis tick={axisTick} tickLine={false} axisLine={false} width={36} domain={[0.4, 1]} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#22d3ee"
                    fill="url(#breadthGradient)"
                    strokeWidth={2.5}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </aside>
      </div>
      </ProGate>

      {/* ---------------------------------------------------------- */}
      {/* ETF signal grid — Pro                                       */}
      {/* ---------------------------------------------------------- */}
      <ProGate label="ETF signal universe">
      <Card className="p-6">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <SectionLabel>ETF signal universe</SectionLabel>
            <h2 className="mt-2 text-lg font-semibold text-white">Live sector signal scan</h2>
          </div>
          <div className="flex items-center gap-3">
            {loading && (
              <span className="inline-flex items-center gap-2 rounded-full bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-300">
                <span className="h-1.5 w-1.5 animate-ping rounded-full bg-cyan-300" />
                Refreshing signals…
              </span>
            )}
            <button
              onClick={handleExport}
              disabled={exporting}
              className="rounded-full border border-slate-700 px-3.5 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-cyan-500/50 hover:bg-slate-800 disabled:opacity-60"
            >
              {exporting ? 'Exporting…' : '⤓ Export CSV'}
            </button>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {signals.map((signal) => {
            const tone = trendTone(signal.dailyChange)
            return (
              <div
                key={signal.symbol}
                className="group rounded-2xl border border-slate-800 bg-slate-950/60 p-5 transition hover:-translate-y-0.5 hover:border-slate-700 hover:bg-slate-900/80"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-lg font-bold tracking-tight text-white">{signal.symbol}</p>
                    <p className="truncate text-xs text-slate-400">{signal.name}</p>
                  </div>
                  <span
                    className={`shrink-0 rounded-lg px-2 py-1 text-xs font-bold ring-1 ${tone.bg} ${tone.text} ${tone.ring}`}
                  >
                    {signal.dailyChange > 0 ? '▲' : signal.dailyChange < 0 ? '▼' : '■'}{' '}
                    {signal.dailyChange > 0 ? '+' : ''}
                    {signal.dailyChange.toFixed(2)}%
                  </span>
                </div>

                <div className="mt-4 space-y-3">
                  <div>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="text-slate-500">Momentum</span>
                      <span className="font-medium text-slate-300">
                        {signal.momentumScore.toFixed(1)}/10
                      </span>
                    </div>
                    <Meter value={signal.momentumScore} max={10} color="bg-cyan-400" />
                  </div>
                  <div>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="text-slate-500">AI exposure</span>
                      <span className="font-medium text-slate-300">{signal.aiExposure}%</span>
                    </div>
                    <Meter value={signal.aiExposure} max={100} color="bg-indigo-400" />
                  </div>
                  <div className="flex items-center justify-between border-t border-slate-800 pt-3 text-xs">
                    <span className="text-slate-500">
                      RS <strong className="text-slate-200">{signal.relativeStrength.toFixed(2)}</strong>
                    </span>
                    <span className="text-slate-500">
                      Spread{' '}
                      <strong className={trendTone(signal.spreadDivergence).text}>
                        {signal.spreadDivergence > 0 ? '+' : ''}
                        {signal.spreadDivergence.toFixed(2)}%
                      </strong>
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-4 border-t border-slate-800 pt-4 text-xs text-slate-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-400" /> Positive
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-rose-400" /> Negative
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-cyan-400" /> Momentum
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-indigo-400" /> AI exposure
          </span>
          <span className="ml-auto">Spread divergence (XLY−XLI): {spreadDivergence >= 0 ? '+' : ''}{spreadDivergence.toFixed(2)}%</span>
        </div>
      </Card>
      </ProGate>
    </div>
  )
}
