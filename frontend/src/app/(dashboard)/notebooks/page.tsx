'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'

import { AppShell } from '@/components/layout/AppShell'
import { useNotebooks } from '@/lib/hooks/use-notebooks'
import { notebooksApi } from '@/lib/api/notebooks'
import { CreateNotebookDialog } from '@/components/notebooks/CreateNotebookDialog'
import type { RecentlyViewedResponse } from '@/lib/types/api'

export default function NotebooksPage() {
  const router = useRouter()
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')

  const { data: notebooks = [] } = useNotebooks(false)
  const { data: recentItems = [] } = useQuery<RecentlyViewedResponse[]>({
    queryKey: ['recently-viewed', 8],
    queryFn: () => notebooksApi.recentlyViewed(8),
  })

  const normalizedQuery = searchTerm.trim().toLowerCase()

  const filteredActive = useMemo(() => {
    if (!notebooks) return []
    if (!normalizedQuery) return notebooks
    return notebooks.filter(
      (nb) =>
        nb.name.toLowerCase().includes(normalizedQuery) ||
        (nb.description && nb.description.toLowerCase().includes(normalizedQuery))
    )
  }, [notebooks, normalizedQuery])

  const formatRelativeTime = (dateString?: string) => {
    if (!dateString) return 'recently'
    try {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return 'recently'
      return formatDistanceToNow(date, { addSuffix: true })
    } catch (_) {
      return 'recently'
    }
  }

  return (
    <AppShell>
      <section className="view nbv on" id="v-nb" style={{ overflowY: 'auto', flex: 1 }}>
        <div className="in">
          {/* Header */}
          <div className="head">
            <div className="sp" />
            <div className="search">
              <svg className="i" viewBox="0 0 24 24">
                <circle cx="11" cy="11" r="7" />
                <path d="m20 20-3.5-3.5" />
              </svg>
              <input
                id="q"
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search notebooks…"
              />
            </div>
            <div className="seg">
              <button
                type="button"
                id="g"
                className={viewMode === 'grid' ? 'on' : ''}
                onClick={() => setViewMode('grid')}
                title="Grid View"
              >
                <svg className="i" viewBox="0 0 24 24" style={{ width: 16 }}>
                  <rect x="4" y="4" width="6" height="6" />
                  <rect x="14" y="4" width="6" height="6" />
                  <rect x="4" y="14" width="6" height="6" />
                  <rect x="14" y="14" width="6" height="6" />
                </svg>
              </button>
              <button
                type="button"
                id="l"
                className={viewMode === 'list' ? 'on' : ''}
                onClick={() => setViewMode('list')}
                title="List View"
              >
                <svg className="i" viewBox="0 0 24 24" style={{ width: 16 }}>
                  <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />
                </svg>
              </button>
            </div>
            <button
              type="button"
              className="btn go btn-pearl"
              onClick={() => setCreateDialogOpen(true)}
            >
              <svg className="i" viewBox="0 0 24 24" style={{ width: 16 }}>
                <path d="M12 5v14M5 12h14" />
              </svg>
              New Notebook
            </button>
          </div>

          {/* Recently viewed */}
          {recentItems.length > 0 && (
            <>
              <h3 className="sec">Recently viewed</h3>
              <div className="rec recent" id="rec">
                {recentItems.slice(0, 8).map((r, i) => {
                  const isSource = r.type === 'source'
                  const href = isSource
                    ? `/sources/${encodeURIComponent(r.id)}`
                    : `/notebooks/${encodeURIComponent(r.id)}`

                  return (
                    <Link
                      key={r.id + i}
                      href={href}
                      className={`r row ${isSource ? 's' : ''}`}
                    >
                      {isSource ? (
                        <svg className="i" viewBox="0 0 24 24">
                          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5" />
                        </svg>
                      ) : (
                        <svg className="i" viewBox="0 0 24 24">
                          <path d="M2 5h7a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H2zM22 5h-7a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h8z" />
                        </svg>
                      )}
                      <span>{r.title}</span>
                      <i className="k tag">{isSource ? 'SOURCE' : 'NOTEBOOK'}</i>
                      <small className="when">{formatRelativeTime(r.last_viewed_at)}</small>
                    </Link>
                  )
                })}
              </div>
            </>
          )}

          {/* Active notebooks */}
          <h3 className="sec">
            Active notebooks · <span id="cnt">{filteredActive.length}</span>
          </h3>

          <div className={`grid ${viewMode === 'list' ? 'list' : ''}`} id="grid">
            {filteredActive.map((nb) => (
              <div
                key={nb.id}
                className="card card-obsidian"
                onClick={() => router.push(`/notebooks/${encodeURIComponent(nb.id)}`)}
              >
                <div className="ic">
                  <svg className="i" viewBox="0 0 24 24">
                    <path d="M2 5h7a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H2zM22 5h-7a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h8z" />
                  </svg>
                </div>
                <h4>{nb.name}</h4>
                <p>{nb.description || 'No description'}</p>
                <div className="meta ft">
                  <span>Updated {formatRelativeTime(nb.updated)}</span>
                  <span>
                    <svg className="i" viewBox="0 0 24 24" style={{ width: 13, verticalAlign: -2 }}>
                      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5" />
                    </svg>{' '}
                    {nb.source_count ?? 1}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {filteredActive.length === 0 && (
            <p className="sub" style={{ marginTop: 16 }}>No notebooks found.</p>
          )}

          {/* Footer */}
          <div className="foot">
            <span>TuT AI · Ministry of Communications and Information Technology</span>
            <span>Developed by Eng Ahmed Arfa for MCIT</span>
          </div>
        </div>
      </section>

      <CreateNotebookDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
      />
    </AppShell>
  )
}
