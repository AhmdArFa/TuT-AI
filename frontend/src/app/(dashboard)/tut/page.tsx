'use client'

import { Suspense, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'next/navigation'
import { ExternalLink } from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'
import { Button } from '@/components/ui/button'
import { TutAvatar } from '@/components/tut/TutAvatar'
import { tutApi } from '@/lib/api/admin'
import { useTheme } from '@/lib/stores/theme-store'

/**
 * TuT Agent: the TuT-Agent app (agent runtime, tools, skills, knowledge,
 * memory, multi-agent groups) embedded in TuT AI. It signs in with the same
 * TuT AI account through the shared login.
 */
function TutAgent() {
  const params = useSearchParams()
  const { data: url = '', isLoading } = useQuery({ queryKey: ['tut-url'], queryFn: tutApi.url, staleTime: Infinity })
  const notebook = params.get('notebook')
  const { effectiveTheme } = useTheme()
  const iframeRef = useRef<HTMLIFrameElement>(null)

  const themeQuery = `theme=${effectiveTheme}`
  const baseSrc = url ? `${url}/` : ''
  const fullSrc = baseSrc ? (baseSrc.includes('?') ? `${baseSrc}&${themeQuery}` : `${baseSrc}?${themeQuery}`) : ''

  useEffect(() => {
    const handleMessage = (e: MessageEvent) => {
      if (e.data?.type === 'MCIT_ACCENT_CHANGE' && e.data?.accent) {
        document.documentElement.style.setProperty('--primary', e.data.accent)
        document.documentElement.style.setProperty('--gold', e.data.accent)
        document.documentElement.style.setProperty('--ring', e.data.accent)
        try {
          localStorage.setItem('mcit-accent-color', e.data.accent)
        } catch (_) {}
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [])

  useEffect(() => {
    if (iframeRef.current?.contentWindow) {
      const accent = localStorage.getItem('mcit-accent-color') || '#4B7BFF'
      iframeRef.current.contentWindow.postMessage(
        { type: 'MCIT_THEME_CHANGE', theme: effectiveTheme },
        '*'
      )
      iframeRef.current.contentWindow.postMessage(
        { type: 'MCIT_ACCENT_CHANGE', accent },
        '*'
      )
    }
  }, [effectiveTheme])

  const handleIframeLoad = () => {
    const accent = localStorage.getItem('mcit-accent-color') || '#4B7BFF'
    iframeRef.current?.contentWindow?.postMessage(
      { type: 'MCIT_THEME_CHANGE', theme: effectiveTheme },
      '*'
    )
    iframeRef.current?.contentWindow?.postMessage(
      { type: 'MCIT_ACCENT_CHANGE', accent },
      '*'
    )
  }

  return (
    <AppShell>
      <div className="relative flex h-full w-full min-h-0 flex-1 overflow-hidden bg-background">
        {isLoading ? null : url ? (
          <iframe
            ref={iframeRef}
            onLoad={handleIframeLoad}
            title="TuT Agent"
            src={fullSrc}
            className="h-full w-full border-0 bg-background"
            allow="clipboard-read; clipboard-write; microphone; camera"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-8 text-center bg-background">
            <TutAvatar size={80} />
            <h1 className="text-xl font-semibold">TuT Agent is not connected yet</h1>
            <p className="max-w-md text-sm text-muted-foreground">
              Your administrator needs to start the TuT Agent service and set its address
              (TUT_AGENT_PUBLIC_URL). Notebook chat and Studio keep working in the meantime.
            </p>
          </div>
        )}
      </div>
    </AppShell>
  )
}

export default function TutAgentPage() {
  return (
    <Suspense>
      <TutAgent />
    </Suspense>
  )
}
