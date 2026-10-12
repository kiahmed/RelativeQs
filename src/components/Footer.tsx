import { useState } from 'react'
import { Link } from 'react-router-dom'
import Logo from './Logo'

// TODO: point these at the real RelativeQs handles when live.
const X_URL = 'https://x.com/relativeqs'
const LINKEDIN_URL = 'https://www.linkedin.com/company/relativeqs'

function IconX({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24h-6.66l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231 5.45-6.231Zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77Z" />
    </svg>
  )
}

function IconLinkedIn({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.13 1.45-2.13 2.94v5.67H9.35V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.07 2.07 0 1 1 0-4.14 2.07 2.07 0 0 1 0 4.14ZM7.12 20.45H3.55V9h3.57v11.45ZM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0Z" />
    </svg>
  )
}

export default function Footer() {
  const year = new Date().getFullYear()
  const [shared, setShared] = useState(false)

  const handleShare = async () => {
    const url = typeof window !== 'undefined' ? window.location.origin : ''
    const shareData = {
      title: 'RelativeQs',
      text: 'See what AI bottlenecks are really driving the Nasdaq — RelativeQs.',
      url,
    }
    try {
      if (navigator.share) {
        await navigator.share(shareData)
        return
      }
      await navigator.clipboard.writeText(url)
      setShared(true)
      setTimeout(() => setShared(false), 1800)
    } catch {
      /* user dismissed share / clipboard blocked — no-op */
    }
  }

  const iconLink =
    'grid h-9 w-9 place-items-center rounded-xl border border-slate-800 bg-slate-900/60 text-slate-400 transition hover:border-slate-600 hover:text-white'

  return (
    <footer className="mt-12 border-t border-slate-800/80 bg-slate-950/60">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-5 px-4 py-7 sm:flex-row sm:px-6 lg:px-8">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-cyan-400 to-indigo-500 text-slate-950">
            <Logo className="h-4 w-4" />
          </span>
          <p className="text-xs text-slate-500">
            © RelativeQs {year}. All rights reserved.{' '}
            <Link to="/about" className="text-slate-400 transition hover:text-slate-200">
              About
            </Link>
            {' · '}
            <Link to="/contact" className="text-slate-400 transition hover:text-slate-200">
              Contact
            </Link>
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <a href={X_URL} target="_blank" rel="noopener noreferrer" aria-label="RelativeQs on X" className={iconLink}>
            <IconX className="h-4 w-4" />
          </a>
          <a
            href={LINKEDIN_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="RelativeQs on LinkedIn"
            className={iconLink}
          >
            <IconLinkedIn className="h-4 w-4" />
          </a>
          <button
            onClick={handleShare}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs font-medium text-slate-300 transition hover:border-slate-600 hover:text-white"
          >
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98" />
            </svg>
            {shared ? 'Link copied' : 'Share'}
          </button>
        </div>
      </div>
    </footer>
  )
}
