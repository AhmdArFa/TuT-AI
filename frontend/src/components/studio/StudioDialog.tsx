'use client'

import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronDown, Circle, FileSpreadsheet, FileText, Loader2, PenTool, Presentation, X } from 'lucide-react'

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { FileCard } from '@/components/files/FileCard'
import { TutAvatar } from '@/components/tut/TutAvatar'
import { followJob, formatTokens, JobEvent, LibraryFile, PresetId, PresetMode, StudioPreset, studioApi } from '@/lib/api/studio'
import { cn } from '@/lib/utils'

// Midnight Noir swatches: background, surface, accent
const NOIR_DARK = ['#010612', '#030F1F', '#16A6E9']
const NOIR_LIGHT = ['#FFFFFF', '#F2F5F9', '#1E507A']
const LOOK: Record<PresetId, { icon: typeof FileText }> = {
  presentation: { icon: Presentation },
  report: { icon: FileText },
  infograph: { icon: PenTool },
  spreadsheet: { icon: FileSpreadsheet },
}

const FALLBACK: StudioPreset[] = [
  { id: 'presentation', name: 'Presentation', description: 'Midnight Noir briefing deck with the constant covers and native charts.', modes: ['dark', 'light'], outputs: ['pptx', 'pdf'], ready: true },
  { id: 'report', name: 'Report', description: 'Noir report as a print PDF and an editable Word document.', modes: ['dark', 'light'], outputs: ['pdf', 'docx'], lengths: ['short', 'medium', 'long'], ready: true },
  { id: 'infograph', name: 'Infograph', description: 'One-page sketchnote with hand-drawn artwork.', modes: ['light', 'dark'], outputs: ['png', 'pdf', 'svg'], ready: true },
  { id: 'spreadsheet', name: 'Spreadsheet', description: 'Noir report workbook: paste your figures, every computed cell is a formula.', modes: ['dark', 'light'], outputs: ['xlsx'], ready: true },
]

interface Step {
  id: string
  title: string
  status: 'running' | 'done' | 'error'
  notes: string[]
}

function steps(events: JobEvent[]): Step[] {
  const list: Step[] = []
  for (const ev of events) {
    if (ev.type === 'step') {
      const existing = list.find((s) => s.id === ev.id)
      if (existing) existing.status = ev.status
      else list.push({ id: ev.id, title: ev.title || 'Working', status: ev.status, notes: [] })
    } else if (ev.type === 'progress') {
      const target = list.find((s) => s.id === ev.step_id) ?? list[list.length - 1]
      target?.notes.push(ev.message)
    }
  }
  return list
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </div>
  )
}

function Segmented<T extends string>({ value, options, onChange, disabled }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; disabled?: boolean }) {
  return (
    <div className="flex rounded-lg bg-muted p-1" role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={cn('flex-1 rounded-md px-3 py-1.5 text-sm transition-colors', value === o.value ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground hover:text-foreground')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

interface StudioDialogProps {
  notebookId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function StudioDialog({ notebookId, open, onOpenChange }: StudioDialogProps) {
  const qc = useQueryClient()
  const { data: presets = FALLBACK } = useQuery({ queryKey: ['studio-presets'], queryFn: studioApi.presets, enabled: open })
  const [preset, setPreset] = useState<PresetId>('presentation')
  const [mode, setMode] = useState<PresetMode>('dark')
  const [slideCount, setSlideCount] = useState(10)
  const [length, setLength] = useState<'short' | 'medium' | 'long'>('medium')
  const [audience, setAudience] = useState('senior leadership')
  const [instructions, setInstructions] = useState('')
  const [template, setTemplate] = useState<'default' | 'custom'>('default')
  const [design, setDesign] = useState('')
  const [usage, setUsage] = useState<{ input_tokens: number; output_tokens: number; calls: number } | null>(null)
  const [openSteps, setOpenSteps] = useState<Record<string, boolean>>({})
  const [events, setEvents] = useState<JobEvent[]>([])
  const [files, setFiles] = useState<LibraryFile[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const running = jobId !== null

  const current = presets.find((p) => p.id === preset)
  useEffect(() => {
    if (current && !current.modes.includes(mode)) setMode(current.modes[0])
  }, [current, mode])

  const timeline = useMemo(() => steps(events), [events])

  const generate = async () => {
    setEvents([])
    setFiles([])
    setUsage(null)
    setMessage(null)
    setError(null)
    try {
      const job = await studioApi.start({
        notebook_id: notebookId,
        preset,
        mode,
        slide_count: slideCount,
        length,
        audience,
        template,
        design: template === 'custom' ? design.trim() || null : null,
        instructions: instructions.trim() || null,
      })
      setJobId(job.id)
      await followJob(job.id, (evs) => {
        setEvents((e) => [...e, ...evs])
        for (const ev of evs) {
          if (ev.type === 'file') setFiles((f) => (f.some((x) => x.id === ev.file.id) ? f : [...f, ev.file]))
          if (ev.type === 'message') setMessage(ev.content)
          if (ev.type === 'usage') setUsage({ input_tokens: ev.input_tokens, output_tokens: ev.output_tokens, calls: ev.calls })
          if (ev.type === 'error') setError(ev.message)
        }
      })
      qc.invalidateQueries({ queryKey: ['studio-files'] })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'The job could not start')
    } finally {
      setJobId(null)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto rounded-2xl sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg font-semibold">
            <TutAvatar size={24} /> Studio
          </DialogTitle>
          <DialogDescription>TuT Agent writes from this notebook; the document engines build and check every file.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 md:grid-cols-[1fr_1fr]">
          <div className="flex flex-col gap-5">
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="What to create">
              {presets.map((p) => {
                const look = LOOK[p.id]
                const Icon = look.icon
                const sw = (p.id === preset ? mode : p.modes[0]) === 'dark' ? NOIR_DARK : NOIR_LIGHT
                return (
                  <button
                    key={p.id}
                    type="button"
                    role="radio"
                    aria-checked={preset === p.id}
                    disabled={running || !p.ready}
                    onClick={() => setPreset(p.id)}
                    className={cn(
                      'flex flex-col gap-2 rounded-xl border p-3 text-left transition-colors disabled:opacity-50',
                      preset === p.id ? 'border-primary/60 bg-muted' : 'hover:bg-muted/50'
                    )}
                  >
                    <div className="flex h-9 overflow-hidden rounded-md border border-border">
                      <span className="flex-[3]" style={{ background: sw[0] }} />
                      <span className="flex-[2]" style={{ background: sw[1] }} />
                      <span className="flex-1" style={{ background: sw[2] }} />
                    </div>
                    <span className="flex items-center gap-2 text-sm font-medium">
                      <Icon className="h-4 w-4 text-primary" /> {p.name}
                    </span>
                    <span className="text-xs text-muted-foreground">{p.description}</span>
                    {!p.ready && <span className="text-[11px] text-muted-foreground">Needs: {(p.missing || []).join(', ') || 'document engines'}</span>}
                  </button>
                )
              })}
            </div>

            <Field label="Design" hint={template === 'default' ? 'The approved template, generated straight away.' : 'Starts from the approved template, applies your direction, then checks and fixes the file up to five times.'}>
              <Segmented value={template} onChange={setTemplate} disabled={running} options={[{ value: 'default', label: 'Default template' }, { value: 'custom', label: 'Custom' }]} />
            </Field>
            {template === 'custom' && (
              <Field label="Design direction" hint="For example: more visual, data first, compact, calmer royal accent.">
                <Textarea value={design} onChange={(e) => setDesign(e.target.value)} disabled={running} rows={2} />
              </Field>
            )}

            {current && current.modes.length > 1 && (
              <Field label="Style">
                <Segmented value={mode} onChange={setMode} disabled={running} options={[{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }]} />
              </Field>
            )}

            {preset === 'presentation' && (
              <Field
                label={`Total Slides: ${slideCount}`}
                hint={
                  slideCount >= 6
                    ? `${slideCount - 3} content slides + title cover, agenda & closing (${slideCount} total)`
                    : `${slideCount - 2} content slides + title cover & closing (${slideCount} total)`
                }
              >
                <input
                  type="range"
                  min={4}
                  max={20}
                  value={slideCount}
                  disabled={running}
                  onChange={(e) => setSlideCount(Number(e.target.value))}
                  className="accent-[var(--primary)]"
                  aria-label="Number of slides"
                />
              </Field>
            )}
            {preset === 'report' && (
              <Field label="Length">
                <Segmented value={length} onChange={setLength} disabled={running} options={[{ value: 'short', label: 'Short' }, { value: 'medium', label: 'Medium' }, { value: 'long', label: 'Long' }]} />
              </Field>
            )}

            <Field label="Audience">
              <Input value={audience} onChange={(e) => setAudience(e.target.value)} disabled={running} />
            </Field>
            <Field label={preset === 'spreadsheet' ? 'Figures and instructions' : 'Instructions for TuT Agent'} hint={preset === 'spreadsheet' ? 'Paste your figures (a table, or one line per indicator). TuT enters them exactly; changes and totals are formulas.' : 'Optional: focus, sections to include, figures to highlight.'}>
              <Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} disabled={running} rows={preset === 'spreadsheet' ? 6 : 3} className={preset === 'spreadsheet' ? 'font-mono text-xs' : undefined} />
            </Field>

            <div className="flex gap-2">
              <Button onClick={generate} disabled={running || !current?.ready} className="h-10 flex-1 rounded-xl">
                {running && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {running ? 'Working' : events.length ? 'Create again' : 'Create'}
              </Button>
              {running && jobId && (
                <Button variant="outline" className="h-10 rounded-xl" onClick={() => studioApi.cancel(jobId)}>
                  Stop
                </Button>
              )}
            </div>
          </div>

          <div className="flex min-h-[420px] flex-col gap-3 rounded-2xl border border-border bg-muted/40 p-4" aria-live="polite">
            {!events.length && !running && (
              <div className="m-auto flex max-w-xs flex-col items-center gap-3 text-center text-sm text-muted-foreground">
                <TutAvatar size={48} />
                Progress and finished files appear here.
              </div>
            )}
            {timeline.length > 0 && (
              <ol className="flex flex-col gap-3">
                {timeline.map((s) => (
                  <li key={s.id} className="flex gap-3">
                    <span className="mt-0.5">
                      {s.status === 'running' ? (
                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      ) : s.status === 'done' ? (
                        <Check className="h-4 w-4 text-primary" />
                      ) : s.status === 'error' ? (
                        <X className="h-4 w-4 text-destructive" />
                      ) : (
                        <Circle className="h-4 w-4 text-muted-foreground" />
                      )}
                    </span>
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <button
                        type="button"
                        className="flex items-center gap-1 text-left text-sm font-medium"
                        aria-expanded={openSteps[s.id] ?? s.status === 'running'}
                        onClick={() => setOpenSteps((o) => ({ ...o, [s.id]: !(o[s.id] ?? s.status === 'running') }))}
                      >
                        {s.title}
                        {s.notes.length > 0 && (
                          <ChevronDown className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform', (openSteps[s.id] ?? s.status === 'running') && 'rotate-180')} />
                        )}
                      </button>
                      {(openSteps[s.id] ?? s.status === 'running') &&
                        s.notes.map((n, i) => (
                          <span key={i} className="text-xs text-muted-foreground">{n}</span>
                        ))}
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {usage && (
              <p className="text-xs tabular-nums text-muted-foreground">
                Tokens: {formatTokens(usage.input_tokens)} in, {formatTokens(usage.output_tokens)} out, {usage.calls} model call(s)
              </p>
            )}
            {files.length > 0 && (
              <div className="flex flex-col gap-2">
                {files.map((f) => (
                  <div key={f.id} className="flex flex-col gap-1">
                    <FileCard file={f} />
                    {(f.audit_issues || []).length > 0 && (
                      <p className="text-[11px] text-muted-foreground">Open audit issues: {(f.audit_issues || []).join('; ')}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
            {message && <p className="text-sm">{message}</p>}
            {error && <p role="alert" className="rounded-lg border border-destructive/30 px-3 py-2 text-sm text-destructive">{error}</p>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
