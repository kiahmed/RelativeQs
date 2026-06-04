import { describe, it, expect } from 'vitest'
import { deriveLeadLag, type PredictionPayload } from '../marketSignals'

function makePrediction(overrides: Partial<PredictionPayload> = {}): PredictionPayload {
  return {
    timestamp: 1_700_000_000,
    status: 'ok',
    bars_used: 120,
    universe: ['QQQ', 'SMH', 'XLK', 'XLY', 'XLF'],
    target: 'QQQ',
    lead_lag: {
      status: 'ok',
      bars_used: 120,
      target: 'QQQ',
      entries: [
        { symbol: 'SMH', best_lag: 3, best_corr: 0.71, corr_at_zero: 0.6, beta: 1.2, role: 'leader' },
        { symbol: 'XLY', best_lag: 0, best_corr: 0.4, corr_at_zero: 0.4, beta: 0.8, role: 'confirmer' },
        { symbol: 'XLE', best_lag: 5, best_corr: 0.02, corr_at_zero: -0.3, beta: -0.4, role: 'diverging' },
      ],
      leader: { symbol: 'SMH', lag_minutes: 3, corr: 0.71, beta: 1.2 },
      confirmers: ['XLY'],
      diverging: ['XLE'],
    },
    score: {
      status: 'ok',
      verdict: 'continue',
      score: 0.4,
      probability_up: 0.65,
      components: { leadership: 0.5, broadening: 0.3, fragility: 0.1 },
      momentum_30m: { QQQ: 0.001, SMH: 0.002 },
    },
    projection: {
      status: 'ok',
      horizon_minutes: 15,
      current_price: 500,
      expected_return: 0.003,
      projected_price: 501.5,
      band_low: 499,
      band_high: 504,
      confidence: 0.6,
      direction: 'up',
      basis: 'leader_projection',
    },
    ...overrides,
  }
}

describe('deriveLeadLag', () => {
  it('returns the measured leader/lag/confidence when status is ok', () => {
    const result = deriveLeadLag(makePrediction())
    expect(result.leader).toBe('SMH')
    expect(result.lagger).toBe('QQQ')
    expect(result.leadMinutes).toBe(3)
    expect(result.confidence).toBe('High')
    expect(result.details.join(' ')).toContain('leads QQQ by 3 minutes')
    expect(result.details.join(' ')).toContain('0.71')
  })

  it('maps correlation to confidence buckets', () => {
    const med = makePrediction()
    med.lead_lag.leader = { symbol: 'XLK', lag_minutes: 2, corr: 0.45, beta: 1.0 }
    expect(deriveLeadLag(med).confidence).toBe('Medium')

    const low = makePrediction()
    low.lead_lag.leader = { symbol: 'XLK', lag_minutes: 1, corr: 0.3, beta: 1.0 }
    expect(deriveLeadLag(low).confidence).toBe('Low')
  })

  it('returns a warming-up signal when prediction is warming_up', () => {
    const result = deriveLeadLag(makePrediction({ status: 'warming_up', bars_used: 12 }))
    expect(result.leader).toBe('—')
    expect(result.leadMinutes).toBe(0)
    expect(result.confidence).toBe('Warming up')
    expect(result.details[0]).toContain('12 bars collected')
  })

  it('returns a warming-up signal when prediction is null', () => {
    const result = deriveLeadLag(null)
    expect(result.leader).toBe('—')
    expect(result.lagger).toBe('QQQ')
    expect(result.confidence).toBe('Warming up')
    expect(result.details[0]).toContain('0 bars collected')
  })

  it('surfaces the strongest tentative lead when no leader qualifies', () => {
    const p = makePrediction()
    p.lead_lag.leader = null // engine found no decisive leader, but entries have lagged corr
    const result = deriveLeadLag(p)
    expect(result.leader).toBe('SMH?') // strongest best_lag>=1 candidate, flagged tentative
    expect(result.leadMinutes).toBe(3)
    expect(result.confidence).toBe('Low')
    const joined = result.details.join(' ')
    expect(joined).toContain('No sector is decisively leading')
    expect(joined).toContain('Strongest tendency: SMH')
  })

  it('reports None when no leader and no lagged candidate exists', () => {
    const p = makePrediction()
    p.lead_lag.leader = null
    // every entry is coincident (best_lag 0) -> no tentative lead to surface
    p.lead_lag.entries = p.lead_lag.entries.map((e) => ({ ...e, best_lag: 0 }))
    const result = deriveLeadLag(p)
    expect(result.leader).toBe('None')
    expect(result.leadMinutes).toBe(0)
    expect(result.confidence).toBe('Low')
    expect(result.details.join(' ')).toContain('No sector is decisively leading')
  })

  it('does not surface a noisy/diverging symbol as a tentative lead', () => {
    const p = makePrediction()
    p.lead_lag.leader = null
    // mirror the real bug: a diverging symbol with a noise-level corr at a positive lag
    p.lead_lag.entries = [
      { symbol: 'SMH', best_lag: 0, best_corr: 0.53, corr_at_zero: 0.53, beta: 1.0, role: 'confirmer' },
      { symbol: 'XLE', best_lag: 6, best_corr: 0.04, corr_at_zero: -0.3, beta: -0.4, role: 'diverging' },
    ]
    p.lead_lag.diverging = ['XLE']
    p.lead_lag.confirmers = ['SMH']
    const result = deriveLeadLag(p)
    expect(result.leader).toBe('None')
    const joined = result.details.join(' ')
    expect(joined).not.toContain('Strongest tendency')
    expect(joined).not.toContain('XLE ~')
  })
})
