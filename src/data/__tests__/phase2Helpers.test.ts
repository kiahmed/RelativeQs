import { describe, it, expect } from 'vitest'
import { deriveStabilityBadge, deriveHitRate, type PredictionPayload } from '../marketSignals'

function makePrediction(overrides: Partial<PredictionPayload> = {}): PredictionPayload {
  return {
    timestamp: 1_700_000_000,
    status: 'ok',
    bars_used: 120,
    universe: ['QQQ', 'SMH', 'XLK'],
    target: 'QQQ',
    lead_lag: {
      status: 'ok',
      bars_used: 120,
      target: 'QQQ',
      entries: [],
      leader: { symbol: 'SMH', lag_minutes: 3, corr: 0.71, beta: 1.2 },
      confirmers: [],
      diverging: [],
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

describe('deriveStabilityBadge', () => {
  it('maps a tradeable verdict to an emerald badge', () => {
    const badge = deriveStabilityBadge(
      makePrediction({
        stability: {
          status: 'ok',
          leader: 'SMH',
          sessions_analyzed: 5,
          lead_persistence: 0.8,
          intraday_consistency: 0.7,
          median_lag: 3,
          tradeable: true,
          verdict: 'tradeable',
          message: 'Lead held 4/5 sessions @ ~3min — tradeable.',
        },
      }),
    )
    expect(badge.verdict).toBe('tradeable')
    expect(badge.tone).toBe('emerald')
    expect(badge.label).toBe('Tradeable')
    expect(badge.ready).toBe(true)
    expect(badge.message).toContain('tradeable')
  })

  it('maps an unstable verdict to an amber badge', () => {
    const badge = deriveStabilityBadge(
      makePrediction({
        stability: {
          status: 'ok',
          leader: 'SMH',
          sessions_analyzed: 5,
          lead_persistence: 0.2,
          intraday_consistency: 0.3,
          median_lag: 2,
          tradeable: false,
          verdict: 'unstable',
          message: 'Leader keeps changing — unstable.',
        },
      }),
    )
    expect(badge.tone).toBe('amber')
    expect(badge.label).toBe('Unstable')
    expect(badge.ready).toBe(true)
  })

  it('treats a gathering status as a slate, not-ready badge', () => {
    const badge = deriveStabilityBadge(
      makePrediction({
        stability: {
          status: 'gathering',
          leader: 'SMH',
          sessions_analyzed: 1,
          lead_persistence: 0,
          intraday_consistency: 0,
          median_lag: 0,
          tradeable: false,
          verdict: 'gathering',
          message: 'Gathering data — 1 session so far.',
        },
      }),
    )
    expect(badge.verdict).toBe('gathering')
    expect(badge.tone).toBe('slate')
    expect(badge.ready).toBe(false)
  })

  it('maps no_leader to a slate badge', () => {
    const badge = deriveStabilityBadge(
      makePrediction({
        stability: {
          status: 'ok',
          leader: null,
          sessions_analyzed: 4,
          lead_persistence: 0,
          intraday_consistency: 0,
          median_lag: 0,
          tradeable: false,
          verdict: 'no_leader',
          message: 'No leader to track.',
        },
      }),
    )
    expect(badge.verdict).toBe('no_leader')
    expect(badge.tone).toBe('slate')
    expect(badge.label).toBe('No leader')
    expect(badge.ready).toBe(true)
  })

  it('falls back to a gathering badge when the section is missing', () => {
    const badge = deriveStabilityBadge(makePrediction())
    expect(badge.verdict).toBe('gathering')
    expect(badge.tone).toBe('slate')
    expect(badge.ready).toBe(false)
  })

  it('handles a null prediction', () => {
    const badge = deriveStabilityBadge(null)
    expect(badge.verdict).toBe('gathering')
    expect(badge.ready).toBe(false)
  })
})

describe('deriveHitRate', () => {
  const okHitRate = {
    status: 'ok',
    leader: 'SMH',
    horizon_minutes: 3,
    horizon_mode: 'auto' as const,
    sample_size: 42,
    sessions: 5,
    hit_rate: 0.61,
    baseline: 0.52,
    edge: 0.09,
    by_horizon: { '3': 0.61, '5': 0.58, '15': 0.55, '30': 0.52 },
    message: 'QQQ followed SMH 61% of the time.',
  }

  it('uses the auto (measured-lead) horizon by default', () => {
    const view = deriveHitRate(makePrediction({ hit_rate: okHitRate }))
    expect(view.mode).toBe('auto')
    expect(view.horizonMinutes).toBe(3)
    expect(view.hitRatePct).toBe(61)
    expect(view.ready).toBe(true)
    expect(view.line).toContain('QQQ followed SMH 61% over ~3m')
    expect(view.line).toContain('n=42')
    expect(view.line).toContain('5 sessions')
  })

  it('treats null/undefined horizon as auto', () => {
    const p = makePrediction({ hit_rate: okHitRate })
    expect(deriveHitRate(p, { horizon: null }).mode).toBe('auto')
    expect(deriveHitRate(p, { horizon: undefined }).mode).toBe('auto')
    expect(deriveHitRate(p, {}).mode).toBe('auto')
  })

  it('picks a manual horizon from by_horizon client-side', () => {
    const view = deriveHitRate(makePrediction({ hit_rate: okHitRate }), { horizon: 15 })
    expect(view.mode).toBe('manual')
    expect(view.horizonMinutes).toBe(15)
    expect(view.hitRatePct).toBe(55)
    expect(view.line).toContain('~15m')
  })

  it('falls back to auto when the requested horizon is absent', () => {
    const view = deriveHitRate(makePrediction({ hit_rate: okHitRate }), { horizon: 99 })
    expect(view.mode).toBe('auto')
    expect(view.horizonMinutes).toBe(3)
    expect(view.hitRatePct).toBe(61)
  })

  it('exposes sorted horizon options from by_horizon keys', () => {
    const view = deriveHitRate(makePrediction({ hit_rate: okHitRate }))
    expect(view.horizonOptions).toEqual([3, 5, 15, 30])
  })

  it('reports a gathering line until status is ok', () => {
    const view = deriveHitRate(
      makePrediction({
        hit_rate: { ...okHitRate, status: 'gathering', sample_size: 4, sessions: 1 },
      }),
    )
    expect(view.ready).toBe(false)
    expect(view.status).toBe('gathering')
    expect(view.line).toBe('Gathering data — 1 session.')
  })

  it('reports no_leader when there is no leader', () => {
    const view = deriveHitRate(
      makePrediction({ hit_rate: { ...okHitRate, status: 'no_leader', leader: null } }),
    )
    expect(view.ready).toBe(false)
    expect(view.status).toBe('no_leader')
    expect(view.line).toContain('No leader')
  })

  it('handles a missing hit_rate section', () => {
    const view = deriveHitRate(makePrediction())
    expect(view.status).toBe('unavailable')
    expect(view.ready).toBe(false)
    expect(view.horizonOptions).toEqual([])
  })

  it('never touches lead/lag (auto horizon is independent of any pick)', () => {
    const p = makePrediction({ hit_rate: okHitRate })
    const manual = deriveHitRate(p, { horizon: 30 })
    // lead/lag leader/lag stays whatever the payload says, regardless of pick
    expect(p.lead_lag.leader?.lag_minutes).toBe(3)
    expect(manual.horizonMinutes).toBe(30)
  })
})
