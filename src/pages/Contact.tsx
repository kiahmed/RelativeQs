import React, { useState } from 'react'

export default function Contact() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // no backend: open mail client as fallback
    const mailto = `mailto:hello@priceflow.example?subject=${encodeURIComponent(
      'Contact from ' + name,
    )}&body=${encodeURIComponent(message + '\n\nFrom: ' + name + ' <' + email + '>')}`
    window.location.href = mailto
  }

  return (
    <div className="space-y-8">
      <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-8">
        <h1 className="text-3xl font-semibold text-white">Contact</h1>
        <p className="mt-3 text-slate-300">We&apos;d love to hear from you — sales, partnerships, or general questions.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <form onSubmit={handleSubmit} className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6">
          <h2 className="text-2xl font-semibold text-white">Contact form</h2>
          <div className="mt-4 space-y-4">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-slate-100"
            />
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Email address"
              className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-slate-100"
            />
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="How can we help?"
              className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-slate-100"
              rows={6}
            />
            <div>
              <button className="rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950">Send</button>
            </div>
          </div>
        </form>

        <aside className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 space-y-4">
          <h2 className="text-2xl font-semibold text-white">Other ways to reach us</h2>
          <p className="text-slate-200">Email: <a className="text-cyan-300" href="mailto:hello@priceflow.example">hello@priceflow.example</a></p>
          <p className="text-slate-200">Phone: <a className="text-cyan-300" href="tel:+1234567890">+1 (234) 567-890</a></p>
          <div>
            <h3 className="text-white font-semibold">Office location</h3>
            <p className="text-slate-300">New York, NY — <em>Map placeholder</em></p>
          </div>
          <div>
            <h3 className="text-white font-semibold">Social</h3>
            <div className="mt-2 flex gap-3">
              <a className="text-cyan-300" href="#">Twitter</a>
              <a className="text-cyan-300" href="#">LinkedIn</a>
              <a className="text-cyan-300" href="#">GitHub</a>
            </div>
          </div>
          <div>
            <h3 className="text-white font-semibold">Business hours</h3>
            <p className="text-slate-300">Mon–Fri: 9:00 — 18:00 ET</p>
          </div>
        </aside>
      </div>
    </div>
  )
}
