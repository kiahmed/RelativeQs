import { useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type {
  RotationData,
  RotationRow,
  RotationTag,
  RotationWindow,
} from '../data/marketSignals'

/* ------------------------------------------------------------------ */
/* local presentational helpers — mirror the Dashboard.tsx patterns     */
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

/** "?" icon that reveals an explanation popup (portal'd to body so it floats). */
function InfoTip({ text, align = 'center' }: { text: string; align?: 'left' | 'center' | 'right' }) {
  const TIP_W = 288 // w-72 — this copy is long
  const btnRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState({ top: 0, left: 0 })

  const place = () => {
    const el = btnRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
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

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
      {children}
    </p>
  )
}

/* ------------------------------------------------------------------ */
/* copy                                                                 */
/* ------------------------------------------------------------------ */

const FLOW_TIP =
  'Educated inference, NOT actual fund flows. Intraday flows can\'t be measured directly ' +
  '(creations/redemptions are end-of-day). Inferred from relative move + dollar-volume across a ' +
  'tracked set; money can also go to cash or untracked names ("unaccounted"). XLK/SMH excluded ' +
  'because they ARE QQQ.'

const WINDOWS: { key: string; label: string }[] = [
  { key: '15m', label: '15m' },
  { key: '30m', label: '30m' },
  { key: '60m', label: '60m' },
]

const LEGEND: { label: string; cls: string }[] = [
  { label: 'In — absorbing money', cls: 'bg-emerald-400' },
  { label: 'Out — shedding', cls: 'bg-rose-400' },
  { label: 'Neutral — no volume-backed move', cls: 'bg-slate-500' },
]

/* ------------------------------------------------------------------ */
/* tag styling                                                          */
/* ------------------------------------------------------------------ */

function tagStyle(tag: RotationTag) {
  if (tag === 'in')
    return {
      cell: 'border-emerald-500/40 bg-emerald-500/10 hover:border-emerald-400/70',
      sym: 'text-emerald-200',
      rel: 'text-emerald-300',
      dot: 'bg-emerald-400',
    }
  if (tag === 'out')
    return {
      cell: 'border-rose-500/40 bg-rose-500/10 hover:border-rose-400/70',
      sym: 'text-rose-200',
      rel: 'text-rose-300',
      dot: 'bg-rose-400',
    }
  return {
    cell: 'border-slate-700/70 bg-slate-800/30 hover:border-slate-600',
    sym: 'text-slate-300',
    rel: 'text-slate-400',
    dot: 'bg-slate-500',
  }
}

function fmtPct(v: number | null | undefined, withSign = true) {
  if (v == null || !Number.isFinite(v)) return '—'
  const pct = v * 100
  const sign = withSign && pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

function fmtSurge(v: number | null | undefined) {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${v.toFixed(1)}×`
}

function regimeStyle(regime: RotationWindow['regime']) {
  switch (regime) {
    case 'rotating':
      return { chip: 'bg-cyan-500/15 text-cyan-200', dot: 'bg-cyan-400', label: 'Rotating' }
    case 'coupled':
      return { chip: 'bg-indigo-500/15 text-indigo-200', dot: 'bg-indigo-400', label: 'Coupled' }
    case 'flat':
      return { chip: 'bg-slate-700/50 text-slate-300', dot: 'bg-slate-400', label: 'Flat' }
    default:
      return { chip: 'bg-slate-700/50 text-slate-300', dot: 'bg-slate-500', label: 'Warming up' }
  }
}

/* ------------------------------------------------------------------ */
/* one instrument cell                                                  */
/* ------------------------------------------------------------------ */

function FlowCell({ row, subject }: { row: RotationRow; subject: string }) {
  const s = tagStyle(row.tag)
  const busy = Number.isFinite(row.dvol_surge) && row.dvol_surge >= 1
  return (
    <div
      className={`flex min-w-[112px] flex-1 flex-col rounded-xl border p-2.5 transition ${s.cell}`}
      title={`${row.symbol} ${row.name}\nReturn ${fmtPct(row.ret)} · vs ${subject} ${fmtPct(
        row.rel,
      )}\n$-volume ${fmtSurge(row.dvol_surge)} vs session norm · ${row.tag}`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className={`text-sm font-bold tracking-tight ${s.sym}`}>{row.symbol}</span>
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${s.dot}`} />
      </div>
      <span className="truncate text-[0.62rem] text-slate-400">{row.name}</span>
      <div className="mt-1.5 flex items-end justify-between gap-1">
        <span className={`text-sm font-semibold ${s.rel}`}>{fmtPct(row.rel)}</span>
        <span
          className={`text-[0.62rem] font-medium ${busy ? 'text-slate-300' : 'text-slate-500'}`}
          title="Dollar-volume vs session norm (>1× = busier than usual)"
        >
          {fmtSurge(row.dvol_surge)}
        </span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* panel                                                                */
/* ------------------------------------------------------------------ */

export default function RotationFlow({ rotation }: { rotation: RotationData | null }) {
  const [windowKey, setWindowKey] = useState<string>('30m')

  // pick the selected window; fall back to the first available so the panel
  // still renders if the backend ships a different window set.
  const win: RotationWindow | undefined = useMemo(() => {
    if (!rotation) return undefined
    return rotation.windows[windowKey] ?? Object.values(rotation.windows)[0]
  }, [rotation, windowKey])

  const subject = rotation?.subject ?? 'QQQ'
  const ready = !!rotation && !!win && win.regime !== 'warming_up'

  // warming-up / absent contract — never crash, show a calm placeholder
  if (!rotation || !win) {
    return (
      <Card className="p-5 sm:p-6">
        <div className="flex items-center gap-2">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cyan-500/10 text-lg text-cyan-300">
            🔄
          </span>
          <span className="inline-flex items-center gap-1.5">
            <SectionLabel>Rotation flow</SectionLabel>
            <InfoTip text={FLOW_TIP} align="left" />
          </span>
        </div>
        <p className="mt-3 text-sm text-slate-400">
          Warming up — inferring where intraday money is rotating across the tracked universe.
        </p>
      </Card>
    )
  }

  const regime = regimeStyle(win.regime)
  const rows = win.rows ?? []
  const subjReturn = win.subject_return
  const subjTone =
    subjReturn == null
      ? 'text-slate-300'
      : subjReturn > 0
        ? 'text-emerald-400'
        : subjReturn < 0
          ? 'text-rose-400'
          : 'text-slate-300'

  return (
    <Card className="relative overflow-hidden p-5 sm:p-6">
      <div className="pointer-events-none absolute -right-16 -top-16 h-48 w-48 rounded-full bg-cyan-500/10 blur-3xl" />

      {/* ---- header ---- */}
      <div className="relative flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cyan-500/10 text-lg text-cyan-300">
              🔄
            </span>
            <span className="inline-flex items-center gap-1.5">
              <SectionLabel>Rotation flow</SectionLabel>
              <InfoTip text={FLOW_TIP} align="left" />
            </span>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${regime.chip}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${regime.dot}`} />
              {regime.label}
            </span>
            {rotation.session === 'final' && (
              <span className="inline-flex items-center gap-1 rounded-full bg-slate-700/50 px-2 py-0.5 text-[0.6rem] font-semibold uppercase tracking-[0.15em] text-slate-300">
                ● Settled
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-sm text-slate-400">
              {subject} ·{' '}
              <strong className={`text-base font-semibold ${subjTone}`}>{fmtPct(subjReturn)}</strong>{' '}
              <span className="text-slate-500">/ {windowKey}</span>
            </span>
            <span className="text-xs text-slate-500">
              $-vol {fmtSurge(win.subject_dvol_surge)} vs norm
            </span>
          </div>

          {win.summary?.text && (
            <p className="mt-2 max-w-3xl text-[0.95rem] font-medium leading-6 text-slate-100">
              {win.summary.text}
            </p>
          )}
        </div>

        {/* window toggle */}
        <div className="flex shrink-0 items-center gap-1 rounded-full border border-slate-800 bg-slate-950/60 p-0.5">
          {WINDOWS.map((w) => {
            const has = !!rotation.windows[w.key]
            return (
              <button
                key={w.key}
                disabled={!has}
                onClick={() => setWindowKey(w.key)}
                className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                  windowKey === w.key
                    ? 'bg-cyan-500/15 text-cyan-200'
                    : has
                      ? 'text-slate-400 hover:text-slate-200'
                      : 'cursor-not-allowed text-slate-600'
                }`}
              >
                {w.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ---- flow strip ---- */}
      {ready && rows.length > 0 ? (
        <div className="relative mt-4">
          <div className="mb-1.5 flex items-center justify-between text-[0.6rem] font-semibold uppercase tracking-[0.2em]">
            <span className="text-emerald-300/80">◀ Money flowing in</span>
            <span className="text-rose-300/80">Money flowing out ▶</span>
          </div>
          {/* left→right by flow score (strongest inflow first) */}
          <div className="flex flex-wrap gap-2">
            {rows.map((row) => (
              <FlowCell key={row.symbol} row={row} subject={subject} />
            ))}
          </div>
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-400">
          {win.regime === 'flat'
            ? 'Flat tape — no volume-backed rotation across the tracked universe right now.'
            : 'Warming up — not enough volume-backed movement to infer rotation yet.'}
        </p>
      )}

      {/* ---- unaccounted note ---- */}
      {win.summary?.unaccounted && (
        <p className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-amber-500/10 px-2.5 py-1.5 text-xs font-medium text-amber-300">
          → cash / bonds / untracked — outflow not fully absorbed by the tracked set.
        </p>
      )}

      {/* ---- legend ---- */}
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-slate-800/80 pt-3 text-[0.7rem] text-slate-400">
        {LEGEND.map((it) => (
          <span key={it.label} className="inline-flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${it.cls}`} />
            {it.label}
          </span>
        ))}
        <span className="ml-auto inline-flex items-center gap-1.5 text-slate-500">
          % = move vs {subject} · ×= $-volume vs norm
          <InfoTip text={FLOW_TIP} align="right" />
        </span>
      </div>
    </Card>
  )
}
