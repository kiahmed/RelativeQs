import React, { useState } from 'react'

const inputCls =
  'w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 ' +
  'text-slate-100 outline-none transition focus:border-cyan-400'

const channels = [
  { icon: '✉️', label: 'Email', value: 'hello@priceflow.example', href: 'mailto:hello@priceflow.example' },
  { icon: '📞', label: 'Phone', value: '+1 (234) 567-890', href: 'tel:+1234567890' },
  { icon: '📍', label: 'Office', value: 'New York, NY' },
  { icon: '🕒', label: 'Hours', value: 'Mon–Fri, 9:00–18:00 ET' },
]

export default function Contact() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // no backend: open the user's mail client as a fallback
    const mailto = `mailto:hello@priceflow.example?subject=${encodeURIComponent(
      'Contact from ' + name,
    )}&body=${encodeURIComponent(message + '\n\nFrom: ' + name + ' <' + email + '>')}`
    window.location.href = mailto
  }

  return (
    <div className="space-y-8">
      {/* hero */}
      <section className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-indigo-950/40 p-8 shadow-glow sm:p-10">
        <div className="pointer-events-none absolute -right-20 -top-20 h-60 w-60 rounded-full bg-indigo-500/10 blur-3xl" />
        <div className="relative max-w-2xl">
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
            Contact
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Get in touch
          </h1>
          <p className="mt-4 text-base leading-7 text-slate-300">
            Questions about the product, partnerships, or feedback — we&apos;d love to
            hear from you.
          </p>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* form */}
        <form
          onSubmit={handleSubmit}
          className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-glow sm:p-8"
        >
          <h2 className="text-lg font-semibold text-white">Send a message</h2>
          <div className="mt-5 space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-200" htmlFor="c-name">
                Your name
              </label>
              <input
                id="c-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Doe"
                className={`mt-2 ${inputCls}`}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-200" htmlFor="c-email">
                Email address
              </label>
              <input
                id="c-email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className={`mt-2 ${inputCls}`}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-200" htmlFor="c-msg">
                Message
              </label>
              <textarea
                id="c-msg"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="How can we help?"
                rows={6}
                className={`mt-2 ${inputCls}`}
              />
            </div>
            <button
              type="submit"
              className="rounded-2xl bg-gradient-to-r from-cyan-400 to-indigo-500 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:opacity-90"
            >
              Send message
            </button>
          </div>
        </form>

        {/* channels */}
        <aside className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-glow">
          <h2 className="text-lg font-semibold text-white">Other ways to reach us</h2>
          <div className="mt-5 space-y-3">
            {channels.map((c) => (
              <div
                key={c.label}
                className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-950/60 px-4 py-3"
              >
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-cyan-500/15 text-base">
                  {c.icon}
                </span>
                <div className="min-w-0">
                  <p className="text-[0.65rem] uppercase tracking-[0.2em] text-slate-500">
                    {c.label}
                  </p>
                  {c.href ? (
                    <a href={c.href} className="text-sm text-cyan-300 hover:text-cyan-200">
                      {c.value}
                    </a>
                  ) : (
                    <p className="text-sm text-slate-200">{c.value}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  )
}
