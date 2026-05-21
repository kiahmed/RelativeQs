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

export type LeadLagSignal = {
  leader: string
  lagger: string
  leadMinutes: number
  confidence: string
  details: string[]
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
  const regime = avgAI >= 75 && avgBreadth >= 0.6 ? 'AI Breadth Expansion' : avgBreadth >= 0.55 ? 'Sector Leadership Broadening' : 'Leadership Narrowing'
  const summary = `QQQ health is ${score}/100 with ${regime.toLowerCase()}.` 

  return {
    score,
    regime,
    breadth: `${Math.round(avgBreadth * 100)}% breadth`,
    summary,
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

export function calculateLeadLag(signals: ETFSignal[]): LeadLagSignal {
  const smh = signals.find((item) => item.symbol === 'SMH')
  const xlk = signals.find((item) => item.symbol === 'XLK')
  const qqqApprox = safeAverage(signals.map((item) => item.dailyChange))

  const leader = smh && smh.momentumScore > (xlk?.momentumScore ?? 0) ? 'SMH' : 'XLK'
  const lagger = 'QQQ'
  const leadMinutes = leader === 'SMH' ? 3 : 5
  const confidence = Math.abs((smh?.momentumScore ?? 0) - (xlk?.momentumScore ?? 0)) >= 2 ? 'High' : 'Medium'
  const details = [
    `${leader} leading QQQ by ${leadMinutes} minutes`,
    `Correlation strength is ${confidence.toLowerCase()}.`,
    `Relative strength on ${leader} remains above market average.`,
  ]

  return {
    leader,
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
