import { useEffect, useMemo, useState } from 'react'
import { fetchPremarket } from '../services/marketApi'
import type { PremarketBoard, PremarketMover } from '../data/marketSignals'

const POLL_MS = 120_000 // backend caches ~15m; we poll lightly to refresh the clock

const pct = (x: number | null | undefined, dp = 2) =>
  x === null || x === undefined ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(dp)}%`

const fmtEta = (m: number | null) =>
  m === null ? '' : m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ''}` : `${m}m`

const PHASE_LABEL: Record<PremarketBoard['phase'], string> = {
  pre: 'Pre-market',
  open: 'Just opened',
  regular: 'Market open',
  after: 'After hours',
  closed: 'Last session',
}

const TIP =
  "The day's biggest Nasdaq-100 movers before the open, set against the overnight tape " +
  '(NQ/ES futures, Asia semis, Europe). Tags tell you what KIND of move it is — ' +
  'with-tape / counter-tape = moving with or against the futures; sector-wide / lone = ' +
  'whether its sector peers follow or it’s moving alone (usually stock news); ' +
  'fading = the pre-market move is rolling over. The open-lean (~60% hist.) is a modest ' +
  'directional hint, shown pre-open only. Descriptive context for the open — not a ' +
  'forecast of where price goes.'

/** Self-contained hover tooltip (the ribbon lives outside Dashboard's InfoTip). */
function InfoDot({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex">
      <span className="flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-slate-600 text-[0.6rem] font-bold text-slate-400 hover:border-slate-400 hover:text-slate-200">
        ?
      </span>
      <span className="pointer-events-none absolute left-0 top-5 z-20 hidden w-72 rounded-lg border border-slate-700 bg-slate-900 p-3 text-[0.7rem] leading-5 text-slate-300 shadow-xl group-hover:block">
        {text}
      </span>
    </span>
  )
}

/** A signed value chip for the overnight tape strip. */
function TapeChip({ label, value }: { label: string; value: number | null }) {
  const up = (value ?? 0) >= 0
  const tone = value === null ? 'text-slate-500' : up ? 'text-emerald-300' : 'text-rose-300'
  return (
    <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
      <span className="text-[0.65rem] uppercase tracking-wide text-slate-500">{label}</span>
      <span className={`text-xs font-semibold tabular-nums ${tone}`}>
        {value !== null && (up ? '▲' : '▼')} {pct(value, 1)}
      </span>
    </span>
  )
}

/** What a trader watches: counter-tape / lone / fading are the notable flags. */
function moverTags(m: PremarketMover) {
  const tags: { text: string; notable: boolean }[] = []
  if (m.vs_tape === 'counter_tape') tags.push({ text: 'counter-tape', notable: true })
  else if (m.vs_tape === 'with_tape') tags.push({ text: 'with tape', notable: false })
  if (m.crowd === 'lone' || m.crowd === 'against_market') tags.push({ text: 'lone', notable: true })
  else if (m.crowd === 'sector_wide') tags.push({ text: `${m.sector ?? 'sector'}-wide`, notable: false })
  if (m.sustain === 'fading') tags.push({ text: 'fading', notable: true })
  return tags
}

function MoverChip({ m, maxAbs }: { m: PremarketMover; maxAbs: number }) {
  const up = m.dir === 'up'
  const g = m.gap ?? 0
  const barW = Math.max(6, Math.min(100, (Math.abs(g) / (maxAbs || 1)) * 100))
  return (
    <div className="min-w-[8.5rem] shrink-0 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-white">{m.symbol}</span>
        <span className={`text-sm font-semibold tabular-nums ${up ? 'text-emerald-300' : 'text-rose-300'}`}>
          {pct(g)}
        </span>
      </div>
      <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full ${up ? 'bg-emerald-400' : 'bg-rose-400'}`} style={{ width: `${barW}%` }} />
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {moverTags(m).map((t) => (
          <span
            key={t.text}
            className={`rounded px-1.5 py-0.5 text-[0.6rem] font-medium ${
              t.notable ? 'bg-amber-500/15 text-amber-300' : 'bg-slate-800 text-slate-400'
            }`}
          >
            {t.text}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function PreMarketRibbon({ className = '' }: { className?: string }) {
  const [board, setBoard] = useState<PremarketBoard | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [userCollapsed, setUserCollapsed] = useState(false)

  useEffect(() => {
    let alive = true
    const load = () => fetchPremarket().then((b) => alive && b && setBoard(b))
    load()
    const id = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const maxAbs = useMemo(
    () => Math.max(0, ...(board?.movers ?? []).map((m) => Math.abs(m.gap ?? 0))),
    [board],
  )

  if (!board || board.status !== 'ok' || board.movers.length === 0) return null

  const { phase, tape, open_lean, movers, minutes_to_open, asof } = board
  const collapsed = userCollapsed || (board.collapse && !expanded)
  const preOpen = phase === 'pre' || phase === 'open'
  const asofTime = asof
    ? new Date(asof).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : ''
  const phaseText =
    phase === 'pre' ? `${PHASE_LABEL.pre} · ${fmtEta(minutes_to_open)} to open` : PHASE_LABEL[phase]

  // Collapsed: a single slim, clickable line with the headline movers.
  if (collapsed) {
    return (
      <button
        onClick={() => {
          setUserCollapsed(false)
          setExpanded(true)
        }}
        className={`flex w-full items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-2 text-left transition hover:border-slate-700 ${className}`}
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Overnight</span>
        <span className="hidden text-xs text-slate-500 sm:inline">{phaseText}</span>
        <span className="flex flex-1 items-center gap-3 overflow-hidden">
          {movers.slice(0, 5).map((m) => (
            <span key={m.symbol} className="whitespace-nowrap text-xs">
              <span className="font-semibold text-slate-200">{m.symbol}</span>{' '}
              <span className={m.dir === 'up' ? 'text-emerald-300' : 'text-rose-300'}>{pct(m.gap)}</span>
            </span>
          ))}
        </span>
        <span className="text-xs text-cyan-300">expand →</span>
      </button>
    )
  }

  return (
    <section
      className={`rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900/80 to-slate-950/60 p-4 ${className}`}
    >
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            {preOpen && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-70" />
            )}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${preOpen ? 'bg-cyan-400' : 'bg-slate-600'}`} />
          </span>
          <h2 className="text-sm font-semibold text-white">Overnight Board</h2>
          <InfoDot text={TIP} />
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[0.65rem] font-medium text-slate-300">
            {phaseText}
          </span>
          <span className="text-[0.65rem] italic text-slate-500">(auto-hides ~10am ET)</span>
        </div>
        <div className="flex items-center gap-3 text-[0.65rem] text-slate-500">
          {asofTime && <span>as of {asofTime}</span>}
          <button onClick={() => setUserCollapsed(true)} className="text-slate-400 hover:text-slate-200">
            collapse
          </button>
        </div>
      </div>

      {/* overnight tape strip */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-slate-800/70 bg-slate-950/50 px-3 py-2">
        <TapeChip label="NQ" value={tape.nq} />
        <TapeChip label="ES" value={tape.es} />
        <TapeChip label="Asia semis" value={tape.asia} />
        <TapeChip label="Europe" value={tape.europe} />
        <span className="text-[0.65rem] text-slate-500">
          breadth{' '}
          <span className="font-semibold text-slate-300">
            {tape.breadth_up !== null ? `${Math.round(tape.breadth_up * 100)}% green` : '—'}
          </span>
        </span>
        {preOpen && open_lean.dir !== 'flat' && (
          <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-200">
            → tech open leans{' '}
            <span className="font-semibold">{open_lean.dir === 'up' ? 'UP' : 'DOWN'}</span>
            <span className="text-cyan-400/70">(~{Math.round(open_lean.hist_hit * 100)}% hist.)</span>
          </span>
        )}
      </div>

      {/* mover chips — horizontal strip */}
      <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
        {movers.map((m) => (
          <MoverChip key={m.symbol} m={m} maxAbs={maxAbs} />
        ))}
      </div>

      {/* footer: honest framing + expand-to-table */}
      <div className="mt-2 flex items-center justify-between gap-2">
        <p className="text-[0.65rem] leading-4 text-slate-500">
          Biggest Nasdaq-100 movers vs the overnight tape. Descriptive context for the open — not a
          forecast of where price goes.
        </p>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="shrink-0 text-[0.65rem] font-medium text-cyan-300 hover:text-cyan-200"
        >
          {expanded ? 'hide table' : 'table ↓'}
        </button>
      </div>

      {expanded && (
        <div className="mt-2 overflow-hidden rounded-xl border border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/70 text-slate-400">
              <tr>
                <th className="px-3 py-2 font-medium" title="Nasdaq-100 ticker">Symbol</th>
                <th
                  className="px-3 py-2 text-right font-medium"
                  title="Gap into the open (overnight) | move since the 9:30 open"
                >
                  pre-mkt <span className="text-slate-600">|</span> since open
                </th>
                <th className="px-3 py-2 font-medium" title="Sector bucket">Sector</th>
                <th className="px-3 py-2 font-medium" title="Moving with or against the overnight futures (NQ)">
                  vs tape
                </th>
                <th className="px-3 py-2 font-medium" title="Sector peers moving with it, or it's moving alone">
                  crowd
                </th>
                <th className="px-3 py-2 font-medium" title="Did the pre-market move hold or fade into the open">
                  holding?
                </th>
              </tr>
            </thead>
            <tbody>
              {movers.map((m) => (
                <tr key={m.symbol} className="border-t border-slate-800/70">
                  <td className="px-3 py-2 font-semibold text-white">{m.symbol}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    <span className={m.dir === 'up' ? 'text-emerald-300' : 'text-rose-300'}>{pct(m.gap)}</span>
                    {m.since_open !== null && (
                      <>
                        <span className="mx-1 text-slate-600">|</span>
                        <span className={m.since_open >= 0 ? 'text-emerald-300' : 'text-rose-300'}>
                          {pct(m.since_open)}
                        </span>
                      </>
                    )}
                  </td>
                  <td className="px-3 py-2 capitalize text-slate-400">{m.sector ?? '—'}</td>
                  <td className={`px-3 py-2 ${m.vs_tape === 'counter_tape' ? 'text-amber-300' : 'text-slate-400'}`}>
                    {m.vs_tape === 'counter_tape' ? 'counter' : m.vs_tape === 'with_tape' ? 'with' : '—'}
                  </td>
                  <td className={`px-3 py-2 ${m.crowd === 'lone' || m.crowd === 'against_market' ? 'text-amber-300' : 'text-slate-400'}`}>
                    {m.crowd?.replace('_', ' ') ?? '—'}
                  </td>
                  <td className={`px-3 py-2 ${m.sustain === 'fading' ? 'text-amber-300' : 'text-slate-400'}`}>
                    {m.sustain ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
