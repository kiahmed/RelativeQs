import React from 'react'

function Tier({ name, price, bullets, cta }: { name: string; price: string; bullets: string[]; cta?: string }) {
  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
      <h3 className="text-xl font-semibold text-white">{name}</h3>
      <p className="mt-2 text-3xl font-bold text-white">{price}</p>
      <ul className="mt-4 space-y-2 text-slate-200">
        {bullets.map((b) => (
          <li key={b} className="rounded-2xl bg-slate-950/80 px-3 py-2">
            {b}
          </li>
        ))}
      </ul>
      <div className="mt-4">
        <button className="rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950">{cta || 'Get started'}</button>
      </div>
    </div>
  )
}

export default function Pricing() {
  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-8">
        <h1 className="text-3xl font-semibold text-white">Pricing</h1>
        <p className="mt-3 text-slate-300">Flexible plans for traders, teams, and enterprises.</p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Tier name="Starter" price="Free" bullets={["Basic signals", "Community support", "1 watchlist"]} cta="Sign up" />
        <Tier name="Pro" price="$29/mo" bullets={["Real-time signals", "Email alerts", "3 watchlists"]} cta="Start trial" />
        <Tier name="Team" price="$99/mo" bullets={["Priority support", "Team seats", "API access"]} cta="Contact sales" />
      </div>

      <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
        <h2 className="text-2xl font-semibold text-white">Feature comparison</h2>
        <p className="mt-3 text-slate-300">Compare features across plans to pick the right fit.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full table-auto text-left text-sm text-slate-200">
            <thead>
              <tr>
                <th className="px-3 py-2">Feature</th>
                <th className="px-3 py-2">Starter</th>
                <th className="px-3 py-2">Pro</th>
                <th className="px-3 py-2">Team</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-3 py-2">Real-time signals</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2">✓</td>
                <td className="px-3 py-2">✓</td>
              </tr>
              <tr>
                <td className="px-3 py-2">Email alerts</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2">✓</td>
                <td className="px-3 py-2">✓</td>
              </tr>
              <tr>
                <td className="px-3 py-2">API access</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2">—</td>
                <td className="px-3 py-2">✓</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
        <h2 className="text-2xl font-semibold text-white">Frequently asked questions</h2>
        <div className="mt-4 space-y-3 text-slate-200">
          <details className="rounded-2xl bg-slate-950/80 p-3">
            <summary className="cursor-pointer">Do you offer a free trial?</summary>
            <p className="mt-2 text-slate-300">Yes — Pro includes a 14-day free trial for new users.</p>
          </details>
          <details className="rounded-2xl bg-slate-950/80 p-3">
            <summary className="cursor-pointer">Is there an enterprise option?</summary>
            <p className="mt-2 text-slate-300">We offer custom enterprise plans with SSO, dedicated SLAs, and API access.</p>
          </details>
        </div>
      </section>
    </div>
  )
}
