import {
  etfSignals,
  flowHistory,
  qqqComparisonHistory,
  xlyXlpRatioHistory,
  rollingCorrelationHistory,
  breadthHistory,
  type ETFSignal,
  type ComparisonPoint,
  type CorrelationPoint,
  type ChartPoint,
  type QQQScore,
} from '../data/marketSignals'

const BACKEND_URL = 'http://localhost:8000'

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value))

export type MarketSnapshot = {
  timestamp: number
  signals: Record<string, number>
  flow_series?: ChartPoint[]
  flowHistory?: ChartPoint[]
  qqqComparison?: ComparisonPoint[]
  xlyXlpRatio?: ChartPoint[]
  rollingCorrelation?: CorrelationPoint[]
  breadthHistory?: ChartPoint[]
  qqqScore?: QQQScore
}

export async function fetchLiveQQQScore(): Promise<QQQScore | null> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/qqq-score`)
    if (!response.ok) {
      console.error('Failed to fetch qqq score:', response.statusText)
      return null
    }
    const data: QQQScore = await response.json()
    return data
  } catch (error) {
    console.error('[Frontend] Failed to fetch qqq score:', error)
    return null
  }
}

/**
 * Transform backend signals format { "XLK_mom": 0.05, ... } 
 * into ETFSignal[] for frontend display
 */
function transformBackendSignals(signals: Record<string, number>): ETFSignal[] {
  const etfMap: Record<string, Partial<ETFSignal>> = {
    XLK: { name: 'Technology Select', symbol: 'XLK' },
    SMH: { name: 'Semiconductor', symbol: 'SMH' },
    QQQ: { name: 'Nasdaq-100', symbol: 'QQQ' },
    XLY: { name: 'Consumer Discretionary', symbol: 'XLY' },
    XLF: { name: 'Financial Select', symbol: 'XLF' },
    XLI: { name: 'Industrial Select', symbol: 'XLI' },
    IWM: { name: 'Russell 2000', symbol: 'IWM' },
    XLE: { name: 'Energy Select', symbol: 'XLE' },
  }

  const result: ETFSignal[] = []
  for (const [key, value] of Object.entries(signals)) {
    const parts = key.split('_')
    if (parts.length === 2) {
      const symbol = parts[0]
      const signalType = parts[1]
      const existing = result.find((s) => s.symbol === symbol)

      if (!existing && etfMap[symbol]) {
        const newSignal: ETFSignal = {
          name: etfMap[symbol].name || symbol,
          symbol,
          dailyChange: 0,
          momentumScore: 5,
          breadthScore: 0.5,
          liquidityScore: 5,
          fragilityScore: 5,
          aiExposure: 50,
          relativeStrength: 1.0,
          spreadDivergence: 0.0,
        }

        if (signalType === 'mom') {
          newSignal.momentumScore = clamp(5 + value * 50, 1, 10)
          newSignal.dailyChange = clamp(value * 100, -3, 3)
        } else if (signalType === 'conf') {
          newSignal.relativeStrength = clamp(1.0 + value, 0.3, 1.4)
        } else if (signalType === 'breadth') {
          newSignal.breadthScore = clamp(value, 0, 1)
        }

        result.push(newSignal)
      } else if (existing) {
        if (signalType === 'mom') {
          existing.momentumScore = clamp(5 + value * 50, 1, 10)
          existing.dailyChange = clamp(value * 100, -3, 3)
        } else if (signalType === 'conf') {
          existing.relativeStrength = clamp(1.0 + value, 0.3, 1.4)
        } else if (signalType === 'breadth') {
          existing.breadthScore = clamp(value, 0, 1)
        }
      }
    }
  }

  return result
}

export async function fetchLiveMarketSnapshot(): Promise<MarketSnapshot> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/snapshot`)
    if (!response.ok) {
      console.error('Failed to fetch snapshot:', response.statusText)
      throw new Error(`API error: ${response.status}`)
    }
    const data: MarketSnapshot = await response.json()
    console.log('[Frontend] Snapshot received from backend:', data)
    return data
  } catch (error) {
    console.error('[Frontend] Failed to fetch live snapshot, falling back to mock:', error)
    // fallback to mock data
    await new Promise((resolve) => setTimeout(resolve, 300))
    return {
      timestamp: Date.now(),
      signals: {
        XLK_mom: (Math.random() - 0.5) * 0.1,
        SMH_mom: (Math.random() - 0.5) * 0.1,
        XLY_conf: (Math.random() - 0.5) * 0.05,
        XLF_conf: (Math.random() - 0.5) * 0.05,
        XLI_breadth: (Math.random() - 0.5) * 0.1,
        IWM_breadth: (Math.random() - 0.5) * 0.1,
        XLE_inflation_stress: (Math.random() - 0.5) * 0.05,
      },
      flow_series: flowHistory,
      qqqComparison: qqqComparisonHistory,
      xlyXlpRatio: xlyXlpRatioHistory,
      rollingCorrelation: rollingCorrelationHistory,
      breadthHistory,
    }
  }
}
