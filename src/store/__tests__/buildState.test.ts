import { describe, it, expect } from 'vitest'
import { buildState, transformBackendSignals } from '../useMarketStore'
import type { PredictionPayload } from '../../data/marketSignals'
import type { MarketSnapshot } from '../../services/marketApi'

function makePrediction(): PredictionPayload {
  return {
    timestamp: 1_700_000_000,
    status: 'ok',
    bars_used: 120,
    universe: ['QQQ', 'SMH'],
    target: 'QQQ',
    lead_lag: {
      status: 'ok',
      bars_used: 120,
      target: 'QQQ',
      entries: [
        { symbol: 'SMH', best_lag: 4, best_corr: 0.68, corr_at_zero: 0.5, beta: 1.1, role: 'leader' },
      ],
      leader: { symbol: 'SMH', lag_minutes: 4, corr: 0.68, beta: 1.1 },
      confirmers: ['XLY'],
      diverging: [],
    },
    score: {
      status: 'ok',
      verdict: 'continue',
      score: 0.3,
      probability_up: 0.62,
      components: { leadership: 0.4, broadening: 0.2, fragility: 0.1 },
      momentum_30m: { QQQ: 0.001 },
    },
    projection: {
      status: 'ok',
      horizon_minutes: 15,
      current_price: 500,
      expected_return: 0.002,
      projected_price: 501,
      band_low: 499,
      band_high: 503,
      confidence: 0.55,
      direction: 'up',
      basis: 'leader_projection',
    },
  }
}

describe('transformBackendSignals', () => {
  it('maps a backend signals dict into ETFSignal[]', () => {
    const signals = transformBackendSignals({ XLK_mom: 0.05, SMH_mom: 0.08, XLY_conf: 0.1 })
    const xlk = signals.find((s) => s.symbol === 'XLK')
    const smh = signals.find((s) => s.symbol === 'SMH')
    const xly = signals.find((s) => s.symbol === 'XLY')
    expect(xlk).toBeDefined()
    expect(smh).toBeDefined()
    expect(xly).toBeDefined()
    expect(xlk!.momentumScore).toBeGreaterThan(5)
    expect(xly!.relativeStrength).toBeGreaterThan(1.0)
  })

  it('merges multiple signal types onto the same symbol', () => {
    const signals = transformBackendSignals({ XLK_mom: 0.05, XLK_breadth: 0.7 })
    expect(signals).toHaveLength(1)
    expect(signals[0].symbol).toBe('XLK')
    expect(signals[0].breadthScore).toBeCloseTo(0.7)
  })

  it('ignores unknown symbols and malformed keys', () => {
    const signals = transformBackendSignals({ ZZZ_mom: 0.1, badkey: 0.2 })
    expect(signals).toHaveLength(0)
  })
})

describe('buildState', () => {
  const snapshot: MarketSnapshot = {
    timestamp: Date.now(),
    signals: { XLK_mom: 0.05, SMH_mom: 0.08 },
  }

  it('derives a warming-up leadLag and null prediction when no prediction passed', () => {
    const state = buildState(snapshot)
    expect(state.prediction).toBeNull()
    expect(state.leadLag.confidence).toBe('Warming up')
    expect(state.leadLag.leader).toBe('—')
    expect(state.signals.length).toBeGreaterThan(0)
  })

  it('derives a real leadLag from a provided prediction payload', () => {
    const prediction = makePrediction()
    const state = buildState(snapshot, prediction)
    expect(state.prediction).toBe(prediction)
    expect(state.leadLag.leader).toBe('SMH')
    expect(state.leadLag.leadMinutes).toBe(4)
    expect(state.leadLag.confidence).toBe('High')
  })

  it('derives QQQ health from real prediction components, not the ~70 placeholder', () => {
    // healthy payload: high prob_up, broad participation, low fragility
    const strong = makePrediction()
    strong.score.probability_up = 0.92
    strong.score.components = { leadership: 0.6, broadening: 0.4, fragility: 0.05 }
    strong.score.momentum_30m = { QQQ: 0.002, SMH: 0.003, XLK: 0.002, XLY: 0.001 }
    const strongState = buildState(snapshot, strong)

    // fragile payload: low prob_up, narrow participation, high fragility
    const weak = makePrediction()
    weak.score.probability_up = 0.35
    weak.score.components = { leadership: -0.2, broadening: -0.1, fragility: 0.7 }
    weak.score.momentum_30m = { QQQ: 0.001, SMH: -0.002, XLK: -0.001, XLY: -0.003 }
    const weakState = buildState(snapshot, weak)

    expect(strongState.qqqHealth.score).toBeGreaterThan(weakState.qqqHealth.score)
    expect(strongState.qqqHealth.score).toBeGreaterThan(75)
    expect(weakState.qqqHealth.score).toBeLessThan(50)
    // the two payloads must not collapse to the same constant (the old bug)
    expect(strongState.qqqHealth.score).not.toBe(weakState.qqqHealth.score)
  })
})
