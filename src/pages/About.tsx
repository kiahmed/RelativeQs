const stats = [
  { label: 'Sector ETFs tracked', value: '8' },
  { label: 'Backtest window', value: '12 yrs' },
  { label: 'Signal refresh', value: '30 s' },
]

const team = [
  { name: 'Alex Morgan', role: 'Founder & CEO' },
  { name: 'Priya Patel', role: 'Head of Data Science' },
  { name: 'Samir Khan', role: 'Lead Engineer' },
]

const values = [
  {
    icon: '🔎',
    title: 'Rigor',
    desc: 'Every signal is backtested before it ships. If it has no edge, it does not go in the product.',
  },
  {
    icon: '🪟',
    title: 'Transparency',
    desc: 'We show our methodology and our limits — analytics and education, never hype.',
  },
  {
    icon: '⚡',
    title: 'Fast iteration',
    desc: 'A small team shipping focused, meaningful improvements rather than feature bloat.',
  },
]

function initials(name: string) {
  return name
    .split(' ')
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
}

export default function About() {
  return (
    <div className="space-y-8">
      {/* hero */}
      <section className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-cyan-950/40 p-8 shadow-glow sm:p-10">
        <div className="pointer-events-none absolute -right-20 -top-20 h-60 w-60 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="relative max-w-2xl">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
            About us
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Making the market&apos;s posture legible
          </h1>
          <p className="mt-4 text-base leading-7 text-slate-300">
            Price Flow Tracker watches the sector ETFs behind the Nasdaq-100 and turns
            them into one clear read — the market&apos;s trend regime, plus the leadership,
            breadth, and fragility behind it. No noise, no hype.
          </p>
        </div>
      </section>

      {/* stats */}
      <section className="grid gap-4 sm:grid-cols-3">
        {stats.map((s) => (
          <div
            key={s.label}
            className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 text-center shadow-card"
          >
            <p className="text-3xl font-semibold text-cyan-300">{s.value}</p>
            <p className="mt-1 text-sm text-slate-400">{s.label}</p>
          </div>
        ))}
      </section>

      {/* story */}
      <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-8 shadow-glow">
        <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
          Our story
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Built by traders and engineers</h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">
          We built Price Flow Tracker because watching QQQ alone tells you almost
          nothing about whether a move is healthy. The answer lives in the internals —
          which sectors lead, whether breadth confirms, and where price sits relative
          to its long-term trend. Our mission is to make that picture clear enough to
          read in seconds.
        </p>
      </section>

      {/* values */}
      <section>
        <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
          What we value
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-white">How we work</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          {values.map((v) => (
            <div
              key={v.title}
              className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-card transition hover:-translate-y-0.5 hover:border-slate-700"
            >
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-cyan-500/15 text-lg">
                {v.icon}
              </span>
              <h3 className="mt-4 text-base font-semibold text-white">{v.title}</h3>
              <p className="mt-1.5 text-sm leading-6 text-slate-400">{v.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* team */}
      <section>
        <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
          The team
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-white">Who&apos;s behind it</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          {team.map((m) => (
            <div
              key={m.name}
              className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-card"
            >
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-gradient-to-br from-cyan-400 to-indigo-500 text-sm font-bold text-slate-950">
                {initials(m.name)}
              </span>
              <div>
                <p className="text-sm font-semibold text-white">{m.name}</p>
                <p className="text-xs text-slate-400">{m.role}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
