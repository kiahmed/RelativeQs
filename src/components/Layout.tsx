import { Suspense } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuthStore } from '../store/useAuthStore'
import Logo from './Logo'
import Footer from './Footer'

/** Shown while a lazy-loaded page chunk is being fetched. */
function PageFallback() {
  return (
    <div className="grid min-h-[50vh] place-items-center text-sm text-slate-400">
      <span className="animate-pulse">Loading…</span>
    </div>
  )
}

const navLinks = [
  { label: 'Home', href: '/' },
  { label: 'About', href: '/about' },
  { label: 'Pricing', href: '/pricing' },
  { label: 'Contact', href: '/contact' },
  { label: 'Dashboard', href: '/dashboard' },
]

export default function Layout() {
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  return (
    <div className="flex min-h-screen flex-col text-slate-100">
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-4 py-3.5 sm:px-6">
          <Link to="/" className="group flex items-center gap-2.5">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-500 text-slate-950 shadow-glow transition group-hover:scale-105">
              <Logo className="h-5 w-5" />
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-lg font-semibold tracking-tight text-white">
                Relative<span className="text-cyan-300">Qs</span>
              </span>
              <span className="hidden whitespace-nowrap text-[0.72rem] text-slate-300 lg:block">
                What&apos;s driving{' '}
                <span className="text-sm font-semibold text-white">QQQ</span> intraday —
                leadership, breadth &amp;{' '}
                <span className="font-medium text-fuchsia-300">AI-infra bottlenecks</span>
              </span>
            </span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            {navLinks.map((link) => (
              <NavLink
                key={link.href}
                to={link.href}
                end={link.href === '/'}
                className={({ isActive }) =>
                  `rounded-full px-3.5 py-2 text-sm font-medium transition ${
                    isActive
                      ? 'bg-slate-800 text-white shadow-inner'
                      : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-100'
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            {user ? (
              <>
                {user.plan === 'pro' && (
                  <span className="hidden rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-emerald-300 sm:inline">
                    Pro
                  </span>
                )}
                <Link
                  to="/account"
                  className="hidden text-sm text-slate-400 transition hover:text-slate-100 sm:inline"
                >
                  {user.fullName || user.email}
                </Link>
                <button
                  onClick={logout}
                  className="rounded-full border border-slate-700 px-3.5 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 hover:bg-slate-800"
                >
                  Log out
                </button>
              </>
            ) : (
              <Link
                to="/login"
                className="rounded-full bg-gradient-to-r from-cyan-400 to-indigo-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:opacity-90"
              >
                Login
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
        <Suspense fallback={<PageFallback />}>
          <Outlet />
        </Suspense>
      </main>

      <Footer />
    </div>
  )
}
