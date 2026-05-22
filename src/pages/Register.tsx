import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const inputCls =
  'mt-2 w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 ' +
  'text-slate-100 outline-none transition focus:border-cyan-400'

export default function Register() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const register = useAuthStore((state) => state.register)
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()

  useEffect(() => {
    if (user) navigate('/dashboard')
  }, [user, navigate])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setNotice('')

    if (!fullName.trim()) {
      setError('Enter your full name.')
      return
    }
    if (!emailRegex.test(email)) {
      setError('Enter a valid email address.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters long.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    const result = await register(fullName.trim(), email.trim(), password)
    setSubmitting(false)

    if (!result.ok) {
      setError(result.error || 'Unable to create account.')
      return
    }
    if (result.message) {
      // email confirmation required — stay here and show guidance
      setNotice(result.message)
      return
    }
    navigate('/dashboard')
  }

  return (
    <div className="mx-auto max-w-md">
      <div className="relative overflow-hidden rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-indigo-950/40 p-8 shadow-glow">
        <div className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full bg-indigo-500/10 blur-3xl" />
        <div className="relative">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-lg font-bold text-slate-950">
            ◈
          </span>
          <p className="mt-5 text-[0.7rem] font-semibold uppercase tracking-[0.25em] text-cyan-300/80">
            Get started
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-white">Create your account</h1>
          <p className="mt-1.5 text-sm text-slate-400">
            Free to start — track the market regime in minutes.
          </p>

          <form onSubmit={handleSubmit} className="mt-7 space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-200" htmlFor="fullName">
                Full name
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                className={inputCls}
                placeholder="Jane Doe"
              />
            </div>

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
                placeholder="At least 8 characters"
              />
            </div>

            <div>
              <label
                className="block text-sm font-medium text-slate-200"
                htmlFor="confirmPassword"
              >
                Confirm password
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                className={inputCls}
                placeholder="Repeat your password"
              />
            </div>

            {error && <p className="text-sm text-rose-400">{error}</p>}
            {notice && <p className="text-sm text-emerald-400">{notice}</p>}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-2xl bg-gradient-to-r from-cyan-400 to-indigo-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? 'Creating account…' : 'Create account'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-cyan-300 hover:text-cyan-200">
              Log in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
