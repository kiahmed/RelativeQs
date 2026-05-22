import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useIsPro } from './ProGate'
import { BACKEND_URL } from '../config'

/**
 * Pro-only control for regime-change email alerts: an on/off toggle plus a
 * "send test email" button to verify the email path. Renders nothing for free
 * users (the Pricing page is where they're sold the feature).
 */
export default function AlertToggle() {
  const isPro = useIsPro()
  const token = useAuthStore((s) => s.token)
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testMsg, setTestMsg] = useState('')

  useEffect(() => {
    if (!isPro || !token) return
    fetch(`${BACKEND_URL}/api/alerts/preferences`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) setEnabled(Boolean(d.alerts_enabled))
      })
      .catch(() => {})
  }, [isPro, token])

  if (!isPro) return null

  const toggle = async () => {
    if (!token || enabled === null) return
    const next = !enabled
    setSaving(true)
    try {
      const res = await fetch(`${BACKEND_URL}/api/alerts/preferences`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ alerts_enabled: next }),
      })
      if (res.ok) setEnabled(next)
    } finally {
      setSaving(false)
    }
  }

  const sendTest = async () => {
    if (!token) return
    setTestMsg('')
    setTesting(true)
    try {
      const res = await fetch(`${BACKEND_URL}/api/alerts/test`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const data = await res.json().catch(() => ({}))
      setTestMsg(
        res.ok
          ? `✓ Test email sent to ${data.to ?? 'your inbox'}.`
          : data.detail || 'Could not send the test email.',
      )
    } catch {
      setTestMsg('Could not reach the server to send the test email.')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-5 py-3.5">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="text-lg">🔔</span>
          <div>
            <p className="text-sm font-medium text-white">Regime-change email alerts</p>
            <p className="text-xs text-slate-400">
              Get an email the moment QQQ flips risk-on / risk-off.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={sendTest}
            disabled={testing}
            className="rounded-full border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-cyan-500/50 hover:bg-slate-800 disabled:opacity-50"
          >
            {testing ? 'Sending…' : 'Send test email'}
          </button>
          <button
            onClick={toggle}
            disabled={saving || enabled === null}
            aria-pressed={enabled === true}
            className={`relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50 ${
              enabled ? 'bg-emerald-500' : 'bg-slate-700'
            }`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
                enabled ? 'left-[22px]' : 'left-0.5'
              }`}
            />
          </button>
        </div>
      </div>
      {testMsg && <p className="mt-2 text-xs text-slate-400">{testMsg}</p>}
    </div>
  )
}
