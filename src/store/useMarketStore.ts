import { create } from 'zustand'
import {
  calculateMarketSignalSummary,
  calculateQQQHealth,
  calculateFragilityMeter,
  calculateLeadLag,
  calculateAIConcentration,
  etfSignals,
  flowHistory,
  qqqComparisonHistory,
  xlyXlpRatioHistory,
  rollingCorrelationHistory,
  breadthHistory,
  MarketSignalSummary,
  ETFSignal,
  QQQHealth,
  QQQScore,
  FragilityMeter,
  LeadLagSignal,
  AIConcentration,
  ChartPoint,
  ComparisonPoint,
  CorrelationPoint,
} from '../data/marketSignals'
import { fetchLiveMarketSnapshot, fetchLiveQQQScore, MarketSnapshot } from '../services/marketApi'
import { createBackendClient } from '../services/backendClient'
import { WS_URL } from '../config'

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value))

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

export type MarketState = {
  signals: ETFSignal[]
  history: ChartPoint[]
  qqqComparison: ComparisonPoint[]
  xlyXlpRatio: ChartPoint[]
  rollingCorrelation: CorrelationPoint[]
  breadthHistory: ChartPoint[]
  summary: MarketSignalSummary
  qqqHealth: QQQHealth
  qqqScore: QQQScore
  fragilityMeter: FragilityMeter
  leadLag: LeadLagSignal
  aiConcentration: AIConcentration
  loading: boolean
  refresh: () => Promise<void>
  startRealtime: (wsUrl?: string) => void
  stopRealtime: () => void
  wsConnected: boolean
}

const buildState = (snapshot: MarketSnapshot) => {
  // Handle both old format (direct signals array) and new format (signals dict from backend)
  const signals = Array.isArray(snapshot.signals) 
    ? snapshot.signals 
    : transformBackendSignals(snapshot.signals || {})
  
  const flow = snapshot.flowHistory || snapshot.flow_series || flowHistory
  const qqqComp = snapshot.qqqComparison || qqqComparisonHistory
  const xlyXlp = snapshot.xlyXlpRatio || xlyXlpRatioHistory
  const rollingCorr = snapshot.rollingCorrelation || rollingCorrelationHistory
  const breadthHist = snapshot.breadthHistory || breadthHistory
  const qqqScore = snapshot.qqqScore || {
    direction: 'neutral',
    raw_score: 0,
    probability: 0,
    fragility: 0,
    provider: 'mock',
    leader_momentum: { XLK: 0, SMH: 0 },
    mags_momentum: 0,
    broadening_momentum: { XLY: 0, XLF: 0 },
    broadening_avg: 0,
    confirmation_momentum: { XLI: 0, IWM: 0, XLE: 0 },
    confirmation_avg: 0,
    lead_lag: [],
    lead_signal: 0,
    recent_qqq: [],
  }

  return {
    signals,
    history: flow,
    qqqComparison: qqqComp,
    xlyXlpRatio: xlyXlp,
    rollingCorrelation: rollingCorr,
    breadthHistory: breadthHist,
    summary: calculateMarketSignalSummary(signals),
    qqqHealth: calculateQQQHealth(signals),
    qqqScore,
    fragilityMeter: calculateFragilityMeter(signals),
    leadLag: calculateLeadLag(signals),
    aiConcentration: calculateAIConcentration(signals),
  }
}

export const useMarketStore = create<MarketState>((set) => {
  const mockSnapshot: MarketSnapshot = {
    timestamp: Date.now(),
    signals: etfSignals as unknown as Record<string, number>,
    flowHistory,
    qqqComparison: qqqComparisonHistory,
    xlyXlpRatio: xlyXlpRatioHistory,
    rollingCorrelation: rollingCorrelationHistory,
    breadthHistory,
  }

  return {
    ...buildState(mockSnapshot),
    qqqScore: {
      direction: 'neutral',
      raw_score: 0,
      probability: 0,
      fragility: 0,
      provider: 'mock',
      leader_momentum: { XLK: 0, SMH: 0 },
      mags_momentum: 0,
      broadening_momentum: { XLY: 0, XLF: 0 },
      broadening_avg: 0,
      confirmation_momentum: { XLI: 0, IWM: 0, XLE: 0 },
      confirmation_avg: 0,
      lead_lag: [],
      lead_signal: 0,
      recent_qqq: [],
    },
    loading: false,
    wsConnected: false,
    startRealtime: (wsUrl = WS_URL) => {
      // lazy-create client on first call
      const anyGlobal = (window as any)
      if (!anyGlobal.__pf_ws_client) {
        anyGlobal.__pf_ws_client = createBackendClient(wsUrl)
        anyGlobal.__pf_ws_client.onSnapshot((payload: MarketSnapshot) => {
          try {
            set({ ...buildState(payload) })
          } catch (e) {
            console.error('Failed to apply snapshot', e)
          }
        })
        anyGlobal.__pf_ws_client.onQQQScore((payload: QQQScore) => {
          set({ qqqScore: payload })
        })
        anyGlobal.__pf_ws_client.connect()
        set({ wsConnected: true })
      }
    },
    stopRealtime: () => {
      const anyGlobal = (window as any)
      if (anyGlobal.__pf_ws_client) {
        anyGlobal.__pf_ws_client.disconnect()
        delete anyGlobal.__pf_ws_client
        set({ wsConnected: false })
      }
    },
    refresh: async () => {
      set({ loading: true })
      const snapshot = await fetchLiveMarketSnapshot()
      const qqqScore = await fetchLiveQQQScore()
      set({
        ...buildState({ ...snapshot, qqqScore: qqqScore ?? undefined }),
        loading: false,
      })
    },
  }
})
