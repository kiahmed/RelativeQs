import {
  ETFSignal,
  ComparisonPoint,
  CorrelationPoint,
  ChartPoint,
  etfSignals,
  flowHistory,
  qqqComparisonHistory,
  xlyXlpRatioHistory,
  rollingCorrelationHistory,
  breadthHistory,
} from '../data/marketSignals'

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value))

const randomizeSeries = <T extends ChartPoint>(series: T[]) =>
  series.map((point) => ({
    ...point,
    value: clamp(point.value + (Math.random() - 0.5) * 4, 0, 120),
  }))

const randomizeComparison = (series: ComparisonPoint[]) =>
  series.map((point) => ({
    ...point,
    qqq: clamp(point.qqq + (Math.random() - 0.5) * 2.5, 430, 470),
    xlk: clamp(point.xlk + (Math.random() - 0.5) * 2, 260, 290),
    smh: clamp(point.smh + (Math.random() - 0.5) * 2, 210, 240),
  }))

const randomizeCorrelation = (series: CorrelationPoint[]) =>
  series.map((point) => ({
    ...point,
    qqqXlk: clamp(point.qqqXlk + (Math.random() - 0.5) * 0.02, 0.7, 1),
    qqqSmh: clamp(point.qqqSmh + (Math.random() - 0.5) * 0.025, 0.7, 1),
    breadth: clamp(point.breadth + (Math.random() - 0.5) * 0.02, 0.4, 0.85),
  }))

export type MarketSnapshot = {
  signals: ETFSignal[]
  flowHistory: ChartPoint[]
  qqqComparison: ComparisonPoint[]
  xlyXlpRatio: ChartPoint[]
  rollingCorrelation: CorrelationPoint[]
  breadthHistory: ChartPoint[]
}

export async function fetchLiveMarketSnapshot(): Promise<MarketSnapshot> {
  await new Promise((resolve) => setTimeout(resolve, 300))

  const signals = etfSignals.map((signal) => ({
    ...signal,
    dailyChange: clamp(signal.dailyChange + (Math.random() - 0.5) * 0.9, -3, 3),
    momentumScore: clamp(signal.momentumScore + Math.round((Math.random() - 0.5) * 2), 1, 10),
    breadthScore: clamp(signal.breadthScore + (Math.random() - 0.5) * 0.07, 0, 1),
    liquidityScore: clamp(signal.liquidityScore + Math.round((Math.random() - 0.5) * 2), 1, 10),
    fragilityScore: clamp(signal.fragilityScore + Math.round((Math.random() - 0.5) * 1), 1, 10),
    aiExposure: clamp(signal.aiExposure + Math.round((Math.random() - 0.5) * 5), 0, 100),
    relativeStrength: clamp(signal.relativeStrength + (Math.random() - 0.5) * 0.08, 0.3, 1.4),
    spreadDivergence: clamp(signal.spreadDivergence + (Math.random() - 0.5) * 0.05, -0.5, 1.5),
  }))

  return {
    signals,
    flowHistory: randomizeSeries(flowHistory),
    qqqComparison: randomizeComparison(qqqComparisonHistory),
    xlyXlpRatio: randomizeSeries(xlyXlpRatioHistory),
    rollingCorrelation: randomizeCorrelation(rollingCorrelationHistory),
    breadthHistory: randomizeSeries(breadthHistory),
  }
}
