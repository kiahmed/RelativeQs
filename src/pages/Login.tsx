import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const inputCls =
  'mt-2 w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 ' +
  'text-slate-100 outline-none transition focus:border-cyan-400'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const login = useAuthStore((state) => state.login)
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()

  useEffect(() => {
    if (user) navigate('/dashboard')
  }, [user, navigate])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')

    if (!emailRegex.test(email)) {
      setError('Enter a valid email address.')
      return
    }
    if (!password) {
      setError('Enter your password.')
      return
    }

    setSubmitting(true)
    const result = await login(email.trim(), password)
    setSubmitting(false)

    if (!result.ok) {
      setError(result.error || 'Unable to sign in.')
      return
    }
    navigate('/dashboard')
  }

  return (
    <div className="mx-auto max-w-md">
      <div className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-cyan-950/40 p-8 shadow-glow">
        <div className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="relative">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-lg font-bold text-slate-950">
            ◈
          </span>
          <p className="mt-5 text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
            Welcome back
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-white">Sign in to your account</h1>
          <p className="mt-1.5 text-sm text-slate-400">
            Access your live market-regime dashboard.
          </p>

          <form onSubmit={handleSubmit} className="mt-7 space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-200" htmlFor="email">
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className={inputCls}
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-200" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className={inputCls}
                placeholder="Enter your password"
              />
            </div>

            {error && <p className="text-sm text-rose-400">{error}</p>}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-2xl bg-gradient-to-r from-cyan-400 to-indigo-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            Don&apos;t have an account?{' '}
            <Link to="/register" className="font-semibold text-cyan-300 hover:text-cyan-200">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
