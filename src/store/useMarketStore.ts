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
  FragilityMeter,
  LeadLagSignal,
  AIConcentration,
  ChartPoint,
  ComparisonPoint,
  CorrelationPoint,
} from '../data/marketSignals'
import { fetchLiveMarketSnapshot, MarketSnapshot } from '../services/marketApi'
import { createBackendClient } from '../services/backendClient'

export type MarketState = {
  signals: ETFSignal[]
  history: ChartPoint[]
  qqqComparison: ComparisonPoint[]
  xlyXlpRatio: ChartPoint[]
  rollingCorrelation: CorrelationPoint[]
  breadthHistory: ChartPoint[]
  summary: MarketSignalSummary
  qqqHealth: QQQHealth
  fragilityMeter: FragilityMeter
  leadLag: LeadLagSignal
  aiConcentration: AIConcentration
  loading: boolean
  refresh: () => Promise<void>
  startRealtime: (wsUrl?: string) => void
  stopRealtime: () => void
  wsConnected: boolean
}

const buildState = (snapshot: MarketSnapshot) => ({
  signals: snapshot.signals,
  history: snapshot.flowHistory,
  qqqComparison: snapshot.qqqComparison,
  xlyXlpRatio: snapshot.xlyXlpRatio,
  rollingCorrelation: snapshot.rollingCorrelation,
  breadthHistory: snapshot.breadthHistory,
  summary: calculateMarketSignalSummary(snapshot.signals),
  qqqHealth: calculateQQQHealth(snapshot.signals),
  fragilityMeter: calculateFragilityMeter(snapshot.signals),
  leadLag: calculateLeadLag(snapshot.signals),
  aiConcentration: calculateAIConcentration(snapshot.signals),
})

export const useMarketStore = create<MarketState>((set) => ({
  ...buildState({
    signals: etfSignals,
    flowHistory,
    qqqComparison: qqqComparisonHistory,
    xlyXlpRatio: xlyXlpRatioHistory,
    rollingCorrelation: rollingCorrelationHistory,
    breadthHistory,
  }),
  loading: false,
  wsConnected: false,
  startRealtime: (wsUrl = 'ws://localhost:8000/ws/market') => {
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
    set({
      ...buildState(snapshot),
      loading: false,
    })
  },
}))
