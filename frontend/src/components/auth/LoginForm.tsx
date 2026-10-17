'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { AlertCircle, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '@/lib/hooks/use-auth'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { TuTBrandAvatar } from '@/components/common/TuTBrandIcon'
import { cn } from '@/lib/utils'

export function LoginForm() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [keepSignedIn, setKeepSignedIn] = useState(true)
  const [lang, setLang] = useState<'en' | 'ar'>('en')
  const { login, isLoading, error, isAuthenticated } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next')

  useEffect(() => {
    // Already signed in: finish a pending Tut Agent sign-in or go home
    if (isAuthenticated && !isLoading) {
      if (next?.startsWith('/api/oidc/')) window.location.href = next
      else router.replace('/notebooks')
    }
  }, [isAuthenticated, isLoading, next, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (username.trim() && password) await login(username, password, next)
  }

  if (isAuthenticated && !error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#000000]">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.15fr_0.85fr] bg-[#000000] text-[#f3f5f7]" dir={lang === 'ar' ? 'rtl' : 'ltr'}>
      {/* Left split: Hero with etched line background and MCIT badge */}
      <section className="hidden lg:flex relative overflow-hidden flex-col justify-between border-r border-[rgba(255,255,255,0.08)] bg-[#000000] p-12">
        <div className="relative z-10 inline-block bg-white px-5 py-3 rounded-2xl shadow-[0_0_0_1px_rgba(239,236,228,0.4),0_0_0_7px_rgba(239,236,228,0.05),0_24px_50px_-18px_#000000] self-start">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/mcit-logo.png" alt="Ministry of Communications and Information Technology" className="h-10 w-auto object-contain" />
        </div>
        
        <div className="relative z-10 flex flex-col gap-6 max-w-md">
          <TuTBrandAvatar size={88} />
          <h1 className="text-4xl font-semibold tracking-tight text-[#f3f5f7]">TuT AI</h1>
          <p className="text-base leading-relaxed text-[#8a919b]">
            {lang === 'ar'
              ? 'دفاتر الملاحظات والاستوديو ووكيل TuT في مساحة عمل واحدة. ابحث في مصادرك، وتحاور معها، وأنتج التقارير والعروض التقديمية والرسوم البيانية وجداول البيانات.'
              : 'Notebooks, Studio and TuT Agent in one workspace. Research your sources, chat with them, and produce reports, decks, infographics and spreadsheets.'}
          </p>
        </div>

        <p className="relative z-10 text-xs text-[#8a919b]">
          {lang === 'ar'
            ? 'وزارة الاتصالات وتكنولوجيا المعلومات'
            : 'Ministry of Communications and Information Technology'}
        </p>
      </section>

      {/* Right split: Form card with pearl-edge action */}
      <section className="flex flex-col justify-between p-6 sm:p-10 relative z-10 bg-[#050607]">
        <div className="flex justify-end">
          <div className="flex border border-[rgba(255,255,255,0.08)] rounded-full p-1 bg-[#08090b]" role="group" aria-label="Language">
            <button
              type="button"
              onClick={() => setLang('en')}
              className={cn(
                "px-3.5 py-1 rounded-full text-xs font-medium transition-all cursor-pointer",
                lang === 'en'
                  ? "bg-[#000000] text-[#f3f1ea] shadow-[0_0_0_1px_rgba(255,255,255,0.38),0_0_14px_-2px_rgba(190,215,255,0.35)]"
                  : "text-[#8a919b] hover:text-[#f3f5f7]"
              )}
            >
              EN
            </button>
            <button
              type="button"
              onClick={() => setLang('ar')}
              className={cn(
                "px-3.5 py-1 rounded-full text-xs font-medium transition-all cursor-pointer",
                lang === 'ar'
                  ? "bg-[#000000] text-[#f3f1ea] shadow-[0_0_0_1px_rgba(255,255,255,0.38),0_0_14px_-2px_rgba(190,215,255,0.35)]"
                  : "text-[#8a919b] hover:text-[#f3f5f7]"
              )}
            >
              عربي
            </button>
          </div>
        </div>

        <div className="flex items-center justify-center my-auto py-8">
          <form onSubmit={handleSubmit} className="w-full max-w-sm flex flex-col" aria-label="Sign in">
            <div className="lg:hidden mb-4"><TuTBrandAvatar size={56} /></div>
            <h2 className="text-3xl font-semibold tracking-tight text-[#f3f5f7] mb-2">
              {lang === 'ar' ? 'تسجيل الدخول' : 'Sign in'}
            </h2>
            <p className="text-sm text-[#8a919b] mb-8">
              {lang === 'ar'
                ? 'استخدم الحساب الذي أنشأه لك المسؤول.'
                : (next?.startsWith('/api/oidc/')
                  ? 'Sign in to continue to TuT Agent.'
                  : 'Use the account your administrator created for you.')}
            </p>

            {/* Floating label inputs */}
            <div className="relative mb-4">
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                placeholder=" "
                required
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isLoading}
                className="peer w-full h-14 pt-5 pb-1.5 px-4 bg-[#0d1014] border border-[rgba(255,255,255,0.08)] rounded-xl text-[#f3f5f7] text-sm outline-none transition-all hover:border-[rgba(255,255,255,0.16)] focus:border-[#efece4] focus:ring-4 focus:ring-[rgba(239,236,228,0.12)]"
              />
              <label
                htmlFor="username"
                className="absolute top-4 start-4 text-xs text-[#8a919b] pointer-events-none transition-all peer-placeholder-shown:top-4 peer-placeholder-shown:text-sm peer-placeholder-shown:text-[#8a919b] peer-focus:top-1.5 peer-focus:text-[11px] peer-focus:text-[#efece4] peer-[:not(:placeholder-shown)]:top-1.5 peer-[:not(:placeholder-shown)]:text-[11px]"
              >
                {lang === 'ar' ? 'اسم المستخدم' : 'Username'}
              </label>
            </div>

            <div className="relative mb-4">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder=" "
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
                className="peer w-full h-14 pt-5 pb-1.5 ps-4 pe-12 bg-[#0d1014] border border-[rgba(255,255,255,0.08)] rounded-xl text-[#f3f5f7] text-sm outline-none transition-all hover:border-[rgba(255,255,255,0.16)] focus:border-[#efece4] focus:ring-4 focus:ring-[rgba(239,236,228,0.12)]"
              />
              <label
                htmlFor="password"
                className="absolute top-4 start-4 text-xs text-[#8a919b] pointer-events-none transition-all peer-placeholder-shown:top-4 peer-placeholder-shown:text-sm peer-placeholder-shown:text-[#8a919b] peer-focus:top-1.5 peer-focus:text-[11px] peer-focus:text-[#efece4] peer-[:not(:placeholder-shown)]:top-1.5 peer-[:not(:placeholder-shown)]:text-[11px]"
              >
                {lang === 'ar' ? 'كلمة المرور' : 'Password'}
              </label>
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute top-0 end-0 h-14 w-12 flex items-center justify-center text-[#8a919b] hover:text-[#f3f5f7] transition-colors cursor-pointer"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>

            <div className="flex items-center gap-2 mb-6 text-xs text-[#8a919b]">
              <input
                type="checkbox"
                id="keep"
                checked={keepSignedIn}
                onChange={(e) => setKeepSignedIn(e.target.checked)}
                className="h-4 w-4 rounded border-[rgba(255,255,255,0.22)] bg-[#0d1014] checked:bg-[#08090b] checked:border-[#efece4] transition-all cursor-pointer"
              />
              <label htmlFor="keep" className="cursor-pointer select-none">
                {lang === 'ar' ? 'ابقني مسجلاً على هذا الجهاز' : 'Keep me signed in on this device'}
              </label>
            </div>

            {error && (
              <div role="alert" className="mb-4 flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Pearl-edge submit button */}
            <button
              type="submit"
              disabled={isLoading || !username.trim() || !password}
              className="go btn-pearl w-full h-[52px] rounded-xl flex items-center justify-center gap-2 text-sm font-semibold tracking-wide disabled:opacity-50 disabled:pointer-events-none cursor-pointer"
            >
              {isLoading && <span className="h-4 w-4 rounded-full border-2 border-white/25 border-t-white animate-spin" />}
              <span>{isLoading ? (lang === 'ar' ? 'جارٍ تسجيل الدخول…' : 'Signing in…') : (lang === 'ar' ? 'تسجيل الدخول' : 'Sign in')}</span>
              {!isLoading && (
                <svg className={cn("w-4 h-4 transition-transform", lang === 'ar' && "scale-x-[-1]")} fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 6l6 6-6 6" />
                </svg>
              )}
            </button>

            <div className="flex gap-2.5 mt-7 pt-5 border-t border-[rgba(255,255,255,0.08)] text-xs text-[#8a919b]">
              <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <rect x="4" y="11" width="16" height="10" rx="2" />
                <path d="M8 11V7a4 4 0 018 0v4" />
              </svg>
              <span>
                {lang === 'ar'
                  ? 'يتم إنشاء الحسابات بواسطة مسؤول النظام. تواصل معه إذا كنت بحاجة إلى وصول أو كلمة مرور جديدة.'
                  : 'Accounts are created by your administrator. Contact them if you need access or a new password.'}
              </span>
            </div>
          </form>
        </div>

        <div />
      </section>
    </div>
  )
}
