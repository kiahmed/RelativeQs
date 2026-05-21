import React from 'react'

export default function About() {
  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-8 shadow-glow">
        <h1 className="text-3xl font-semibold text-white">About Us</h1>
        <p className="mt-3 text-slate-300">
          Price Flow Tracker combines market microstructure insights with modern UX to help traders and analysts
          monitor sector leadership and liquidity regimes in real time.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-4 rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
          <h2 className="text-2xl font-semibold text-white">Company story</h2>
          <p className="text-slate-300">Founded by traders and engineers, we built this product to surface meaningful
            signals across sector ETFs without the noise of traditional dashboards.</p>

          <h3 className="mt-4 text-lg font-semibold text-white">Mission & vision</h3>
          <p className="text-slate-300">Our mission is to make actionable market-flow signals accessible and
            interpretable. We envision a world where traders can quickly identify leadership shifts and liquidity
            regimes with confidence.</p>
        </section>

        <section className="space-y-4 rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
          <h2 className="text-2xl font-semibold text-white">Team members</h2>
          <ul className="space-y-3 text-slate-200">
            <li className="rounded-2xl bg-slate-950/80 p-3">Alex Morgan — Founder & CEO</li>
            <li className="rounded-2xl bg-slate-950/80 p-3">Priya Patel — Head of Data Science</li>
            <li className="rounded-2xl bg-slate-950/80 p-3">Samir Khan — Lead Engineer</li>
          </ul>

          <h3 className="mt-4 text-lg font-semibold text-white">Company values</h3>
          <p className="text-slate-300">Transparency, rigor, and fast iteration drive our product decisions.</p>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
          <h2 className="text-2xl font-semibold text-white">Achievements & statistics</h2>
          <ul className="mt-4 space-y-3 text-slate-200">
            <li className="flex items-center justify-between bg-slate-950/80 rounded-2xl px-4 py-3">
              <span>Active users</span>
              <strong>2,400+</strong>
            </li>
            <li className="flex items-center justify-between bg-slate-950/80 rounded-2xl px-4 py-3">
              <span>Signals processed daily</span>
              <strong>1M+</strong>
            </li>
            <li className="flex items-center justify-between bg-slate-950/80 rounded-2xl px-4 py-3">
              <span>Average latency</span>
              <strong>~800ms</strong>
            </li>
          </ul>
        </section>

        <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
          <h2 className="text-2xl font-semibold text-white">Certifications & awards</h2>
          <p className="mt-3 text-slate-300">Recognized by industry workshops for innovation in market analytics.</p>
          <ul className="mt-4 space-y-2 text-slate-200">
            <li className="rounded-2xl bg-slate-950/80 px-4 py-3">Top Fintech Startup — Market Innovators 2024</li>
            <li className="rounded-2xl bg-slate-950/80 px-4 py-3">Data Privacy & Security Accreditation</li>
          </ul>
        </section>
      </div>
    </div>
  )
}
