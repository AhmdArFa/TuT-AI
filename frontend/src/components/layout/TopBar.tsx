'use client'

import { useState, useEffect } from 'react'

export const ACCENT_PRESETS = [
  { name: 'Lapis Blue', gold: '#4B7BFF', gold2: '#A9C1FF', deep: '#1F3FB8', rgb: '75,123,255', on: '#ffffff' },
  { name: 'Emerald', gold: '#2FD08C', gold2: '#A4F2CF', deep: '#0B8A5C', rgb: '47,208,140', on: '#03140c' },
  { name: 'Amethyst', gold: '#A47CF5', gold2: '#DCCBFF', deep: '#5E34C4', rgb: '164,124,245', on: '#ffffff' },
  { name: 'Crimson', gold: '#F0506E', gold2: '#FFADBD', deep: '#A8123A', rgb: '240,80,110', on: '#ffffff' },
  { name: 'Aqua', gold: '#22C7E8', gold2: '#A6EEFB', deep: '#0A7C98', rgb: '34,199,232', on: '#02161b' },
  { name: 'Gold', gold: '#F5C242', gold2: '#FFEDB9', deep: '#B97D0C', rgb: '245,194,66', on: '#1a1204' }
]

export function applyAccentTheme(index: number) {
  const a = ACCENT_PRESETS[index] || ACCENT_PRESETS[0]
  const r = document.documentElement.style
  r.setProperty('--gold', a.gold)
  r.setProperty('--gold2', a.gold2)
  r.setProperty('--d', a.deep)
  r.setProperty('--accrgb', a.rgb)
  r.setProperty('--on', a.on)
  r.setProperty('--gg', a.gold)
  r.setProperty('--primary', a.gold)
  r.setProperty('--ring', a.gold)

  try {
    localStorage.setItem('tut-acc', String(index))
    localStorage.setItem('mcit-accent-color', a.gold)
  } catch (_) {}

  // Sync with Tut Agent iframe
  try {
    document.querySelectorAll('iframe').forEach((frame) => {
      frame.contentWindow?.postMessage({ type: 'MCIT_ACCENT_CHANGE', accent: a.gold }, '*')
    })
  } catch (_) {}

  // Dispatch event for other React components
  window.dispatchEvent(new CustomEvent('mcit-accent-changed', { detail: { index, accent: a.gold } }))
}

export function TopBar() {
  const [popOpen, setPopOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  useEffect(() => {
    let sv = 0
    try {
      sv = parseInt(localStorage.getItem('tut-acc') || '0', 10)
      if (isNaN(sv) || sv < 0 || sv >= ACCENT_PRESETS.length) sv = 0
    } catch (_) {}
    setActiveIndex(sv)
    applyAccentTheme(sv)

    const onAccent = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail && typeof detail.index === 'number') {
        setActiveIndex(detail.index)
      }
    }
    window.addEventListener('mcit-accent-changed', onAccent)
    return () => window.removeEventListener('mcit-accent-changed', onAccent)
  }, [])

  return (
    <div className="tut-top">
      <div className="sp" />
      <div className="pick">
        <button
          type="button"
          className="ib"
          id="pk"
          title="Accent color"
          onClick={(e) => {
            e.stopPropagation()
            setPopOpen(!popOpen)
          }}
        >
          <svg className="i" viewBox="0 0 24 24">
            <path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.6-.8 1.6-1.6 0-.5-.3-.9-.5-1.3-.3-.4-.5-.8-.5-1.3 0-.9.7-1.6 1.6-1.6H16a5 5 0 0 0 5-5c0-3.9-4-7.2-9-7.2z" />
            <circle cx="7.5" cy="11" r="1" />
            <circle cx="10" cy="7" r="1" />
            <circle cx="15" cy="7.5" r="1" />
          </svg>
        </button>

        {popOpen && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setPopOpen(false)}
            />
            <div className="pop on" id="pop">
              {ACCENT_PRESETS.map((a, i) => (
                <button
                  key={a.name}
                  type="button"
                  className={`sw ${activeIndex === i ? 'on' : ''}`}
                  title={a.name}
                  style={{
                    background: `linear-gradient(135deg, ${a.gold2}, ${a.gold} 50%, ${a.deep})`,
                  }}
                  onClick={() => {
                    setActiveIndex(i)
                    applyAccentTheme(i)
                    setPopOpen(false)
                  }}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
