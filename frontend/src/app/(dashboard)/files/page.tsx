'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Search } from 'lucide-react'
import { toast } from 'sonner'

import { AppShell } from '@/components/layout/AppShell'
import { FileCard } from '@/components/files/FileCard'
import { filesApi } from '@/lib/api/studio'
import { cn } from '@/lib/utils'
import { useFilePanel } from '@/lib/stores/file-panel-store'

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'presentation', label: 'Presentations' },
  { id: 'report', label: 'Reports' },
  { id: 'infographic', label: 'Infographs' },
  { id: 'spreadsheet', label: 'Spreadsheets' },
]

export default function FilesPage() {
  return (
    <Suspense>
      <FilesLibrary />
    </Suspense>
  )
}

function FilesLibrary() {
  const qc = useQueryClient()
  const { data: files = [], isLoading } = useQuery({ queryKey: ['studio-files'], queryFn: () => filesApi.list(), refetchInterval: 10000 })
  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')
  const params = useSearchParams()
  const openFile = useFilePanel((s) => s.open)
  // Links from Tut Agent and Studio (/files?open=<id>) open the same file in the viewer
  useEffect(() => {
    const id = params.get('open')
    if (id) {
      openFile(id)
      if (params.get('embed') === 'true') {
        useFilePanel.setState({ fullscreen: true })
      }
    }
  }, [params, openFile])

  const shown = useMemo(
    () =>
      files.filter(
        (f) =>
          (filter === 'all' || f.kind === filter) &&
          (!q || `${f.filename} ${f.notebook_name ?? ''}`.toLowerCase().includes(q.toLowerCase()))
      ),
    [files, filter, q]
  )

  const remove = async (id: string) => {
    try {
      await filesApi.remove(id)
      qc.invalidateQueries({ queryKey: ['studio-files'] })
    } catch {
      toast.error('Could not delete the file')
    }
  }

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
          <div className="flex flex-col gap-1">
            <h1 className="text-2xl font-semibold tracking-tight text-[#f3f1ea]">Files</h1>
            <p className="text-sm text-[#a9afb9]">
              Everything Studio and TuT Agent produced for you. Open a file to view it, or edit it in the office viewer.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex rounded-xl bg-[#08090b] border border-[rgba(255,255,255,0.09)] p-1" role="tablist" aria-label="File type">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  role="tab"
                  aria-selected={filter === f.id}
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-xs font-medium transition-all cursor-pointer',
                    filter === f.id
                      ? 'bg-[#000000] text-[#f3f1ea] shadow-[0_0_0_1px_rgba(255,255,255,0.38),0_0_14px_-2px_rgba(190,215,255,0.35)]'
                      : 'text-[#a9afb9] hover:text-[#f3f1ea]'
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="relative ml-auto">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#a9afb9]" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search files"
                aria-label="Search files"
                className="h-10 w-64 rounded-xl border border-[rgba(255,255,255,0.09)] bg-[#08090b] pl-9 pr-3 text-xs text-[#f3f1ea] outline-none focus:border-[#efece4] focus:ring-4 focus:ring-[rgba(239,236,228,0.08)] transition-all"
              />
            </div>
          </div>
          {isLoading ? (
            <p className="text-sm text-[#a9afb9]">Loading files…</p>
          ) : shown.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-[rgba(255,255,255,0.14)] py-16 text-center text-[#a9afb9]">
              <FolderOpen className="h-6 w-6 text-[#a9afb9]" />
              <p className="text-sm font-medium text-[#f3f1ea]">No files yet</p>
              <p className="text-sm text-[#a9afb9]">Open a notebook and use Studio, or ask TuT Agent.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {shown.map((f) => (
                <FileCard key={f.id} file={f} onDelete={remove} />
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
