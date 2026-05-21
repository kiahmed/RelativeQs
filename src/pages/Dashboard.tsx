import { useEffect } from 'react'
import { Line, LineChart, ResponsiveContainer, CartesianGrid, Tooltip, XAxis, YAxis, Legend, AreaChart, Area } from 'recharts'
import { useAuthStore } from '../store/useAuthStore'
import { useMarketStore } from '../store/useMarketStore'
import MarketChart from '../components/MarketChart'

const displayLabels: Record<string, string> = {
  leadership: 'Leadership',
  breadth: 'Breadth',
  divergence: 'Divergence',
  momentum: 'Momentum',
  fragility: 'Fragility',
  liquidityRegime: 'Liquidity regime',
  aiConcentration: 'AI concentration',
}

export default function Dashboard() {
  const user = useAuthStore((state) => state.user)
  const {
    signals,
    history,
    qqqComparison,
    xlyXlpRatio,
    rollingCorrelation,
    breadthHistory,
    summary,
    qqqHealth,
    fragilityMeter,
    leadLag,
    aiConcentration,
    loading,
    refresh,
    startRealtime,
    stopRealtime,
  } = useMarketStore()

  const highestStrength = signals.reduce((best, item) => (item.relativeStrength > best.relativeStrength ? item : best), signals[0])
  const xly = signals.find((item) => item.symbol === 'XLY')
  const xli = signals.find((item) => item.symbol === 'XLI')
  const spreadDivergence = xly && xli ? xly.dailyChange - xli.dailyChange : 0

  useEffect(() => {
    refresh()
    const interval = window.setInterval(refresh, 12000)
    // start websocket realtime feed
    startRealtime()
    return () => {
      window.clearInterval(interval)
      stopRealtime()
    }
  }, [refresh])

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-8 shadow-glow">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">Real-time market dashboard</p>
            <h1 className="mt-3 text-3xl font-semibold text-white">QQQ & sector leadership analytics</h1>
            <p className="mt-2 max-w-2xl text-slate-300">
              Live sector dashboard with relative strength, divergence, rolling correlations, lead/lag signals, fragility, and AI concentration.
            </p>
          </div>
          <div className="rounded-3xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-slate-200">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Signed in as</p>
            <p className="mt-1 font-medium text-white">{user?.email ?? 'Unknown'}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-6 shadow-glow">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">Live sector dashboard</p>
          <h2 className="mt-3 text-2xl font-semibold text-white">% change, RS, spread divergence</h2>
          <div className="mt-6 space-y-4 text-slate-300">
            <div className="rounded-3xl bg-slate-950/80 p-4">
              <p className="text-sm uppercase tracking-[0.3em] text-slate-400">Top relative strength</p>
              <p className="mt-2 text-lg font-semibold text-white">{highestStrength.symbol} at {highestStrength.relativeStrength.toFixed(2)}x</p>
            </div>
            <div className="rounded-3xl bg-slate-950/80 p-4">
              <p className="text-sm uppercase tracking-[0.3em] text-slate-400">Spread divergence</p>
              <p className="mt-2 text-lg font-semibold text-white">{spreadDivergence >= 0 ? '+' : ''}{spreadDivergence.toFixed(2)}%</p>
            </div>
            <div className="rounded-3xl bg-slate-950/80 p-4">
              <p className="text-sm uppercase tracking-[0.3em] text-slate-400">Relative strength leader</p>
              <p className="mt-2 text-lg font-semibold text-white">{highestStrength.name}</p>
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-6 shadow-glow">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">QQQ internal health</p>
          <div className="mt-4 flex items-center justify-between gap-4">
            <div>
              <h2 className="text-4xl font-semibold text-white">{qqqHealth.score}/100</h2>
              <p className="mt-2 text-sm text-slate-400">Regime: {qqqHealth.regime}</p>
            </div>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-slate-950/80">
              <div className="h-full rounded-full bg-cyan-400" style={{ width: `${qqqHealth.score}%` }} />
            </div>
          </div>
          <p className="mt-4 text-sm text-slate-300">{qqqHealth.summary}</p>
          <p className="mt-4 text-sm uppercase tracking-[0.3em] text-slate-500">Breadth</p>
          <p className="text-lg font-semibold text-white">{qqqHealth.breadth}</p>
        </div>

        <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-6 shadow-glow">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">Fragility meter</p>
          <h2 className="mt-3 text-2xl font-semibold text-white">{fragilityMeter.level}</h2>
          <div className="mt-5 space-y-3 text-sm text-slate-300">
            {fragilityMeter.warnings.map((warning) => (
              <div key={warning} className="rounded-3xl bg-slate-950/80 px-4 py-4">
                <p>{warning}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="space-y-6 rounded-3xl border border-slate-800 bg-slate-900/90 p-8 shadow-glow">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-3xl bg-slate-950/80 p-6">
              <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">Lead / lag detection</p>
              <h3 className="mt-3 text-2xl font-semibold text-white">{leadLag.leader} leads {leadLag.lagger}</h3>
              <p className="mt-2 text-slate-300">Confidence: {leadLag.confidence}</p>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-slate-300">
                {leadLag.details.map((detail) => (
                  <li key={detail}>{detail}</li>
                ))}
              </ul>
            </div>
            <div className="rounded-3xl bg-slate-950/80 p-6">
              <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">AI concentration meter</p>
              <h3 className="mt-3 text-2xl font-semibold text-white">Top drivers</h3>
              <div className="mt-4 space-y-3 text-slate-300">
                {aiConcentration.topDrivers.map((driver) => (
                  <div key={driver} className="rounded-3xl bg-slate-900/90 px-4 py-3">
                    {driver}
                  </div>
                ))}
              </div>
              <p className="mt-4 text-sm text-slate-300">{aiConcentration.summary}</p>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-800 bg-slate-950/80 p-6">
            <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">QQQ vs sector charts</p>
            <div className="mt-6 space-y-6">
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={qqqComparison}>
                    <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: 12 }} />
                    <Legend wrapperStyle={{ color: '#94a3b8' }} />
                    <Line type="monotone" dataKey="qqq" stroke="#22d3ee" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="xlk" stroke="#38bdf8" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={qqqComparison}>
                    <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: 12 }} />
                    <Legend wrapperStyle={{ color: '#94a3b8' }} />
                    <Line type="monotone" dataKey="qqq" stroke="#22d3ee" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="smh" stroke="#818cf8" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </section>

        <aside className="space-y-6 rounded-3xl border border-slate-800 bg-slate-900/90 p-8 shadow-glow">
          <div className="rounded-3xl bg-slate-950/80 p-6">
            <h3 className="text-xl font-semibold text-white">Market regime analytics</h3>
            <p className="mt-3 text-sm leading-6 text-slate-300">
              Rolling correlations, XLY/XLP ratio, and breadth score help you detect whether leadership is broadening or narrowing.
            </p>
          </div>

          <div className="space-y-6 rounded-3xl border border-slate-800 bg-slate-950/80 p-6">
            <div className="rounded-3xl bg-slate-900/90 p-4">
              <p className="text-sm uppercase tracking-[0.3em] text-slate-400">XLY / XLP ratio</p>
              <div className="mt-3 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={xlyXlpRatio}>
                    <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: 12 }} />
                    <Line type="monotone" dataKey="value" stroke="#22d3ee" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-3xl bg-slate-900/90 p-4">
              <p className="text-sm uppercase tracking-[0.3em] text-slate-400">Rolling correlations</p>
              <div className="mt-3 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={rollingCorrelation}>
                    <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} domain={[0.6, 1]} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: 12 }} />
                    <Line type="monotone" dataKey="qqqXlk" stroke="#22d3ee" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="qqqSmh" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-3xl bg-slate-900/90 p-4">
              <p className="text-sm uppercase tracking-[0.3em] text-slate-400">Breadth score</p>
              <div className="mt-3 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={breadthHistory}>
                    <defs>
                      <linearGradient id="breadthGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.8} />
                        <stop offset="95%" stopColor="#0f172a" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} domain={[0.4, 1]} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: 12 }} />
                    <Area type="monotone" dataKey="value" stroke="#22d3ee" fill="url(#breadthGradient)" strokeWidth={2} dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </aside>
      </div>

      <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-8 shadow-glow">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80">ETF signal universe</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">Live sector signal scan</h2>
          </div>
          {loading && <p className="text-sm text-cyan-300">Refreshing market signals...</p>}
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {signals.map((signal) => (
            <div key={signal.symbol} className="rounded-3xl border border-slate-800 bg-slate-950/80 p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm uppercase tracking-[0.3em] text-slate-400">{signal.symbol}</p>
                  <p className="mt-2 font-semibold text-white">{signal.name}</p>
                </div>
                <span className="rounded-full bg-cyan-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-cyan-300">
                  {signal.dailyChange > 0 ? '+' : ''}{signal.dailyChange.toFixed(2)}%
                </span>
              </div>
              <div className="mt-5 space-y-3 text-sm text-slate-300">
                <div className="flex items-center justify-between gap-2">
                  <span>RS</span>
                  <strong className="text-slate-100">{signal.relativeStrength.toFixed(2)}</strong>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span>Spread</span>
                  <strong className="text-slate-100">{signal.spreadDivergence.toFixed(2)}%</strong>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span>AI exposure</span>
                  <strong className="text-slate-100">{signal.aiExposure}%</strong>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
