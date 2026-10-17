'use client'

import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronDown, Circle, FileSpreadsheet, FileText, Loader2, PenTool, Presentation, X, ArrowRight } from 'lucide-react'

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { FileCard } from '@/components/files/FileCard'
import { TutAvatar } from '@/components/tut/TutAvatar'
import { followJob, formatTokens, JobEvent, LibraryFile, PresetId, PresetMode, StudioPreset, studioApi } from '@/lib/api/studio'
import { cn } from '@/lib/utils'

// Swatches for preview cards
const NOIR_DARK = ['#010612', '#030F1F', '#efece4']
const NOIR_LIGHT = ['#FFFFFF', '#F2F5F9', '#1E507A']

const LOOK: Record<PresetId, { icon: typeof FileText; label: string }> = {
  presentation: { icon: Presentation, label: 'Presentation' },
  report: { icon: FileText, label: 'Report' },
  infograph: { icon: PenTool, label: 'Infographic' },
  spreadsheet: { icon: FileSpreadsheet, label: 'Spreadsheet' },
}

const FALLBACK: StudioPreset[] = [
  { id: 'presentation', name: 'Presentation', description: 'Briefing deck with cover, agenda, structured content and native charts.', modes: ['dark', 'light'], outputs: ['pptx', 'pdf'], ready: true },
  { id: 'report', name: 'Report', description: 'Full report as a print PDF and an editable Word document.', modes: ['dark', 'light'], outputs: ['pdf', 'docx'], lengths: ['short', 'medium', 'long'], ready: true },
  { id: 'infograph', name: 'Infograph', description: 'One-page sketchnote with structured graphics and figures.', modes: ['light', 'dark'], outputs: ['png', 'pdf', 'svg'], ready: true },
  { id: 'spreadsheet', name: 'Spreadsheet', description: 'Formatted report workbook with automated formula calculations.', modes: ['dark', 'light'], outputs: ['xlsx'], ready: true },
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
      <div className="flex justify-between items-baseline">
        <span className="text-xs font-medium text-[#f3f1ea]">{label}</span>
      </div>
      {children}
      {hint && <span className="text-[11px] text-[#a9afb9] leading-tight">{hint}</span>}
    </div>
  )
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
  disabled
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  disabled?: boolean
}) {
  return (
    <div className="grid grid-flow-col auto-cols-fr bg-[#08090b] border border-[rgba(255,255,255,0.09)] rounded-xl p-1 gap-1" role="radiogroup">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={cn(
            'rounded-lg py-2 px-3 text-xs font-medium transition-all text-center cursor-pointer',
            value === o.value
              ? 'bg-[#000000] text-[#f3f1ea] shadow-[0_0_0_1px_rgba(255,255,255,0.38),0_0_14px_-2px_rgba(190,215,255,0.35)]'
              : 'text-[#a9afb9] hover:text-[#f3f1ea]'
          )}
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
      <DialogContent className="max-h-[94vh] max-w-6xl overflow-y-auto rounded-3xl border border-[rgba(255,255,255,0.09)] bg-[#000000] p-6 text-[#f3f1ea] shadow-[0_60px_140px_-30px_#000000]">
        {/* Header */}
        <DialogHeader className="pb-4 border-b border-[rgba(255,255,255,0.09)]">
          <div className="flex items-center gap-4">
            <div className="rounded-full shadow-[0_0_0_1px_rgba(239,236,228,0.4),0_0_24px_-4px_rgba(190,215,255,0.35)]">
              <TutAvatar size={44} />
            </div>
            <div>
              <DialogTitle className="text-xl font-semibold tracking-tight text-[#f3f1ea]">
                Studio
              </DialogTitle>
              <DialogDescription className="text-xs text-[#a9afb9]">
                TuT Agent writes from this notebook; the document engines build and check every file.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* 3-Zone Grid Layout */}
        <div className="grid gap-6 pt-2 lg:grid-cols-[1.2fr_1fr_0.95fr]">
          
          {/* Zone 1: Choose Output */}
          <div className="flex flex-col gap-4">
            <h3 className="text-sm font-semibold tracking-tight text-[#f3f1ea] flex items-center justify-between">
              <span>1. Choose output</span>
              <span className="text-xs font-mono text-[#a9afb9] font-normal">{presets.length} formats</span>
            </h3>

            <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="What to create">
              {presets.map((p) => {
                const look = LOOK[p.id] || { icon: FileText, label: p.name }
                const Icon = look.icon
                const isSelected = preset === p.id
                const sw = (isSelected ? mode : p.modes[0]) === 'dark' ? NOIR_DARK : NOIR_LIGHT

                return (
                  <button
                    key={p.id}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    disabled={running || !p.ready}
                    onClick={() => setPreset(p.id)}
                    className={cn(
                      'card-obsidian text-left p-3.5 rounded-2xl flex flex-col justify-between transition-all cursor-pointer',
                      isSelected && 'on active'
                    )}
                  >
                    <div className="h-20 rounded-xl border border-[rgba(255,255,255,0.09)] bg-[#06070a] mb-2.5 flex items-center justify-center relative overflow-hidden">
                      <div className="absolute top-2 end-2 flex gap-1">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ background: sw[0], border: '1px solid rgba(255,255,255,0.2)' }} />
                        <span className="w-2.5 h-2.5 rounded-full" style={{ background: sw[1], border: '1px solid rgba(255,255,255,0.2)' }} />
                        <span className="w-2.5 h-2.5 rounded-full" style={{ background: sw[2], border: '1px solid rgba(255,255,255,0.2)' }} />
                      </div>
                      <Icon className={cn("w-7 h-7 transition-colors", isSelected ? "text-[#efece4]" : "text-[#a9afb9]")} />
                    </div>

                    <div className="flex items-center justify-between font-semibold text-sm text-[#f3f1ea] mb-1">
                      <span>{p.name}</span>
                      <i className={cn(
                        "w-2 h-2 rounded-full transition-all",
                        isSelected
                          ? "bg-[#efece4] shadow-[0_0_12px_rgba(190,215,255,0.7)]"
                          : "bg-transparent shadow-[inset_0_0_0_1px_rgba(255,255,255,0.25)]"
                      )} />
                    </div>

                    <p className="text-xs text-[#a9afb9] leading-relaxed line-clamp-2">
                      {p.description}
                    </p>

                    {!p.ready && (
                      <span className="mt-2 text-[10px] text-destructive">
                        Needs: {(p.missing || []).join(', ') || 'engines'}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Zone 2: Shape It */}
          <div className="flex flex-col gap-4 border-t lg:border-t-0 lg:border-l border-[rgba(255,255,255,0.09)] lg:pl-6 pt-4 lg:pt-0">
            <h3 className="text-sm font-semibold tracking-tight text-[#f3f1ea]">
              2. Shape it
            </h3>

            <div className="flex flex-col gap-4">
              <Field label="Design mode" hint={template === 'default' ? 'The approved template, generated straight away.' : 'Applies your custom direction with multi-pass refinement.'}>
                <Segmented
                  value={template}
                  onChange={setTemplate}
                  disabled={running}
                  options={[
                    { value: 'default', label: 'Default template' },
                    { value: 'custom', label: 'Custom' }
                  ]}
                />
              </Field>

              {template === 'custom' && (
                <Field label="Design direction" hint="E.g. executive summary first, royal gold accent, charts on right">
                  <Textarea
                    value={design}
                    onChange={(e) => setDesign(e.target.value)}
                    disabled={running}
                    rows={2}
                    className="bg-[#08090b] border-[rgba(255,255,255,0.09)] text-xs text-[#f3f1ea] rounded-xl"
                  />
                </Field>
              )}

              {current && current.modes.length > 1 && (
                <Field label="Theme appearance">
                  <Segmented
                    value={mode}
                    onChange={setMode}
                    disabled={running}
                    options={[
                      { value: 'dark', label: 'Dark Obsidian' },
                      { value: 'light', label: 'Pearl Light' }
                    ]}
                  />
                </Field>
              )}

              {preset === 'presentation' && (
                <Field
                  label={`Total Slides: ${slideCount}`}
                  hint={
                    slideCount >= 6
                      ? `${slideCount - 3} content slides + title cover, agenda & closing`
                      : `${slideCount - 2} content slides + title cover & closing`
                  }
                >
                  <input
                    type="range"
                    min={4}
                    max={20}
                    value={slideCount}
                    disabled={running}
                    onChange={(e) => setSlideCount(Number(e.target.value))}
                    className="w-full accent-[#efece4] cursor-pointer"
                    aria-label="Number of slides"
                  />
                </Field>
              )}

              {preset === 'report' && (
                <Field label="Report Length">
                  <Segmented
                    value={length}
                    onChange={setLength}
                    disabled={running}
                    options={[
                      { value: 'short', label: 'Short' },
                      { value: 'medium', label: 'Medium' },
                      { value: 'long', label: 'Long' }
                    ]}
                  />
                </Field>
              )}

              <Field label="Audience">
                <Input
                  value={audience}
                  onChange={(e) => setAudience(e.target.value)}
                  disabled={running}
                  className="bg-[#08090b] border-[rgba(255,255,255,0.09)] text-xs text-[#f3f1ea] rounded-xl h-10"
                />
              </Field>

              <Field
                label={preset === 'spreadsheet' ? 'Figures & instructions' : 'Instructions for TuT Agent'}
                hint={preset === 'spreadsheet' ? 'Paste figures or table data. Changes and totals will be dynamic formulas.' : 'Optional focus, key sections, or metrics.'}
              >
                <Textarea
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  disabled={running}
                  rows={preset === 'spreadsheet' ? 4 : 2}
                  className="bg-[#08090b] border-[rgba(255,255,255,0.09)] text-xs text-[#f3f1ea] rounded-xl"
                />
              </Field>

              {/* Action button */}
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={generate}
                  disabled={running || !current?.ready}
                  className="go btn-pearl flex-1 h-12 rounded-xl flex items-center justify-center gap-2 text-sm font-semibold tracking-wide disabled:opacity-50 cursor-pointer"
                >
                  {running && <span className="h-4 w-4 rounded-full border-2 border-white/25 border-t-white animate-spin" />}
                  <span>{running ? 'TuT Agent drafting…' : events.length ? 'Create again' : 'Create output'}</span>
                  {!running && <ArrowRight className="w-4 h-4 ml-1" />}
                </button>

                {running && jobId && (
                  <Button
                    variant="outline"
                    className="h-12 rounded-xl border-[rgba(255,255,255,0.15)] bg-transparent hover:bg-white/5"
                    onClick={() => studioApi.cancel(jobId)}
                  >
                    Stop
                  </Button>
                )}
              </div>
            </div>
          </div>

          {/* Zone 3: Progress & Output */}
          <div className="flex flex-col gap-3 rounded-2xl border border-[rgba(255,255,255,0.09)] bg-[#07080a] p-4 min-h-[380px]" aria-live="polite">
            <h3 className="text-sm font-semibold tracking-tight text-[#f3f1ea] flex items-center justify-between">
              <span>3. Progress & files</span>
              {running && <span className="text-xs text-[#bfe0ff] flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-[#bfe0ff] animate-ping" /> Active</span>}
            </h3>

            {!events.length && !running && (
              <div className="m-auto flex max-w-xs flex-col items-center gap-3 text-center text-xs text-[#a9afb9]">
                <div className="p-3 rounded-full bg-white/5">
                  <TutAvatar size={52} />
                </div>
                <span>TuT Agent writes the draft; document engines build and check each file. Progress and outputs appear here.</span>
              </div>
            )}

            {timeline.length > 0 && (
              <ol className="flex flex-col gap-2.5 my-2">
                {timeline.map((s) => (
                  <li key={s.id} className="flex gap-2.5 text-xs">
                    <span className="mt-0.5 shrink-0">
                      {s.status === 'running' ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-[#bfe0ff]" />
                      ) : s.status === 'done' ? (
                        <Check className="h-3.5 w-3.5 text-emerald-400" />
                      ) : s.status === 'error' ? (
                        <X className="h-3.5 w-3.5 text-destructive" />
                      ) : (
                        <Circle className="h-3.5 w-3.5 text-[#a9afb9]" />
                      )}
                    </span>
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <button
                        type="button"
                        className="flex items-center gap-1 text-left font-medium text-[#f3f1ea] cursor-pointer"
                        aria-expanded={openSteps[s.id] ?? s.status === 'running'}
                        onClick={() => setOpenSteps((o) => ({ ...o, [s.id]: !(o[s.id] ?? s.status === 'running') }))}
                      >
                        {s.title}
                        {s.notes.length > 0 && (
                          <ChevronDown className={cn('h-3 w-3 text-[#a9afb9] transition-transform', (openSteps[s.id] ?? s.status === 'running') && 'rotate-180')} />
                        )}
                      </button>
                      {(openSteps[s.id] ?? s.status === 'running') &&
                        s.notes.map((n, i) => (
                          <span key={i} className="text-[11px] text-[#a9afb9]">{n}</span>
                        ))}
                    </div>
                  </li>
                ))}
              </ol>
            )}

            {usage && (
              <p className="text-[11px] font-mono text-[#a9afb9] mt-auto pt-2 border-t border-[rgba(255,255,255,0.08)]">
                Tokens: {formatTokens(usage.input_tokens)} in · {formatTokens(usage.output_tokens)} out ({usage.calls} calls)
              </p>
            )}

            {files.length > 0 && (
              <div className="flex flex-col gap-2 mt-2">
                <span className="text-xs font-semibold text-[#f3f1ea]">Generated outputs ({files.length}):</span>
                {files.map((f) => (
                  <div key={f.id} className="flex flex-col gap-1">
                    <FileCard file={f} />
                    {(f.audit_issues || []).length > 0 && (
                      <p className="text-[10px] text-[#a9afb9]">Issues: {(f.audit_issues || []).join('; ')}</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {message && <p className="text-xs text-[#f3f1ea]">{message}</p>}
            {error && <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>}
          </div>

        </div>
      </DialogContent>
    </Dialog>
  )
}
