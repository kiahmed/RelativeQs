export type ETFSignal = {
  symbol: string
  name: string
  dailyChange: number
  momentumScore: number
  breadthScore: number
  liquidityScore: number
  fragilityScore: number
  aiExposure: number
  relativeStrength: number
  spreadDivergence: number
}

export type MarketSignalSummary = {
  leadership: string
  breadth: string
  divergence: string
  momentum: string
  fragility: string
  liquidityRegime: string
  aiConcentration: string
}

export type QQQHealth = {
  score: number
  regime: string
  breadth: string
  summary: string
}

export type QQQScore = {
  direction: string
  raw_score: number
  probability: number
  fragility: number
  provider: string
  leader_momentum: Record<string, number>
  mags_momentum: number
  broadening_momentum: Record<string, number>
  broadening_avg: number
  confirmation_momentum: Record<string, number>
  confirmation_avg: number
  lead_lag: { symbol: string; bestLag: number; corr: number; lead: boolean }[]
  lead_signal: number
  recent_qqq: { t: string; QQQ: number }[]
  // trend-regime fields (200-day SMA engine) — optional for backward compatibility
  regime?: string
  above_trend?: boolean
  trend_gap?: number
  sma?: number
  price?: number
  trend_window?: number
  note?: string
}

export type LeadLagSignal = {
  leader: string
  lagger: string
  leadMinutes: number
  confidence: string
  details: string[]
}

export type LeadLagEntry = {
  symbol: string
  best_lag: number
  lag_minutes?: number
  best_corr: number
  corr_at_zero: number
  beta: number
  role: 'leader' | 'confirmer' | 'diverging' | 'weak'
}

/** Lead/lag recomputed at a coarser frame (5m/15m) + decoupling watch. */
export type LeadLagFrame = {
  status: string
  bars_used: number
  bar_minutes: number
  target: string
  entries: LeadLagEntry[]
  leader: { symbol: string; lag_minutes: number; corr: number; beta: number } | null
  confirmers: string[]
  diverging: string[]
  decoupled: { symbol: string; usual_corr: number; now_corr: number; drop: number }[]
  streak?: { symbol: string | null; lag_minutes: number; count: number; confirmed: boolean }
  confirmed_leader?: { symbol: string; lag_minutes: number; corr: number; beta: number } | null
}

export type PredictionPayload = {
  timestamp: number
  status: 'ok' | 'warming_up' | 'no_data'
  bars_used: number
  universe: string[]
  target: string
  lead_lag: {
    status: string
    bars_used: number
    target: string
    entries: LeadLagEntry[]
    leader: { symbol: string; lag_minutes: number; corr: number; beta: number } | null
    confirmers: string[]
    diverging: string[]
  }
  lead_lag_tf?: Record<string, LeadLagFrame>
  score: {
    status: string
    verdict: 'continue' | 'stall' | 'fragile' | 'warming_up'
    score: number
    probability_up: number
    components: { leadership: number; broadening: number; fragility: number }
    momentum_30m: Record<string, number>
  }
  projection: {
    status: string
    horizon_minutes: number
    current_price: number
    expected_return: number
    projected_price: number
    band_low: number
    band_high: number
    confidence: number
    direction: 'up' | 'down' | 'flat'
    basis: string
  }
  // --- Phase 2: 5 value features (optional = backward compatible if backend older) ---
  attribution?: {
    status: string
    target: string
    window_minutes: number
    target_return: number
    contributors: {
      symbol: string
      label: string
      beta: number
      contribution: number
      share: number
      trend: string
    }[]
    explained_share: number
    residual_share: number
    headline: string
  }
  confirmation?: {
    status: string
    state: 'confirmed' | 'unconfirmed' | 'fragile'
    target_direction: 'up' | 'down' | 'flat'
    participation: number
    participating_count: number
    universe_count: number
    leaders_agree: boolean
    fragility: number
    message: string
  }
  correlation_regime?: {
    status: string
    regime: 'coupled' | 'transitional' | 'fragmented'
    avg_pairwise_corr: number
    dispersion: number
    signals_reliable: boolean
    message: string
  }
  stability?: {
    status: string
    leader: string | null
    sessions_analyzed: number
    lead_persistence: number
    intraday_consistency: number
    median_lag: number
    tradeable: boolean
    verdict: 'tradeable' | 'unstable' | 'gathering' | 'no_leader'
    message: string
  }
  hit_rate?: {
    status: string
    leader: string | null
    horizon_minutes: number
    horizon_mode: 'auto' | 'manual'
    sample_size: number
    sessions: number
    hit_rate: number
    baseline: number
    edge: number
    by_horizon: Record<string, number>
    message: string
  }
  breadth?: {
    status: string
    target: string
    constituents_total: number
    measured: number
    advancers: number
    decliners: number
    unchanged: number
    equal_weight_pct: number
    cap_weight_pct: number
    breadth_state: 'broad' | 'mixed' | 'narrow' | 'unknown'
    divergence: number
    message: string
  }
  ai_dependency?: AIDependency
}

/* ------------------------------------------------------------------ */
/* Rotation flow — inferred intraday money rotation across a universe.  */
/* GET {BACKEND_URL}/rotation  +  WS message field `rotation`.          */
/* ------------------------------------------------------------------ */

export type RotationTag = 'in' | 'out' | 'neutral'

export type RotationRow = {
  symbol: string
  name: string
  /** window return, fraction */
  ret: number
  /** return relative to the subject (QQQ), fraction */
  rel: number
  /** window $-volume/min vs session norm (>1 = busier than usual) */
  dvol_surge: number
  /** in = absorbing money, out = shedding, neutral = no volume-backed move */
  tag: RotationTag
}

export type RotationRegime = 'rotating' | 'coupled' | 'flat' | 'warming_up'

export type RotationSummary = {
  direction: 'qqq_out' | 'qqq_in' | 'broad' | 'flat'
  into: string[]
  from: string[]
  unaccounted: boolean
  text: string
}

export type RotationWindow = {
  regime: RotationRegime
  /** subject (QQQ) return for the window, fraction — can be null */
  subject_return: number | null
  subject_dvol_surge: number
  /** already sorted by flow score (strongest inflow first) */
  rows: RotationRow[]
  summary: RotationSummary
}

export type RotationData = {
  subject: string
  universe: string[]
  asof: string
  session: 'live' | 'final'
  /** keyed by window: "15m" | "30m" | "60m" */
  windows: Record<string, RotationWindow>
}

/** AI-capex dependency index — structural/daily, walled off from intraday. */
export type AIDependencyMember = {
  symbol: string
  label: string
  bars: number
  included: boolean
}
export type AIDependencyTheme = {
  key: string
  label: string
  corr_now: number | null
  beta_now: number | null
  change: number
  limited_history: boolean
  members: AIDependencyMember[]
}
/** Bottleneck coupling re-measured over a lookback window (UI dropdown). */
export type AIDependencyWindow = {
  key: string
  label: string
  days: number
  reliable: boolean
  themes: { key: string; label: string; corr: number | null; change: number; limited: boolean }[]
}
export type AIDependency = {
  status: 'ok' | 'warming_up' | 'no_data'
  target: string
  asof: string | null
  dependency_now: number
  dependency_trend: { date: string; value: number }[]
  change: number
  change_lookback_days: number
  window_days: number
  themes: AIDependencyTheme[]
  windows?: AIDependencyWindow[]
  headline: string
}

export type AIConcentration = {
  topDrivers: string[]
  score: number
  summary: string
}

export type FragilityMeter = {
  level: string
  warnings: string[]
}

export type ChartPoint = {
  name: string
  value: number
}

export type ComparisonPoint = {
  name: string
  qqq: number
  xlk: number
  smh: number
}

export type CorrelationPoint = {
  name: string
  qqqXlk: number
  qqqSmh: number
  breadth: number
}

const baseNames = ['09:30', '10:00', '10:30', '11:00', '11:30', '12:00', '12:30']

export const etfSignals: ETFSignal[] = [
  {
    symbol: 'XLK',
    name: 'Technology Select Sector SPDR Fund',
    dailyChange: 0.82,
    momentumScore: 8,
    breadthScore: 0.72,
    liquidityScore: 9,
    fragilityScore: 3,
    aiExposure: 88,
    relativeStrength: 1.12,
    spreadDivergence: 0.8,
  },
  {
    symbol: 'SMH',
    name: 'VanEck Semiconductor ETF',
    dailyChange: 1.14,
    momentumScore: 9,
    breadthScore: 0.69,
    liquidityScore: 8,
    fragilityScore: 4,
    aiExposure: 86,
    relativeStrength: 1.18,
    spreadDivergence: 1.05,
  },
  {
    symbol: 'FNG',
    name: 'Roundhill Magnificent Seven ETF',
    dailyChange: 0.95,
    momentumScore: 8,
    breadthScore: 0.65,
    liquidityScore: 7,
    fragilityScore: 5,
    aiExposure: 93,
    relativeStrength: 1.15,
    spreadDivergence: 0.96,
  },
  {
    symbol: 'XLY',
    name: 'Consumer Discretionary Select Sector SPDR Fund',
    dailyChange: 0.48,
    momentumScore: 6,
    breadthScore: 0.58,
    liquidityScore: 8,
    fragilityScore: 5,
    aiExposure: 44,
    relativeStrength: 0.92,
    spreadDivergence: 0.55,
  },
  {
    symbol: 'XLF',
    name: 'Financial Select Sector SPDR Fund',
    dailyChange: 0.34,
    momentumScore: 5,
    breadthScore: 0.51,
    liquidityScore: 8,
    fragilityScore: 6,
    aiExposure: 18,
    relativeStrength: 0.74,
    spreadDivergence: 0.38,
  },
  {
    symbol: 'XLI',
    name: 'Industrial Select Sector SPDR Fund',
    dailyChange: 0.29,
    momentumScore: 5,
    breadthScore: 0.47,
    liquidityScore: 7,
    fragilityScore: 6,
    aiExposure: 22,
    relativeStrength: 0.8,
    spreadDivergence: 0.42,
  },
  {
    symbol: 'XLE',
    name: 'Energy Select Sector SPDR Fund',
    dailyChange: 0.06,
    momentumScore: 4,
    breadthScore: 0.42,
    liquidityScore: 7,
    fragilityScore: 7,
    aiExposure: 8,
    relativeStrength: 0.38,
    spreadDivergence: 0.08,
  },
  {
    symbol: 'IWM',
    name: 'iShares Russell 2000 ETF',
    dailyChange: 0.56,
    momentumScore: 6,
    breadthScore: 0.53,
    liquidityScore: 8,
    fragilityScore: 5,
    aiExposure: 14,
    relativeStrength: 0.85,
    spreadDivergence: 0.55,
  },
]

export const flowHistory: ChartPoint[] = baseNames.map((name, index) => ({
  name,
  value: 32 + index * 3 + (index % 2 === 0 ? 2 : 0),
}))

export const qqqComparisonHistory: ComparisonPoint[] = baseNames.map((name, index) => ({
  name,
  qqq: 450 + index * 1.8,
  xlk: 270 + index * 1.2,
  smh: 220 + index * 1.4,
}))

export const xlyXlpRatioHistory: ChartPoint[] = [
  { name: '09:30', value: 1.12 },
  { name: '10:00', value: 1.15 },
  { name: '10:30', value: 1.14 },
  { name: '11:00', value: 1.18 },
  { name: '11:30', value: 1.16 },
  { name: '12:00', value: 1.19 },
  { name: '12:30', value: 1.17 },
]

export const rollingCorrelationHistory: CorrelationPoint[] = baseNames.map((name, index) => ({
  name,
  qqqXlk: 0.86 + index * 0.008,
  qqqSmh: 0.82 + index * 0.01,
  breadth: 0.56 + index * 0.012,
}))

export const breadthHistory: ChartPoint[] = baseNames.map((name, index) => ({
  name,
  value: 0.54 + index * 0.018,
}))

const safeAverage = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1)

export function calculateMarketSignalSummary(signals: ETFSignal[]): MarketSignalSummary {
  const bestLeader = signals.reduce((winner, current) =>
    current.momentumScore > winner.momentumScore ? current : winner,
  )
  const positiveBreadth = signals.filter((item) => item.dailyChange >= 0).length
  const worstReturn = Math.min(...signals.map((item) => item.dailyChange))
  const bestReturn = Math.max(...signals.map((item) => item.dailyChange))
  const avgMomentum = safeAverage(signals.map((item) => item.momentumScore))
  const avgFragility = safeAverage(signals.map((item) => item.fragilityScore))
  const avgLiquidity = safeAverage(signals.map((item) => item.liquidityScore))
  const avgAiExposure = safeAverage(signals.map((item) => item.aiExposure))

  return {
    leadership: `${bestLeader.name} is driving the current sector rotation`,
    breadth: `${positiveBreadth} of ${signals.length} ETFs are positive today`,
    divergence: `${((bestReturn - worstReturn) * 100).toFixed(1)}% range across the ETF universe`,
    momentum: avgMomentum >= 7 ? 'Momentum remains constructive across major sectors' : 'Momentum is mixed and needs confirmation',
    fragility: avgFragility <= 5 ? 'Fragility is contained near support levels' : 'Fragility is elevated and warrants caution',
    liquidityRegime: avgLiquidity >= 8 ? 'High liquidity regime, market structure remains supportive' : 'Liquidity is moderate; watch for regime shifts',
    aiConcentration: avgAiExposure >= 70 ? 'AI concentration is elevated among the largest sector leaders' : 'AI exposure is moderate relative to broader market breadth',
  }
}

export function calculateQQQHealth(signals: ETFSignal[]): QQQHealth {
  const avgMomentum = safeAverage(signals.map((item) => item.momentumScore))
  const avgBreadth = safeAverage(signals.map((item) => item.breadthScore))
  const avgAI = safeAverage(signals.map((item) => item.aiExposure))
  const avgFragility = safeAverage(signals.map((item) => item.fragilityScore))

  const score = Math.max(0, Math.min(100, Math.round((avgMomentum * 7 + avgBreadth * 15 + avgAI * 0.4 - avgFragility * 5) + 35)))
  const regime = avgAI >= 75 && avgBreadth >= 0.6 ? 'AI Breadth Expansion' : avgBreadth >= 0.55 ? 'Broad Participation' : 'Narrow Participation'
  const summary = `QQQ health is ${score}/100 with ${regime.toLowerCase()}.`

  return {
    score,
    regime,
    breadth: `${Math.round(avgBreadth * 100)}% breadth`,
    summary,
  }
}

/**
 * Derive QQQ internal health from the live prediction payload — the real
 * measured composite (leadership / broadening / fragility) plus participation
 * breadth from per-symbol 30m momentum. Falls back to the placeholder-driven
 * calculateQQQHealth() when no live prediction is available, which is why the
 * old card was pinned near 70: transformBackendSignals never populated the
 * aiExposure / fragility / breadth fields that calculation depends on.
 */
export function deriveQQQHealth(
  prediction: PredictionPayload | null,
  fallbackSignals: ETFSignal[],
): QQQHealth {
  if (!prediction || prediction.status !== 'ok' || prediction.score?.status !== 'ok') {
    return calculateQQQHealth(fallbackSignals)
  }

  const { leadership, broadening, fragility } = prediction.score.components
  const probUp = prediction.score.probability_up
  const target = prediction.target || 'QQQ'

  // participation breadth: share of the (non-target) universe with positive 30m momentum
  const mom = prediction.score.momentum_30m || {}
  const peers = Object.keys(mom).filter((s) => s !== target)
  const participation = peers.length
    ? peers.filter((s) => mom[s] > 0).length / peers.length
    : 0.5

  // 0–100 health: directional conviction, participation breadth, and (inverted) fragility
  const raw = 0.45 * probUp + 0.3 * participation + 0.25 * (1 - fragility)
  const score = Math.max(0, Math.min(100, Math.round(raw * 100)))

  const regime =
    fragility >= 0.5
      ? 'Narrow Participation'
      : participation >= 0.6 && broadening > 0
        ? 'Broad Participation'
        : leadership > 0.2
          ? 'Top-Sector Strength'
          : 'Mixed Participation'

  return {
    score,
    regime,
    breadth: `${Math.round(participation * 100)}% participation`,
    summary: `QQQ health is ${score}/100 with ${regime.toLowerCase()}.`,
  }
}

export function calculateFragilityMeter(signals: ETFSignal[]): FragilityMeter {
  const qqqMomentum = safeAverage(signals.map((item) => item.momentumScore))
  const weakSectors = signals.filter((item) => item.breadthScore < 0.5 || item.fragilityScore >= 6)
  const warnings = []

  if (qqqMomentum >= 7 && weakSectors.length >= 2) {
    warnings.push('QQQ rising while XLY/XLI show signs of weakening.')
    warnings.push('Sector breadth is deteriorating beneath the headline move.')
  }

  if (weakSectors.some((item) => item.symbol === 'XLY' || item.symbol === 'XLI')) {
    warnings.push('Consumer discretionary and industrial breadth are lagging.')
  }

  if (weakSectors.length === 0) {
    warnings.push('Breadth is holding well across the monitored ETFs.')
  }

  const level = warnings.length >= 2 ? 'Warning' : 'Watch'
  return {
    level,
    warnings,
  }
}

/**
 * Derive a LeadLagSignal from the live prediction payload.
 *
 * Replaces the old hardcoded-3/5-minute heuristic: the leader, lag (in
 * minutes) and confidence are now the *measured* cross-correlation results
 * computed by the backend lead/lag engine. Returns an "awaiting data" signal
 * when the prediction is missing or the engine is still warming up.
 */
export function deriveLeadLag(prediction: PredictionPayload | null): LeadLagSignal {
  const lagger = prediction?.target || 'QQQ'

  // No payload yet, or the engine has not produced a verdict for this session.
  if (!prediction || prediction.status !== 'ok' || !prediction.lead_lag) {
    const barsUsed = prediction?.bars_used ?? prediction?.lead_lag?.bars_used ?? 0
    return {
      leader: '—',
      lagger,
      leadMinutes: 0,
      confidence: 'Warming up',
      details: [
        `Warming up — ${barsUsed} bar${barsUsed === 1 ? '' : 's'} collected this session.`,
        'Lead/lag roles are measured from cross-correlation once enough intraday bars accumulate.',
      ],
    }
  }

  const ll = prediction.lead_lag
  const leaderInfo = ll.leader

  // Engine ran but found no qualifying leader. This is the common, realistic
  // case: liquid sector ETFs (XLK/SMH/MAGS are inside QQQ) move coincidentally
  // at 1m resolution, so correlation peaks at lag 0 rather than ahead. Surface
  // the strongest *tentative* lead so the card stays informative.
  if (!leaderInfo) {
    // Only surface a tentative lead that is actually meaningful: its peak must
    // sit at a positive lag, the correlation must clear a noise floor, and the
    // symbol must not already be classified diverging/weak (a corr-0.04 "lead"
    // is noise, and flagging a diverging sector as "leading" is contradictory).
    const TENTATIVE_CORR_FLOOR = 0.2
    const tentative = (ll.entries || [])
      .filter(
        (e) =>
          e.best_lag >= 1 &&
          e.best_corr >= TENTATIVE_CORR_FLOOR &&
          e.role !== 'diverging' &&
          e.role !== 'weak',
      )
      .sort((a, b) => b.best_corr - a.best_corr)[0]

    const details = [`No sector is decisively leading ${lagger} right now.`]
    if (tentative) {
      details.push(
        `Strongest tendency: ${tentative.symbol} ~${tentative.best_lag}m ahead ` +
          `(corr ${tentative.best_corr.toFixed(2)}, tentative — not beating the coincident move).`,
      )
    }
    details.push(
      ll.confirmers.length
        ? `Coincident confirmers: ${ll.confirmers.join(', ')}.`
        : 'No strong coincident confirmers detected.',
    )
    details.push(
      ll.diverging.length ? `Diverging: ${ll.diverging.join(', ')}.` : 'No diverging sectors.',
    )

    return {
      leader: tentative ? `${tentative.symbol}?` : 'None',
      lagger,
      leadMinutes: tentative ? tentative.best_lag : 0,
      confidence: 'Low',
      details,
    }
  }

  const corr = leaderInfo.corr
  const leadMinutes = leaderInfo.lag_minutes
  const confidence = corr >= 0.6 ? 'High' : corr >= 0.4 ? 'Medium' : 'Low'

  const details = [
    `${leaderInfo.symbol} leads ${lagger} by ${leadMinutes} minute${leadMinutes === 1 ? '' : 's'} (measured).`,
    `Cross-correlation ${corr.toFixed(2)} · beta ${leaderInfo.beta.toFixed(2)}.`,
    ll.confirmers.length
      ? `Confirmers moving coincidentally: ${ll.confirmers.join(', ')}.`
      : 'No strong coincident confirmers detected.',
  ]

  return {
    leader: leaderInfo.symbol,
    lagger,
    leadMinutes,
    confidence,
    details,
  }
}

export function calculateAIConcentration(signals: ETFSignal[]): AIConcentration {
  const drivers = [...signals]
    .sort((a, b) => b.aiExposure - a.aiExposure)
    .slice(0, 3)
    .map((item) => item.symbol)
  const avgBreadth = safeAverage(signals.map((item) => item.breadthScore))
  const score = Math.round(safeAverage(signals.map((item) => item.aiExposure)))
  const summary = avgBreadth < 0.58 ? 'Breadth weak underneath, concentration remains elevated.' : 'AI-led strength is backed by reasonable breadth.'

  return {
    topDrivers: drivers,
    score,
    summary,
  }
}

export function formatSignalValue(value: number) {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

export type StabilityBadge = {
  verdict: 'tradeable' | 'unstable' | 'gathering' | 'no_leader'
  /** semantic tone for the pill */
  tone: 'emerald' | 'amber' | 'slate'
  label: string
  message: string
  /** true when the engine produced a usable (non-warming) read */
  ready: boolean
}

/**
 * Derive a stability badge from the live prediction's `stability` section
 * (Phase-2 lead/lag cross-day persistence). Pure — falls back to a
 * "gathering" slate badge when the section is missing/warming so the
 * lead/lag card always renders something sensible.
 */
export function deriveStabilityBadge(prediction: PredictionPayload | null): StabilityBadge {
  const s = prediction?.stability
  if (!s || (s.status !== 'ok' && s.status !== 'gathering')) {
    return {
      verdict: 'gathering',
      tone: 'slate',
      label: 'Gathering',
      message: 'Gathering cross-session data to gauge lead stability.',
      ready: false,
    }
  }

  const verdict = s.verdict
  const tone: StabilityBadge['tone'] =
    verdict === 'tradeable' ? 'emerald' : verdict === 'unstable' ? 'amber' : 'slate'
  const label =
    verdict === 'tradeable'
      ? 'Tradeable'
      : verdict === 'unstable'
        ? 'Unstable'
        : verdict === 'no_leader'
          ? 'No leader'
          : 'Gathering'

  return {
    verdict,
    tone,
    label,
    message: s.message,
    ready: s.status === 'ok',
  }
}

export type HitRateView = {
  /** the section's coarse status, surfaced for warming/no-leader handling */
  status: 'ok' | 'gathering' | 'no_leader' | 'warming_up' | 'unavailable'
  ready: boolean
  leader: string | null
  /** horizon (minutes) actually displayed */
  horizonMinutes: number
  /** whether the displayed value came from the auto horizon or a manual pick */
  mode: 'auto' | 'manual'
  /** hit-rate as a 0-100 percentage for the chosen horizon */
  hitRatePct: number
  /** raw 0..1 hit rate for the chosen horizon */
  hitRate: number
  sampleSize: number
  sessions: number
  /** edge over the naive baseline, 0..1 (auto-horizon value from backend) */
  edge: number
  /** sorted minute options for the dropdown (from by_horizon keys) */
  horizonOptions: number[]
  message: string
  /** ready, human one-liner for the card */
  line: string
}

/**
 * Derive the hit-rate view for the lead/lag card.
 *
 * THE HORIZON RULE: `opts.horizon` only re-selects which forward-return window
 * to *display* from `hit_rate.by_horizon` — it NEVER touches lead/lag. Passing
 * undefined/null means "auto" (the backend's measured-lead horizon, the default
 * mode). Passing a number picks that horizon from by_horizon client-side; if the
 * key is absent we fall back to the auto value.
 */
export function deriveHitRate(
  prediction: PredictionPayload | null,
  opts?: { horizon?: number | null },
): HitRateView {
  const hr = prediction?.hit_rate
  const lagger = prediction?.target || 'QQQ'

  if (!hr) {
    return {
      status: 'unavailable',
      ready: false,
      leader: null,
      horizonMinutes: 0,
      mode: 'auto',
      hitRatePct: 0,
      hitRate: 0,
      sampleSize: 0,
      sessions: 0,
      edge: 0,
      horizonOptions: [],
      message: 'Hit-rate data is not available yet.',
      line: 'Gathering data — 0 sessions.',
    }
  }

  const byHorizon = hr.by_horizon || {}
  const horizonOptions = Object.keys(byHorizon)
    .map((k) => Number(k))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => a - b)

  // Auto = the backend's reported horizon/value (measured lead). Manual = a
  // requested fixed horizon found in by_horizon.
  const wantManual = opts?.horizon != null
  const manualKey = wantManual ? String(opts!.horizon) : null
  const hasManual = manualKey != null && manualKey in byHorizon

  const mode: 'auto' | 'manual' = hasManual ? 'manual' : 'auto'
  const horizonMinutes = hasManual ? Number(manualKey) : hr.horizon_minutes
  const hitRate = hasManual ? byHorizon[manualKey!] : hr.hit_rate
  const hitRatePct = Math.round((hitRate ?? 0) * 100)

  const ready = hr.status === 'ok'
  let line: string
  if (!ready) {
    line =
      hr.status === 'no_leader'
        ? 'No leader to measure continuation against.'
        : `Gathering data — ${hr.sessions} session${hr.sessions === 1 ? '' : 's'}.`
  } else {
    line =
      `${lagger} followed ${hr.leader ?? 'the leader'} ${hitRatePct}% over ~${horizonMinutes}m ` +
      `(n=${hr.sample_size}, ${hr.sessions} session${hr.sessions === 1 ? '' : 's'})`
  }

  return {
    status: (hr.status as HitRateView['status']) || 'unavailable',
    ready,
    leader: hr.leader,
    horizonMinutes,
    mode,
    hitRatePct,
    hitRate: hitRate ?? 0,
    sampleSize: hr.sample_size,
    sessions: hr.sessions,
    edge: hr.edge,
    horizonOptions,
    message: hr.message,
    line,
  }
}

// ---------------------------------------------------------------------------
// Overnight / pre-market board (descriptive pre-open context; never a forecast)
// ---------------------------------------------------------------------------
export type PremarketMover = {
  symbol: string
  gap: number | null
  since_open: number | null
  dir: 'up' | 'down'
  sector: string | null
  weight: number | null
  vs_tape: 'with_tape' | 'counter_tape' | null
  crowd: 'sector_wide' | 'lone' | 'mixed' | 'with_market' | 'against_market' | null
  sustain: 'holding' | 'fading' | null
}

export type PremarketBoard = {
  status: string
  asof: string
  phase: 'pre' | 'open' | 'regular' | 'after' | 'closed'
  collapse: boolean
  minutes_to_open: number | null
  tape: {
    nq: number | null
    es: number | null
    asia: number | null
    europe: number | null
    breadth_up: number | null
    cap_breadth_up: number | null
  }
  open_lean: { dir: 'up' | 'down' | 'flat'; hist_hit: number; basis: string }
  movers: PremarketMover[]
}
