import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { describeError } from '@/lib/http'
import { useSignIn } from '@/stores/useAuthStore'
import { authInput, focusRing, linkReset } from '@/design-system'
import { color, radius, size, tracking, weight } from '@/design-system'

export default function AdminSignInPage() {
  const navigate = useNavigate()
  const signIn = useSignIn()
  const [params] = useSearchParams()
  const next = params.get('next') ?? '/admin/dashboard'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showPass, setShowPass] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!email || !password) { setError('Please fill in all fields.'); return }
    setLoading(true)
    try {
      await signIn(email, password)
      // `next` comes from the URL, so it is attacker-controllable. Only a
      // same-site path is followed — an absolute URL here would turn the login
      // page into an open redirect, which is a phishing primitive.
      navigate(next.startsWith('/') && !next.startsWith('//') ? next : '/admin/dashboard', {
        replace: true,
      })
    } catch (err) {
      // The API answers with one message for an unknown email and a wrong
      // password alike; anything more specific enumerates accounts.
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas, display: 'flex', flexDirection: 'column' }}>
      {/* Top bar */}
      <div style={{ borderBottom: `1px solid ${color.border.base}`, background: color.surface.base, padding: '0 24px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Link
          to="/"
          style={{ ...linkReset, display: 'flex', alignItems: 'center', gap: 8, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          <div style={{ width: 32, height: 32, background: color.brand.base, borderRadius: radius.xl, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ color: color.surface.base, fontSize: size.base, fontWeight: weight.bold }}>PL</span>
          </div>
          <span style={{ fontSize: size.lg, fontWeight: weight.semibold, color: color.text.primary, letterSpacing: tracking.tight }}>Plenilo.com</span>
        </Link>
        <Link to="/" style={{ ...linkReset, fontSize: size.sm, color: color.text.secondary, background: 'none', border: 'none', cursor: 'pointer' }}>
          ← Back to site
        </Link>
      </div>

      {/* Centered card */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
        <div style={{ width: '100%', maxWidth: 400 }}>
          {/* Header */}
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <div style={{ width: 52, height: 52, background: color.brand.base, borderRadius: radius['4xl'], display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color.surface.base} strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
            </div>
            <h1 style={{ fontSize: size['4xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 6px', letterSpacing: tracking.tight }}>Admin Sign In</h1>
            <p style={{ fontSize: size.base, color: color.text.secondary, margin: 0 }}>Operations dashboard for Plenilo.com</p>
          </div>

          {/* Form card */}
          <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: 28 }}>
            {error && (
              <div style={{ background: color.danger.tint, border: `1px solid ${color.danger.border}`, borderRadius: radius.xl, padding: '12px 14px', marginBottom: 20, display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={color.danger.base} strokeWidth="2" style={{ flexShrink: 0, marginTop: 1 }}>
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                <span style={{ fontSize: size.sm, color: color.danger.text }}>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Email */}
              <div>
                <label style={{ display: 'block', fontSize: size.sm, fontWeight: weight.semibold, color: color.text.strong, marginBottom: 6 }}>Email address</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="admin@plenilo.com"
                  autoComplete="email"
                  style={authInput(Boolean(error))}
                  onFocus={e => { e.currentTarget.style.borderColor = color.brand.base; e.currentTarget.style.boxShadow = focusRing(color.brand.alpha18) }}
                  onBlur={e => { e.currentTarget.style.borderColor = error ? color.danger.border : color.border.base; e.currentTarget.style.boxShadow = 'none' }}
                />
              </div>

              {/* Password */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <label style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.strong }}>Password</label>
                  <button type="button" style={{ fontSize: size.xs, color: color.brand.base, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                    Forgot password?
                  </button>
                </div>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPass ? 'text' : 'password'}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    style={authInput(Boolean(error), { padding: '10px 40px 10px 14px' })}
                    onFocus={e => { e.currentTarget.style.borderColor = color.brand.base; e.currentTarget.style.boxShadow = focusRing(color.brand.alpha18) }}
                    onBlur={e => { e.currentTarget.style.borderColor = error ? color.danger.border : color.border.base; e.currentTarget.style.boxShadow = 'none' }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: color.text.muted, padding: 0 }}
                  >
                    {showPass ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                        <line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                      </svg>
                    )}
                  </button>
                </div>
              </div>

              {/* Remember me */}
              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                <div
                  onClick={() => setRemember(!remember)}
                  style={{
                    width: 18, height: 18, borderRadius: radius.smd,
                    border: `2px solid ${remember ? color.brand.base : color.text.disabled}`,
                    background: remember ? color.brand.base : color.surface.base,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0, transition: 'all 0.15s', cursor: 'pointer',
                  }}
                >
                  {remember && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={color.surface.base} strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>}
                </div>
                <span style={{ fontSize: size.sm, color: color.text.strong }}>Remember me for 30 days</span>
              </label>

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                style={{
                  width: '100%', padding: '12px', borderRadius: radius['2xl'],
                  background: loading ? color.brand.light : color.brand.base,
                  border: 'none', color: color.surface.base, fontSize: size.md, fontWeight: weight.semibold,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                  transition: 'background 0.15s', marginTop: 4,
                }}
              >
                {loading ? (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ animation: 'spin 0.8s linear infinite' }}>
                      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                    </svg>
                    Signing in...
                  </>
                ) : 'Sign In to Dashboard'}
              </button>
            </form>
          </div>

          <p style={{ textAlign: 'center', fontSize: size.xs, color: color.text.muted, marginTop: 20 }}>
            Staff access only. Contact an administrator if you need an account.
          </p>
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
