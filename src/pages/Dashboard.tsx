import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  CartesianGrid,
  Tooltip,
  XAxis,
  YAxis,
  Area,
  AreaChart,
  ReferenceDot,
} from 'recharts'
import { useAuthStore } from '../store/useAuthStore'
import { useMarketStore } from '../store/useMarketStore'
import { deriveStabilityBadge, deriveHitRate } from '../data/marketSignals'
import { BACKEND_URL, POLL_INTERVAL_MS } from '../config'
import ProGate from '../components/ProGate'
import AlertToggle from '../components/AlertToggle'

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v))

/** Bucket the per-minute rolling-correlation series into 4-hour groups and
 * average each, so the bar chart shows a few wide grouped bars instead of a
 * dense line. Point names look like "MM-DD HH:MM". */
function bucket4hCorr(points: { name: string; qqqXlk: number; qqqSmh: number }[]) {
  const buckets = new Map<string, { name: string; xlk: number; smh: number; n: number }>()
  for (const p of points || []) {
    const m = (p.name || '').match(/(\d{2}-\d{2})\s+(\d{2}):/)
    const key = m ? `${m[1]} ${String(Math.floor(Number(m[2]) / 4) * 4).padStart(2, '0')}:00` : p.name
    const b = buckets.get(key) || { name: key, xlk: 0, smh: 0, n: 0 }
    if (Number.isFinite(p.qqqXlk)) b.xlk += p.qqqXlk
    if (Number.isFinite(p.qqqSmh)) b.smh += p.qqqSmh
    b.n += 1
    buckets.set(key, b)
  }
  return Array.from(buckets.values()).map((b) => ({
    name: b.name,
    qqqXlk: b.n ? Number((b.xlk / b.n).toFixed(3)) : 0,
    qqqSmh: b.n ? Number((b.smh / b.n).toFixed(3)) : 0,
  }))
}

/** display names for the tracked ETF universe (signal-universe tiles). */
const SECTOR_NAMES: Record<string, string> = {
  QQQ: 'Nasdaq-100', XLK: 'Technology', SMH: 'Semiconductors', SOXX: 'Semiconductors',
  MAGS: 'Magnificent 7', IGV: 'Software', XLY: 'Consumer Disc.', XLF: 'Financials',
  XLI: 'Industrials', IWM: 'Russell 2000', XLE: 'Energy', XLP: 'Cons. Staples',
  TLT: '20Y Treasuries',
}

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

/** small colour-key legend pinned to the bottom of a card */
function CardLegend({ items, note }: { items: { label: string; cls: string }[]; note?: string }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-slate-800/80 pt-2.5 text-[0.7rem] text-slate-400">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-full ${it.cls}`} />
          {it.label}
        </span>
      ))}
      {note && <span className="ml-auto text-slate-500">{note}</span>}
    </div>
  )
}

const ROLE_LEGEND = [
  { label: 'Leader', cls: 'bg-cyan-400' },
  { label: 'Confirmer', cls: 'bg-emerald-400' },
  { label: 'Diverging', cls: 'bg-rose-400' },
  { label: 'Weak', cls: 'bg-slate-500' },
]
const VERDICT_LEGEND = [
  { label: 'Continue', cls: 'bg-emerald-400' },
  { label: 'Stall', cls: 'bg-amber-400' },
  { label: 'Fragile', cls: 'bg-rose-400' },
]
const CONFIRM_LEGEND = [
  { label: 'Confirmed', cls: 'bg-emerald-400' },
  { label: 'Unconfirmed', cls: 'bg-amber-400' },
  { label: 'Fragile', cls: 'bg-rose-400' },
]
const REGIME_LEGEND = [
  { label: 'Coupled', cls: 'bg-emerald-400' },
  { label: 'Transitional', cls: 'bg-amber-400' },
  { label: 'Fragmented', cls: 'bg-rose-400' },
]
const BREADTH_LEGEND = [
  { label: 'Broad', cls: 'bg-emerald-400' },
  { label: 'Mixed', cls: 'bg-amber-400' },
  { label: 'Narrow', cls: 'bg-rose-400' },
]

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
      {children}
    </p>
  )
}

/** tiny "?" icon that reveals an explanation popup on hover / tap.
 * The popup is rendered in a portal on document.body so it floats above every
 * card — escaping card `overflow-hidden` clipping and per-card stacking contexts
 * that a plain absolutely-positioned tooltip can't break out of. */
function InfoTip({ text, align = 'center' }: { text: string; align?: 'left' | 'center' | 'right' }) {
  const TIP_W = 256 // w-64
  const btnRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState({ top: 0, left: 0 })

  const place = () => {
    const el = btnRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    // anchor the box's horizontal edge to the icon per `align`, then clamp on-screen
    let left =
      align === 'left'
        ? r.left
        : align === 'right'
          ? r.right - TIP_W
          : r.left + r.width / 2 - TIP_W / 2
    left = Math.max(8, Math.min(left, window.innerWidth - TIP_W - 8))
    setCoords({ top: r.bottom + 8, left })
  }

  const show = () => {
    place()
    setOpen(true)
  }
  const hide = () => setOpen(false)

  return (
    <span className="relative inline-flex">
      <button
        ref={btnRef}
        type="button"
        aria-label="What does this mean?"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        className="grid h-4 w-4 shrink-0 place-items-center rounded-full border border-slate-600 text-[0.6rem] font-bold leading-none text-slate-400 transition hover:border-cyan-400 hover:text-cyan-300 focus:border-cyan-400 focus:text-cyan-300 focus:outline-none"
      >
        ?
      </button>
      {open &&
        createPortal(
          <span
            role="tooltip"
            style={{ position: 'fixed', top: coords.top, left: coords.left, width: TIP_W }}
            className="pointer-events-none z-[100] rounded-xl border border-slate-700 bg-slate-950/95 p-3 text-left text-xs font-normal normal-case leading-5 tracking-normal text-slate-300 shadow-glow backdrop-blur"
          >
            {text}
          </span>,
          document.body,
        )}
    </span>
  )
}

/** label + question-mark tooltip on one line */
function LabeledSection({
  label,
  tip,
  align = 'center',
}: {
  label: ReactNode
  tip: string
  align?: 'left' | 'center' | 'right'
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <SectionLabel>{label}</SectionLabel>
      <InfoTip text={tip} align={align} />
    </span>
  )
}

/* tooltip copy — what each card shows and how to read it */
const TIPS = {
  relativeStrength:
    'The sector that\'s moved up the most in the last 30 minutes. Green = gaining, red = fading.',
  health:
    'A 0–100 score for how broad and healthy the move under QQQ is. Higher = more sectors are backing it, so the move is more trustworthy. Below 50 = narrow and shaky.',
  fragility:
    'How much hidden weakness is under the move. LOW = well supported. HIGH = the surface looks strong but it\'s weak underneath, so it\'s more likely to reverse.',
  leadLagScore:
    'A quick bullish / bearish read on where QQQ is leaning right now, with the chance it heads up.',
  aiDependency:
    'How much of QQQ\'s day-to-day move now comes from the AI build-out — memory, optics, networking, power and grid. The % is today\'s reading, the arrow shows if it\'s rising or falling versus a month ago, and the bars show which area QQQ leans on most. A big-picture trend, separate from the live intraday signals.',
  aiWindow:
    'How far back to measure which bottleneck QQQ is leaning on. Shorter windows catch recent shifts; longer ones show the bigger trend. 2 weeks is the floor — anything shorter is too few days to be reliable, so it gets noisy.',
  leadLagDetect:
    'Which sector reliably moves BEFORE QQQ, measured on 15-min (or 5-min) bars. A lead is only reported once it REPEATS on 3 bars in a row — so most of the time it honestly says "no repeating lead." "Broke ranks" flags a sector that usually moves with QQQ but just decoupled. The hit-rate below scores follow-through on the confirmed lead.',
  projection:
    'Where QQQ may be headed over the next few minutes, with a likely price range and whether the move should continue, stall, or is fragile.',
  attribution:
    'What\'s pushing QQQ right now — how much of its move comes from semis, software and mega-caps. "Explained" is how much these account for; the rest is everything else.',
  confirmation:
    'A quick pre-trade check. CONFIRMED = the move has broad sector backing. UNCONFIRMED = only a few sectors are in, so fade risk. FRAGILE = shaky underneath, trade with caution.',
  correlationRegime:
    'Whether the tech sectors are moving together right now. Together = the lead/lag and rotation signals are reliable. Doing their own thing = treat those signals as noise today.',
  stability:
    'Whether the same sector keeps leading day after day. TRADEABLE = a consistent leader. UNSTABLE = it keeps changing. GATHERING = not enough sessions yet.',
  hitRate:
    'How often QQQ actually followed the leader in the past. Compare it to the baseline — being above it is what counts.',
  rollingCorr:
    'How closely QQQ tracks XLK and SMH over time (1.0 = moving in lock-step). Falling = leadership is breaking down, often an early warning.',
  breadth:
    'How many of QQQ\'s ~100 stocks are rising. Equal-weight = how many names are up. Cap-weight = whether the big names are doing the lifting. Cap well above equal = a few giants carrying a narrow market; equal above cap = broad strength.',
  signalUniverse:
    'Live stats for each sector ETF — daily change, momentum and relative strength — so you can see which sectors agree or disagree with QQQ\'s move.',
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
  const token = useAuthStore((state) => state.token)
  const {
    rollingCorrelation,
    qqqHealth,
    prediction,
    loading,
    refresh,
    startRealtime,
    stopRealtime,
  } = useMarketStore()

  const [exporting, setExporting] = useState(false)
  // hit-rate horizon UI (component-local, not store). null = Auto (default).
  const [hitRateAuto, setHitRateAuto] = useState(true)
  const [hitRateHorizon, setHitRateHorizon] = useState<number | null>(null)
  // AI-dependency lookback window (by server-provided key, e.g. '1M'). Drives the
  // baseline comparison + the bottleneck ranking over that window. The headline %
  // (current dependency) stays stable; only the comparison and ranking re-window.
  const [aiWinKey, setAiWinKey] = useState<string>('1M')
  // lead/lag timeframe — 15m default (calmer); 5m faster/noisier; daily = cross-day.
  const [leadTf, setLeadTf] = useState<'5min' | '15min' | 'daily'>('15min')

  useEffect(() => {
    // background poll is silent (no loading flag) so the UI doesn't flicker/reflow
    // every cycle; the tool auto-refreshes, so there's no manual refresh button.
    const run = () => {
      refresh(true)
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

  // Intraday composite signal — the SAME engine as projection / health / lead-lag.
  // Every analytic card on the dashboard derives from this one intraday prediction
  // payload; there is no parallel long-term/daily logic in the UI.
  const composite = prediction?.score ?? null
  const compositeReady = prediction?.status === 'ok' && composite?.status === 'ok'
  const compositeProbPct = Math.round((composite?.probability_up ?? 0.5) * 100)
  const compositeScoreVal = composite?.score ?? 0
  const compositeDir = !compositeReady
    ? 'warming up'
    : compositeProbPct >= 55
      ? 'bullish'
      : compositeProbPct <= 45
        ? 'bearish'
        : 'neutral'
  const compositeTone = trendTone(
    compositeDir === 'bullish' ? 1 : compositeDir === 'bearish' ? -1 : 0,
  )

  // Intraday fragility — drives the Fragility-meter KPI (was placeholder before).
  const fragVal = composite?.components.fragility ?? 0
  const fragLevel = !compositeReady
    ? 'Unknown'
    : fragVal >= 0.5
      ? 'High'
      : fragVal >= 0.25
        ? 'Elevated'
        : 'Low'
  const fragTone = fragilityTone(fragLevel)
  const fragWarning =
    prediction?.confirmation?.message ||
    (prediction?.lead_lag?.diverging?.length
      ? `Diverging: ${prediction.lead_lag.diverging.join(', ')}.`
      : 'No structural warnings detected.')

  // --- AI-capex dependency (structural / daily — NOT intraday) ---
  const aiDep = prediction?.ai_dependency ?? null
  const aiDepReady = aiDep?.status === 'ok'
  const aiDepPct = Math.round((aiDep?.dependency_now ?? 0) * 100)
  const aiTrendFull = aiDep?.dependency_trend ?? []
  const aiAvail = aiTrendFull.length

  // windows are measured server-side (the client can't recompute coupling without
  // the raw daily returns). Pick the selected one; fall back to 1M then the last.
  const aiWindows = aiDep?.windows ?? []
  const aiWin =
    aiWindows.find((w) => w.key === aiWinKey) ??
    aiWindows.find((w) => w.key === '1M') ??
    aiWindows[aiWindows.length - 1]
  const aiWinDays = aiWin?.days ?? 21

  // change + sparkline zoom come from the rolling-dependency trend over `aiWinDays`
  const aiBaselineIdx = Math.max(0, aiAvail - 1 - aiWinDays)
  const aiNowVal = aiAvail ? aiTrendFull[aiAvail - 1].value : 0
  const aiBaseVal = aiAvail ? aiTrendFull[aiBaselineIdx].value : 0
  const aiChangePts = Math.round((aiNowVal - aiBaseVal) * 100)
  const aiWindowTrend = aiTrendFull.slice(aiBaselineIdx).map((p) => ({
    date: p.date,
    value: Math.round(p.value * 100),
  }))
  const aiPeriodLabel =
    aiWin?.key === 'all' ? 'inception' : `the last ${aiWin?.label ?? 'month'}`
  // strongest coupling over the SELECTED window — re-ranks as you change the window
  const aiWinThemes = (aiWin?.themes ?? []).filter((t) => t.corr != null)
  const aiMostCoupled = aiWinThemes[0]?.label
  const aiHookLine = aiDepReady
    ? `QQQ is ~${aiDepPct}% explained by the AI build-out — ${
        aiChangePts >= 0 ? 'up' : 'down'
      } ${Math.abs(aiChangePts)} pts over ${aiPeriodLabel}.${
        aiMostCoupled ? ` Most-coupled bottleneck: ${aiMostCoupled}.` : ''
      }`
    : ''
  // is today the highest dependency reading inside the selected window?
  const aiWindowMax = aiWindowTrend.length ? Math.max(...aiWindowTrend.map((p) => p.value)) : 0
  const aiAtHigh = aiWindowTrend.length > 3 && aiDepPct >= aiWindowMax

  // theme bars: coupling from the selected window, merged with the static member
  // metadata (which tickers fed it) carried on the top-level themes.
  const aiMemberMeta = new Map((aiDep?.themes ?? []).map((t) => [t.key, t]))
  const aiThemeBars = aiWinThemes.map((t) => ({
    name: t.label,
    tickers: (aiMemberMeta.get(t.key)?.members ?? [])
      .filter((m) => m.included)
      .map((m) => m.symbol),
    corr: Math.round((t.corr ?? 0) * 100),
    change: t.change,
    limited: t.limited,
  }))

  // --- intraday QQQ projection (measured lead/lag + composite score) ---
  const proj = prediction?.projection ?? null
  const projScore = prediction?.score ?? null
  const projReady = prediction?.status === 'ok' && proj != null && proj.status === 'ok'
  const verdict = projScore?.verdict ?? 'warming_up'
  const verdictStyle =
    verdict === 'continue'
      ? { label: 'Continue', text: 'text-emerald-400', chip: 'bg-emerald-500/10 text-emerald-300' }
      : verdict === 'fragile'
        ? { label: 'Fragile', text: 'text-rose-400', chip: 'bg-rose-500/10 text-rose-300' }
        : verdict === 'stall'
          ? { label: 'Stall', text: 'text-amber-400', chip: 'bg-amber-500/10 text-amber-300' }
          : { label: 'Warming up', text: 'text-slate-300', chip: 'bg-slate-500/10 text-slate-300' }
  const projDir = proj?.direction ?? 'flat'
  const dirArrow = projDir === 'up' ? '▲' : projDir === 'down' ? '▼' : '■'
  const dirText =
    projDir === 'up' ? 'text-emerald-400' : projDir === 'down' ? 'text-rose-400' : 'text-slate-300'
  const projDirTone = trendTone(projDir === 'up' ? 1 : projDir === 'down' ? -1 : 0)
  const projConfidencePct = Math.round((proj?.confidence ?? 0) * 100)
  const probUpPct = Math.round((projScore?.probability_up ?? 0.5) * 100)
  const barsCollected = prediction?.bars_used ?? 0

  // --- Phase 2 sections ---
  const attribution = prediction?.attribution ?? null
  const attributionReady = attribution?.status === 'ok'
  const confirmation = prediction?.confirmation ?? null
  const confirmationReady = confirmation?.status === 'ok'
  const corrRegime = prediction?.correlation_regime ?? null
  const corrRegimeReady = corrRegime?.status === 'ok'

  const stabilityBadge = deriveStabilityBadge(prediction)
  const hitRateView = deriveHitRate(prediction, {
    horizon: hitRateAuto ? null : hitRateHorizon,
  })

  const corrBars = bucket4hCorr(rollingCorrelation)

  // signal-universe tiles: tracked ETFs ranked by real 30-min momentum (top 8)
  const momentum30 = prediction?.score?.momentum_30m || {}
  const universeTiles = Object.entries(momentum30)
    .filter(([s]) => s !== (prediction?.target || 'QQQ'))
    .map(([s, m]) => ({ symbol: s, name: SECTOR_NAMES[s] || s, mom: Number(m) || 0 }))
    .sort((a, b) => b.mom - a.mom)
    .slice(0, 8)
  const universeMaxAbs = universeTiles.reduce((mx, t) => Math.max(mx, Math.abs(t.mom)), 0)
  const momLeader = universeTiles[0] ?? null  // strongest sector by 30m momentum (KPI)

  const breadth = prediction?.breadth ?? null
  const breadthReady = breadth?.status === 'ok'
  const breadthTone =
    breadth?.breadth_state === 'broad'
      ? 'emerald'
      : breadth?.breadth_state === 'mixed'
        ? 'amber'
        : 'rose'

  // tone -> tailwind classes for the small pills/badges
  const toneClasses = (tone: 'emerald' | 'amber' | 'rose' | 'slate') =>
    tone === 'emerald'
      ? { chip: 'bg-emerald-500/10 text-emerald-300', text: 'text-emerald-400', dot: 'bg-emerald-400' }
      : tone === 'amber'
        ? { chip: 'bg-amber-500/10 text-amber-300', text: 'text-amber-400', dot: 'bg-amber-400' }
        : tone === 'rose'
          ? { chip: 'bg-rose-500/10 text-rose-300', text: 'text-rose-400', dot: 'bg-rose-400' }
          : { chip: 'bg-slate-500/10 text-slate-300', text: 'text-slate-300', dot: 'bg-slate-500' }

  const confTone =
    confirmation?.state === 'confirmed'
      ? 'emerald'
      : confirmation?.state === 'fragile'
        ? 'rose'
        : 'amber'
  const regimeTone =
    corrRegime?.regime === 'coupled'
      ? 'emerald'
      : corrRegime?.regime === 'fragmented'
        ? 'rose'
        : 'amber'

  const stabilityToneCls = toneClasses(stabilityBadge.tone)

  // --- coarser-timeframe lead/lag (#2) + decoupling watch (#3) + streak (#4) ---
  const llFrame = prediction?.lead_lag_tf?.[leadTf]
  const llReady = llFrame?.status === 'ok'
  // only a STREAK-CONFIRMED lead is reported as the leader (kills one-off noise)
  const llLeader = llFrame?.confirmed_leader ?? null
  const llStreak = llFrame?.streak ?? null
  const llStreakMax = 3
  const llTarget = llFrame?.target ?? prediction?.target ?? 'QQQ'
  const llDecoupled = llFrame?.decoupled ?? []
  const llIsDaily = (llFrame?.bar_minutes ?? 0) >= 1440
  // format a lag: days for the daily frame, minutes otherwise
  const fmtLag = (lagMin: number) =>
    llIsDaily ? `${Math.round(lagMin / 1440)}d` : `${lagMin}m`

  return (
    <div className="space-y-4">
      {/* ---------------------------------------------------------- */}
      {/* QQQ intraday projection — measured lead/lag + composite      */}
      {/* ---------------------------------------------------------- */}
      <Card className="relative overflow-hidden p-5 sm:p-6">
        <div className="pointer-events-none absolute -left-16 -top-16 h-48 w-48 rounded-full bg-indigo-500/10 blur-3xl" />
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-indigo-500/10 text-lg text-indigo-300">
                🔮
              </span>
              <LabeledSection label="QQQ projection" tip={TIPS.projection} align="left" />
              {compositeReady && (
                <span
                  className={`ml-1 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${compositeTone.bg} ${compositeTone.text}`}
                  title="Intraday composite read — same engine that sets the direction below"
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${compositeTone.bar}`} />
                  {compositeDir} · {compositeProbPct}%
                </span>
              )}
            </div>

            {projReady ? (
              <>
                <div className="mt-2 flex items-center gap-3">
                  <span className={`text-3xl font-bold ${dirText}`}>{dirArrow}</span>
                  <div>
                    <p className="text-3xl font-semibold tracking-tight text-white">
                      ${proj!.projected_price.toFixed(2)}
                    </p>
                    <p className="text-sm text-slate-400">
                      from ${proj!.current_price.toFixed(2)} · {proj!.horizon_minutes}-min horizon
                    </p>
                  </div>
                  <span
                    className={`ml-1 inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${verdictStyle.chip}`}
                  >
                    {verdictStyle.label}
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-400">
                  Expected move{' '}
                  <strong className={dirText}>
                    {proj!.expected_return >= 0 ? '+' : ''}
                    {(proj!.expected_return * 100).toFixed(2)}%
                  </strong>{' '}
                  · band ${proj!.band_low.toFixed(2)} – ${proj!.band_high.toFixed(2)} ·{' '}
                  basis {proj!.basis.replace(/_/g, ' ')}
                </p>
              </>
            ) : (
              <>
                <h2 className="mt-3 text-2xl font-bold tracking-tight text-slate-300">
                  Warming up
                </h2>
                <p className="mt-1 text-sm text-slate-400">
                  {barsCollected} bar{barsCollected === 1 ? '' : 's'} collected this session —
                  projection appears once enough intraday data accumulates.
                </p>
              </>
            )}
          </div>

          {projReady && (
            <div className="flex gap-6 rounded-2xl border border-slate-800 bg-slate-950/60 px-5 py-4">
              <div className="min-w-[88px]">
                <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-400">
                  Direction
                </p>
                <p className={`mt-1 text-lg font-semibold capitalize ${dirText}`}>{projDir}</p>
              </div>
              <div className="min-w-[88px]">
                <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-400">Prob. up</p>
                <p className="mt-1 text-lg font-semibold text-white">{probUpPct}%</p>
                <Meter value={probUpPct} max={100} color={projDirTone.bar} />
              </div>
              <div className="min-w-[88px]">
                <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-400">
                  Confidence
                </p>
                <p className="mt-1 text-lg font-semibold text-white">{projConfidencePct}%</p>
                <Meter value={projConfidencePct} max={100} color="bg-indigo-400" />
              </div>
            </div>
          )}
        </div>
        {projReady && (
          <CardLegend items={VERDICT_LEGEND} note="verdict · ▲ up  ■ flat  ▼ down" />
        )}
      </Card>

      {/* ---------------------------------------------------------- */}
      {/* KPI cards                                                   */}
      {/* ---------------------------------------------------------- */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {/* leadership */}
        <Card className="animate-fade-up p-4 transition hover:-translate-y-0.5 hover:border-slate-700">
          <div className="flex items-start justify-between">
            <LabeledSection label="Strongest sector · 30m" tip={TIPS.relativeStrength} align="left" />
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-cyan-500/10 text-cyan-300">
              ⚡
            </span>
          </div>
          <p className="mt-4 text-3xl font-semibold text-white">
            {momLeader?.symbol ?? '—'}
          </p>
          <p className="mt-1 text-sm text-slate-400">{momLeader?.name ?? 'Warming up'}</p>
          <div className="mt-4 flex items-center justify-between text-sm">
            <span className="text-slate-400">30-min momentum</span>
            <span className={`font-semibold ${momLeader && momLeader.mom < 0 ? 'text-rose-300' : 'text-cyan-300'}`}>
              {momLeader ? `${momLeader.mom >= 0 ? '+' : ''}${(momLeader.mom * 100).toFixed(2)}%` : '—'}
            </span>
          </div>
        </Card>

        {/* QQQ health */}
        <Card className="animate-fade-up p-4 transition hover:-translate-y-0.5 hover:border-slate-700">
          <div className="flex items-start justify-between">
            <LabeledSection label="QQQ internal health" tip={TIPS.health} align="left" />
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
                  <p className="text-[0.6rem] text-slate-400">/ 100</p>
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
          className={`animate-fade-up p-4 transition hover:-translate-y-0.5 hover:border-slate-700`}
        >
          <div className="flex items-start justify-between">
            <LabeledSection label="Fragility meter" tip={TIPS.fragility} align="left" />
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-amber-500/10 text-amber-300">
              ⚠
            </span>
          </div>
          <div className="mt-4 flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${fragTone.dot}`} />
            <p className={`text-2xl font-semibold capitalize ${fragTone.text}`}>{fragLevel}</p>
          </div>
          <p className="mt-3 text-xs text-slate-400">
            {compositeReady ? `${Math.round(fragVal * 100)}% internal fragility` : 'Warming up'}
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-400 line-clamp-2">{fragWarning}</p>
        </Card>
      </div>

      {/* ---------------------------------------------------------- */}
      {/* AI-capex dependency — flagship structural read (daily)      */}
      {/* ---------------------------------------------------------- */}
      <Card className="relative overflow-hidden p-5 sm:p-6">
        <div className="pointer-events-none absolute -right-20 -top-20 h-52 w-52 rounded-full bg-fuchsia-500/10 blur-3xl" />
        <div className="relative">
          <div className="flex items-center gap-2">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-fuchsia-500/10 text-lg text-fuchsia-300">
              🧠
            </span>
            <LabeledSection label="AI build-out dependency" tip={TIPS.aiDependency} align="left" />
            <span className="ml-1 rounded-full bg-slate-800/80 px-2 py-0.5 text-[0.6rem] font-semibold uppercase tracking-[0.18em] text-slate-400">
              Structural · daily
            </span>
            {aiDepReady && aiWindows.length > 0 && (
              <label className="ml-auto flex items-center gap-1.5 text-[0.7rem] text-slate-400">
                <span className="inline-flex items-center gap-1">
                  <span className="hidden sm:inline">Window</span>
                  <InfoTip text={TIPS.aiWindow} align="right" />
                </span>
                <select
                  value={aiWin?.key ?? '1M'}
                  onChange={(e) => setAiWinKey(e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-950/70 px-2 py-1 text-xs font-medium text-slate-200 outline-none transition hover:border-slate-500 focus:border-fuchsia-400"
                >
                  {aiWindows.map((w) => (
                    <option key={w.key} value={w.key}>
                      {w.key === 'all' ? 'Since inception' : w.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {aiDepReady ? (
            <div className="mt-3 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
              {/* left: headline number + trend */}
              <div>
                <div className="flex flex-wrap items-end gap-x-3 gap-y-1.5">
                  <p className="text-5xl font-bold tracking-tight text-white">{aiDepPct}%</p>
                  <span
                    className={`mb-1.5 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                      aiChangePts > 0
                        ? 'bg-emerald-500/10 text-emerald-300'
                        : aiChangePts < 0
                          ? 'bg-rose-500/10 text-rose-300'
                          : 'bg-slate-700/40 text-slate-300'
                    }`}
                  >
                    {aiChangePts >= 0 ? '▲' : '▼'} {Math.abs(aiChangePts)} pts (
                    {Math.round(aiBaseVal * 100)}%) over {aiPeriodLabel}
                  </span>
                  {aiAtHigh && (
                    <span className="mb-1.5 inline-flex items-center gap-1 rounded-full bg-fuchsia-500/15 px-2 py-0.5 text-xs font-semibold text-fuchsia-200">
                      ◆ highest {aiWin?.key === 'all' ? 'on record' : `in ${aiWin?.label}`}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-slate-400">
                  of QQQ&apos;s daily move is explained by the AI build-out complex
                </p>
                <div className="mt-3 h-24">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={aiWindowTrend} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="aiDepFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#e879f9" stopOpacity={0.5} />
                          <stop offset="100%" stopColor="#e879f9" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <YAxis domain={[0, 100]} hide />
                      <XAxis dataKey="date" hide />
                      <Tooltip
                        contentStyle={{
                          background: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: 12,
                          fontSize: 12,
                        }}
                        labelStyle={{ color: '#94a3b8' }}
                        formatter={(v: number) => [`${v}%`, 'dependency']}
                      />
                      <Area
                        type="monotone"
                        dataKey="value"
                        stroke="#e879f9"
                        strokeWidth={2}
                        fill="url(#aiDepFill)"
                        isAnimationActive={false}
                      />
                      {/* baseline marker — anchors the "vs X" comparison visually */}
                      {aiWindowTrend.length > 1 && (
                        <ReferenceDot
                          x={aiWindowTrend[0].date}
                          y={aiWindowTrend[0].value}
                          r={3.5}
                          fill="#64748b"
                          stroke="#0f172a"
                          strokeWidth={2}
                          isFront
                        />
                      )}
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-3 text-[0.95rem] font-medium leading-6 text-slate-100">
                  {aiHookLine}
                </p>
              </div>

              {/* right: per-bottleneck coupling over the selected window */}
              <div>
                <p className="flex items-center gap-2 text-[0.65rem] uppercase tracking-[0.2em] text-slate-400">
                  Coupling to QQQ by bottleneck · {aiWin?.label ?? '1 month'}
                  {aiWin && !aiWin.reliable && (
                    <span className="rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[0.55rem] font-medium normal-case tracking-normal text-amber-300/90">
                      short window · noisier
                    </span>
                  )}
                </p>
                <div className="mt-3 space-y-2.5">
                  {aiThemeBars.map((t) => (
                    <div key={t.name}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-slate-300">
                          {t.name}
                          {t.tickers.length > 0 && (
                            <span className="ml-1 text-[0.65rem] text-slate-500">
                              ({t.tickers.join(', ')})
                            </span>
                          )}
                          {t.limited && (
                            <span className="ml-1.5 text-[0.6rem] text-amber-300/80">
                              limited history
                            </span>
                          )}
                        </span>
                        <span className="font-semibold text-slate-200">
                          {t.corr}%
                          <span
                            className={`ml-1.5 ${
                              t.change > 0.02
                                ? 'text-emerald-300'
                                : t.change < -0.02
                                  ? 'text-rose-300'
                                  : 'text-slate-500'
                            }`}
                          >
                            {t.change >= 0 ? '▲' : '▼'}
                          </span>
                        </span>
                      </div>
                      <Meter value={Math.abs(t.corr)} max={100} color="bg-fuchsia-400" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-400">
              Warming up — gathering daily history to measure how dependent QQQ has become on the
              AI build-out complex.
            </p>
          )}
        </div>
      </Card>

      {/* ---------------------------------------------------------- */}
      {/* charts + sidebar — Pro                                      */}
      {/* ---------------------------------------------------------- */}
      <ProGate label="Sector analytics">
      <div className="grid gap-6 lg:grid-cols-2">
          {/* lead-lag — full-width hero */}
          <div className="lg:col-span-2">
            <Card className="p-6">
              <div className="flex items-start justify-between gap-3">
                <LabeledSection label="Lead / lag detection" tip={TIPS.leadLagDetect} align="left" />
                {/* timeframe toggle — 15m default (calmer), 5m faster but noisier */}
                <div className="flex items-center gap-1 rounded-full border border-slate-800 bg-slate-950/60 p-0.5">
                  {(['5min', '15min', 'daily'] as const).map((tf) => (
                    <button
                      key={tf}
                      onClick={() => setLeadTf(tf)}
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold transition ${
                        leadTf === tf
                          ? 'bg-cyan-500/15 text-cyan-200'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {tf === '15min' ? '15m' : tf === '5min' ? '5m' : 'Daily'}
                    </button>
                  ))}
                </div>
              </div>
              {leadTf === '5min' && (
                <p className="mt-1.5 text-[0.7rem] text-amber-300/80">
                  5-min frame reacts faster but is noisier — more false leads. 15m is steadier.
                </p>
              )}
              {leadTf === 'daily' && (
                <p className="mt-1.5 text-[0.7rem] text-slate-500">
                  Cross-day: measured over ~1 year of daily bars — where a multi-day lead would
                  show up if one exists.
                </p>
              )}
              {llReady && llLeader ? (
                <h3 className="mt-3 text-xl font-semibold text-white">
                  {llLeader.symbol} <span className="text-slate-400">leads</span> {llTarget}{' '}
                  <span className="text-slate-400">by</span> {fmtLag(llLeader.lag_minutes)}
                  <span className="ml-2 rounded-full bg-cyan-500/15 px-2 py-0.5 text-[0.65rem] font-semibold text-cyan-200">
                    {llIsDaily ? 'cross-day' : `confirmed ×${llStreak?.count ?? llStreakMax}`}
                  </span>
                </h3>
              ) : llReady && llStreak && llStreak.symbol && llStreak.count > 0 ? (
                <h3 className="mt-3 text-xl font-semibold text-slate-300">
                  Possible lead: {llStreak.symbol}{' '}
                  <span className="text-sm font-medium text-amber-300/90">
                    confirming {llStreak.count}/{llStreakMax}…
                  </span>
                </h3>
              ) : (
                <h3 className="mt-3 text-xl font-semibold text-slate-300">
                  {llReady ? 'No repeating lead — sectors moving together' : 'Warming up'}
                </h3>
              )}
              {/* decoupling watch — a usual driver that broke ranks now */}
              {llDecoupled.length > 0 && (
                <p className="mt-2 text-xs leading-5 text-amber-300">
                  ⚠ Broke ranks:{' '}
                  {llDecoupled
                    .slice(0, 3)
                    .map(
                      (d) =>
                        `${d.symbol} (usually ${Math.round(d.usual_corr * 100)}% → now ${Math.round(
                          d.now_corr * 100,
                        )}%)`,
                    )
                    .join(', ')}
                </p>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-300">
                  {llLeader ? `Coupling: ${Math.round(llLeader.corr * 100)}%` : `Frame: ${leadTf === '15min' ? '15-min' : '5-min'}`}
                </span>
                {/* cross-session stability badge (#2) */}
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${stabilityToneCls.chip}`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${stabilityToneCls.dot}`} />
                  Stability: {stabilityBadge.label}
                  <InfoTip text={TIPS.stability} align="left" />
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-400">{stabilityBadge.message}</p>

              {/* hit-rate / continuation probability (#4) — horizon Auto toggle */}
              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1.5 text-[0.7rem] font-semibold uppercase tracking-[0.2em] text-cyan-300/80">
                    Hit rate
                    <InfoTip text={TIPS.hitRate} align="left" />
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        if (hitRateAuto) {
                          // turning Auto OFF -> always have a concrete horizon selected
                          // (default to the first option, 5m) so it evaluates a real window
                          setHitRateHorizon((h) => h ?? hitRateView.horizonOptions[0] ?? 5)
                          setHitRateAuto(false)
                        } else {
                          setHitRateAuto(true)
                        }
                      }}
                      className={`rounded-full px-2.5 py-1 text-[0.7rem] font-semibold transition ${
                        hitRateAuto
                          ? 'bg-cyan-500/15 text-cyan-300'
                          : 'border border-slate-700 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Auto{hitRateAuto && hitRateView.ready ? ` · ~${hitRateView.horizonMinutes}m` : ''}
                    </button>
                    {!hitRateAuto && (
                      <select
                        value={hitRateHorizon ?? hitRateView.horizonOptions[0] ?? 5}
                        onChange={(e) => setHitRateHorizon(Number(e.target.value))}
                        className="rounded-full border border-slate-700 bg-slate-950 px-2.5 py-1 text-[0.7rem] font-semibold text-slate-200 focus:border-cyan-500/50 focus:outline-none"
                      >
                        {hitRateView.horizonOptions.map((h) => (
                          <option key={h} value={h}>
                            {h}m
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>
                {hitRateView.ready ? (
                  <>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span
                        className={`text-2xl font-semibold ${
                          hitRateView.edge > 0 ? 'text-emerald-400' : 'text-slate-300'
                        }`}
                      >
                        {hitRateView.hitRatePct}%
                      </span>
                      <span className="text-xs text-slate-400">{hitRateView.line}</span>
                    </div>
                  </>
                ) : (
                  <p className="mt-2 text-xs text-slate-400">{hitRateView.line}</p>
                )}
              </div>

              {llReady && (llFrame?.entries.length ?? 0) > 0 && (
                <>
                <div className="mt-4 overflow-hidden rounded-xl border border-slate-800">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950/60 text-slate-400">
                      <tr>
                        <th className="px-3 py-2 font-medium">Symbol</th>
                        <th className="px-3 py-2 font-medium">Role</th>
                        <th className="px-3 py-2 text-right font-medium">
                          Lead ({llIsDaily ? 'days' : 'min'})
                        </th>
                        <th className="px-3 py-2 text-right font-medium">Corr</th>
                      </tr>
                    </thead>
                    <tbody>
                      {llFrame!.entries.slice(0, 6).map((entry) => {
                        const roleTone =
                          entry.role === 'leader'
                            ? 'text-cyan-300'
                            : entry.role === 'confirmer'
                              ? 'text-emerald-300'
                              : entry.role === 'diverging'
                                ? 'text-rose-300'
                                : 'text-slate-400'
                        return (
                          <tr key={entry.symbol} className="border-t border-slate-800/80">
                            <td className="px-3 py-2 font-semibold text-slate-200">
                              {entry.symbol}
                            </td>
                            <td className={`px-3 py-2 capitalize ${roleTone}`}>{entry.role}</td>
                            <td className="px-3 py-2 text-right text-slate-300">
                              {fmtLag(entry.lag_minutes ?? entry.best_lag * (llFrame?.bar_minutes ?? 1))}
                            </td>
                            <td className="px-3 py-2 text-right text-slate-300">
                              {entry.best_corr.toFixed(2)}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
                <CardLegend
                  items={ROLE_LEGEND}
                  note="Lead = min ahead of QQQ · 0 = coincident"
                />
                </>
              )}

              {prediction?.status !== 'ok' && (
                <p className="mt-4 text-xs text-slate-400">
                  {barsCollected} bar{barsCollected === 1 ? '' : 's'} collected this session.
                </p>
              )}
            </Card>
          </div>

          {/* Confirmation gate (#3) — the pre-trade card */}
          <Card className="p-6">
            <LabeledSection label="Confirmation gate" tip={TIPS.confirmation} align="left" />
            {confirmationReady && confirmation ? (
              <>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <span
                    className={`inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-sm font-bold uppercase tracking-wide ${toneClasses(confTone).chip}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${toneClasses(confTone).dot}`} />
                    {confirmation.state}
                  </span>
                  <span className="text-sm text-slate-400">
                    QQQ <span className="capitalize text-slate-200">{confirmation.target_direction}</span>
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-300">{confirmation.message}</p>
                <div className="mt-4 grid grid-cols-3 gap-3 text-center">
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2">
                    <p className="text-[0.6rem] uppercase tracking-[0.2em] text-slate-400">Participation</p>
                    <p className="mt-1 text-lg font-semibold text-white">
                      {confirmation.participating_count}/{confirmation.universe_count}
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2">
                    <p className="text-[0.6rem] uppercase tracking-[0.2em] text-slate-400">Leaders agree</p>
                    <p
                      className={`mt-1 text-lg font-semibold ${
                        confirmation.leaders_agree ? 'text-emerald-400' : 'text-slate-300'
                      }`}
                    >
                      {confirmation.leaders_agree ? 'Yes' : 'No'}
                    </p>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2">
                    <p className="text-[0.6rem] uppercase tracking-[0.2em] text-slate-400">Fragility</p>
                    <p className="mt-1 text-lg font-semibold text-white">
                      {Math.round(confirmation.fragility * 100)}%
                    </p>
                  </div>
                </div>
                <CardLegend items={CONFIRM_LEGEND} note="state of the current QQQ move" />
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                Warming up — the confirmation gate appears once enough intraday momentum is measured.
              </p>
            )}
          </Card>

          {/* Driver attribution (#1) — what's moving QQQ */}
          <Card className="p-6">
            <LabeledSection label="What's moving QQQ" tip={TIPS.attribution} align="left" />
            {attributionReady && attribution ? (
              <>
                <p className="mt-3 text-sm leading-6 text-slate-200">{attribution.headline}</p>
                <ul className="mt-4 space-y-3">
                  {attribution.contributors.map((c) => {
                    const pct = Math.round(Math.abs(c.share) * 100)
                    const tone =
                      c.share > 0 ? 'bg-cyan-400' : c.share < 0 ? 'bg-rose-400' : 'bg-slate-500'
                    return (
                      <li key={c.symbol}>
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-medium text-slate-200">
                            {c.label}{' '}
                            <span className="text-slate-500">({c.symbol})</span>
                            <span className="ml-1.5 capitalize text-slate-400">· {c.trend}</span>
                          </span>
                          <span className="font-semibold text-slate-300">
                            {c.share >= 0 ? '' : '−'}
                            {pct}%
                          </span>
                        </div>
                        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                          <div
                            className={`h-full rounded-full ${tone}`}
                            style={{ width: `${clamp(pct, 2, 100)}%`, transition: 'width 0.6s ease' }}
                          />
                        </div>
                      </li>
                    )
                  })}
                </ul>
                <p className="mt-4 border-t border-slate-800/80 pt-3 text-xs text-slate-400">
                  Explained{' '}
                  <strong className="text-slate-200">
                    {Math.round(attribution.explained_share * 100)}%
                  </strong>{' '}
                  · residual {Math.round(attribution.residual_share * 100)}% · over{' '}
                  {attribution.window_minutes}m
                </p>
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                Warming up — attribution appears once enough 1-minute bars accumulate.
              </p>
            )}
          </Card>

          {/* Nasdaq-100 breadth — real constituent participation */}
          <Card className="p-6">
            <div className="flex items-start justify-between gap-3">
              <LabeledSection label="QQQ breadth · 100 stocks" tip={TIPS.breadth} align="left" />
              {/* breadth-shift email alerts live here — this is what the alert tracks */}
              <AlertToggle compact />
            </div>
            {breadthReady && breadth ? (
              <>
                <div className="mt-3 flex items-center justify-between">
                  <span
                    className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ${toneClasses(breadthTone).chip}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${toneClasses(breadthTone).dot}`} />
                    {breadth.breadth_state}
                  </span>
                  <span className="text-xs text-slate-400">
                    {breadth.advancers}/{breadth.measured} advancing
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2.5">
                    <p className="text-[0.6rem] uppercase tracking-[0.2em] text-slate-400">Equal-weight</p>
                    <p className="mt-1 text-2xl font-semibold text-white">
                      {Math.round(breadth.equal_weight_pct * 100)}%
                    </p>
                    <p className="text-[0.6rem] text-slate-400">names advancing</p>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2.5">
                    <p className="text-[0.6rem] uppercase tracking-[0.2em] text-slate-400">Cap-weight</p>
                    <p className="mt-1 text-2xl font-semibold text-white">
                      {Math.round(breadth.cap_weight_pct * 100)}%
                    </p>
                    <p className="text-[0.6rem] text-slate-400">of index weight</p>
                  </div>
                </div>
                <p className="mt-3 text-xs leading-5 text-slate-400">{breadth.message}</p>
                <CardLegend items={BREADTH_LEGEND} note="participation across the 100 stocks" />
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                Breadth warming up — fetching the Nasdaq-100 constituents.
              </p>
            )}
          </Card>

          {/* Correlation regime (#5) — are sector signals even valid today */}
          <Card className="p-6">
            <LabeledSection label="Correlation regime" tip={TIPS.correlationRegime} align="left" />
            {corrRegimeReady && corrRegime ? (
              <>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <span
                    className={`inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-sm font-bold uppercase tracking-wide ${toneClasses(regimeTone).chip}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${toneClasses(regimeTone).dot}`} />
                    {corrRegime.regime}
                  </span>
                  <span className="text-sm text-slate-400">
                    avg corr{' '}
                    <strong className="text-slate-200">
                      {corrRegime.avg_pairwise_corr.toFixed(2)}
                    </strong>
                  </span>
                </div>
                <p
                  className={`mt-3 text-sm font-medium ${
                    corrRegime.signals_reliable ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {corrRegime.signals_reliable
                    ? 'Signals reliable — lead/lag and rotation are meaningful.'
                    : 'Treat lead/lag as noise today.'}
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-400">{corrRegime.message}</p>
                <CardLegend items={REGIME_LEGEND} note="how tightly tech sectors move together" />
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-400">
                Warming up — the correlation regime appears once enough bars accumulate.
              </p>
            )}
          </Card>

          {/* Rolling correlations — QQQ·XLK vs QQQ·SMH, grouped 4h bars */}
          <Card className="p-6 lg:col-span-2">
            <span className="inline-flex items-center gap-1.5">
              <SectionLabel>Rolling correlations · 4h</SectionLabel>
              <InfoTip text={TIPS.rollingCorr} align="left" />
            </span>
            <h3 className="mt-2 text-lg font-semibold text-white">How tightly QQQ tracks its leaders</h3>
            <div className="mt-4 h-60">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={corrBars} barGap={4} barCategoryGap="22%">
                  <CartesianGrid stroke="#1e293b" strokeDasharray="4 4" vertical={false} />
                  <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={false} />
                  <YAxis tick={axisTick} tickLine={false} axisLine={false} width={36} domain={[0, 1]} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="qqqXlk" name="QQQ·XLK" fill="#22d3ee" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  <Bar dataKey="qqqSmh" name="QQQ·SMH" fill="#a78bfa" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-cyan-400" /> QQQ · XLK (tech)
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-violet-400" /> QQQ · SMH (semis)
              </span>
              <span className="ml-auto">1.0 = moving in lock-step · 4-hour buckets</span>
            </div>
          </Card>
      </div>
      </ProGate>

      {/* ---------------------------------------------------------- */}
      {/* ETF signal grid — Pro                                       */}
      {/* ---------------------------------------------------------- */}
      <ProGate label="ETF signal universe">
      <Card className="p-6">
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <LabeledSection label="ETF signal universe" tip={TIPS.signalUniverse} align="left" />
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

        {universeTiles.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {universeTiles.map((t) => {
              const tone = trendTone(t.mom)
              const barPct = universeMaxAbs > 0 ? (Math.abs(t.mom) / universeMaxAbs) * 100 : 0
              return (
                <div
                  key={t.symbol}
                  className="group rounded-2xl border border-slate-800 bg-slate-950/60 p-5 transition hover:-translate-y-0.5 hover:border-slate-700 hover:bg-slate-900/80"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-lg font-bold tracking-tight text-white">{t.symbol}</p>
                      <p className="truncate text-xs text-slate-400">{t.name}</p>
                    </div>
                    <span
                      className={`shrink-0 rounded-lg px-2 py-1 text-xs font-bold ring-1 ${tone.bg} ${tone.text} ${tone.ring}`}
                    >
                      {t.mom > 0 ? '▲' : t.mom < 0 ? '▼' : '■'} {t.mom >= 0 ? '+' : ''}
                      {(t.mom * 100).toFixed(2)}%
                    </span>
                  </div>
                  <div className="mt-4">
                    <p className="mb-1 text-[0.6rem] uppercase tracking-[0.2em] text-slate-400">
                      30-min momentum
                    </p>
                    <Meter value={barPct} max={100} color={t.mom >= 0 ? 'bg-cyan-400' : 'bg-rose-400'} />
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <p className="text-sm text-slate-400">
            Warming up — ranking the tracked ETFs by 30-minute momentum once enough bars accumulate.
          </p>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-4 border-t border-slate-800 pt-4 text-xs text-slate-400">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-cyan-400" /> Gaining (30m)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-rose-400" /> Fading (30m)
          </span>
          <span className="ml-auto">
            Top {universeTiles.length} of {Object.keys(momentum30).length} tracked ETFs by momentum
          </span>
        </div>
      </Card>
      </ProGate>
    </div>
  )
}
