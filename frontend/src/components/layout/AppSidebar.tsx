'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '@/lib/hooks/use-auth'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { LogOut } from 'lucide-react'

import { TuTBrandIcon } from '@/components/common/TuTBrandIcon'

export function AppSidebar() {
  const pathname = usePathname() || ''
  const { user, isAdmin, logout } = useAuth()
  const { data: notebooks = [] } = useNotebooks(false)

  const displayName = user?.display_name || user?.username || 'Ahmed Arfa'
  const initials = displayName
    .split(' ')
    .filter(Boolean)
    .map((n) => n[0])
    .join('')
    .slice(0, 2)
    .toUpperCase() || 'AA'

  const isActive = (href: string) => {
    if (href === '/tut') {
      return pathname === '/tut' || pathname.startsWith('/tut/')
    }
    if (href === '/notebooks') {
      return pathname === '/notebooks' || pathname.startsWith('/notebooks/')
    }
    if (href === '/search') {
      return pathname === '/search' || pathname.startsWith('/search/')
    }
    return pathname === href || pathname.startsWith(href + '/')
  }

  return (
    <aside id="side" className="tut-side">
      {/* Brand / Logo */}
      <div className="brand flex items-center gap-2.5">
        <TuTBrandIcon size={32} className="text-[var(--gold)]" />
        <b style={{ letterSpacing: '0.2em' }}>TuT AI</b>
      </div>

      {/* Main Nav */}
      <Link
        href="/tut"
        className={`nav new ${isActive('/tut') ? 'on' : ''}`}
      >
        <svg className="i" viewBox="0 0 24 24">
          <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
        </svg>
        <span>New chat</span>
      </Link>

      <Link
        href="/search"
        className={`nav ${isActive('/search') ? 'on' : ''}`}
      >
        <svg className="i" viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <span>Search</span>
      </Link>

      <Link
        href="/notebooks"
        className={`nav ${isActive('/notebooks') ? 'on' : ''}`}
      >
        <svg className="i" viewBox="0 0 24 24">
          <path d="M2 5h7a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H2zM22 5h-7a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h8z" />
        </svg>
        <span>Notebooks</span>
      </Link>

      <Link
        href="/sources"
        className={`nav ${isActive('/sources') ? 'on' : ''}`}
      >
        <svg className="i" viewBox="0 0 24 24">
          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5" />
        </svg>
        <span>Sources</span>
      </Link>

      <Link
        href="/files"
        className={`nav ${isActive('/files') ? 'on' : ''}`}
      >
        <svg className="i" viewBox="0 0 24 24">
          <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2z" />
        </svg>
        <span>Files</span>
      </Link>

      <Link
        href="/podcasts"
        className={`nav ${isActive('/podcasts') ? 'on' : ''}`}
      >
        <svg className="i" viewBox="0 0 24 24">
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
        </svg>
        <span>Podcasts</span>
      </Link>

      {isAdmin && (
        <Link
          href="/admin"
          className={`nav ${isActive('/admin') ? 'on' : ''}`}
        >
          <svg className="i" viewBox="0 0 24 24">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span>Admin</span>
        </Link>
      )}

      {/* Recent notebooks section */}
      <div className="lbl">Recent</div>
      <div className="hist">
        {notebooks.slice(0, 8).map((nb) => (
          <Link
            key={nb.id}
            href={`/notebooks/${encodeURIComponent(nb.id)}`}
            className={`nav ${pathname === `/notebooks/${nb.id}` ? 'on' : ''}`}
            title={nb.name}
          >
            {nb.name}
          </Link>
        ))}
      </div>

      {/* User profile footer */}
      <div className="user-box">
        <div className="av">{initials}</div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-[#ececec] truncate">{displayName}</div>
          <small>TuT AI</small>
        </div>
        <button
          type="button"
          onClick={() => logout?.()}
          title="Sign out"
          className="text-[#8b8b8b] hover:text-[#ececec] transition-colors p-1"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </aside>
  )
}
