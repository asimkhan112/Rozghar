import { useState } from 'react'
import Navbar from '@/components/Navbar'
import { color, formFieldLabel, formInput, formSelect, formTextarea, radius, size, tracking, weight } from '@/design-system'

const SUBJECTS = ['Report a listing', 'Employer enquiry', 'Feedback', 'Something else']

/**
 * Contact form.
 *
 * Field, label and button styling is lifted from the admin form primitives so
 * it matches the rest of the product. Submission is local until the contact
 * endpoint lands in Phase 8 — the handler is the only thing that changes then.
 */
export default function ContactPage() {
  const [form, setForm] = useState({ name: '', email: '', subject: SUBJECTS[0], message: '' })
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  const update = (key: keyof typeof form, value: string) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim() || !form.email.trim() || !form.message.trim()) {
      setError('Please fill in your name, email and message.')
      return
    }
    setError('')
    setSent(true)
  }


  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas }}>
      <Navbar />
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '40px 24px 80px' }}>
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ fontSize: size['5xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 6px', letterSpacing: tracking.tight }}>Contact</h1>
          <p style={{ fontSize: size.base, color: color.text.secondary, margin: 0 }}>
            Report a broken listing, ask about posting a job, or just tell us what is missing.
          </p>
        </div>

        {sent ? (
          <div style={{ textAlign: 'center', padding: '64px 24px', background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'] }}>
            <div style={{ fontSize: size['8xl'], marginBottom: 16 }}>✅</div>
            <h2 style={{ fontSize: size['3xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 8px' }}>Message received</h2>
            <p style={{ fontSize: size.md, color: color.text.secondary, margin: '0 0 24px', maxWidth: 380, marginInline: 'auto' }}>
              Thanks, {form.name.split(' ')[0]}. We reply to most messages within two working days.
            </p>
            <button
              onClick={() => { setSent(false); setForm({ name: '', email: '', subject: SUBJECTS[0], message: '' }) }}
              style={{ padding: '10px 24px', background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius.xl, color: color.text.primary, fontSize: size.base, fontWeight: weight.medium, cursor: 'pointer' }}
            >
              Send another
            </button>
          </div>
        ) : (
          <form
            onSubmit={handleSubmit}
            style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: '28px 32px', display: 'flex', flexDirection: 'column', gap: 18 }}
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 18 }}>
              <div>
                <label htmlFor="contact-name" style={formFieldLabel}>Your name</label>
                <input id="contact-name" value={form.name} onChange={e => update('name', e.target.value)} style={formInput} placeholder="Ayesha Khan" />
              </div>
              <div>
                <label htmlFor="contact-email" style={formFieldLabel}>Email</label>
                <input id="contact-email" type="email" value={form.email} onChange={e => update('email', e.target.value)} style={formInput} placeholder="you@example.com" />
              </div>
            </div>

            <div>
              <label htmlFor="contact-subject" style={formFieldLabel}>Subject</label>
              <select id="contact-subject" value={form.subject} onChange={e => update('subject', e.target.value)} style={formSelect}>
                {SUBJECTS.map(s => <option key={s}>{s}</option>)}
              </select>
            </div>

            <div>
              <label htmlFor="contact-message" style={formFieldLabel}>Message</label>
              <textarea
                id="contact-message"
                value={form.message}
                onChange={e => update('message', e.target.value)}
                rows={6}
                style={formTextarea}
                placeholder="Tell us what happened, and include the job link if you have it."
              />
            </div>

            {error && (
              <div style={{ fontSize: size.sm, color: color.danger.text, background: color.danger.tint, border: `1px solid ${color.danger.border}`, borderRadius: radius.xl, padding: '10px 14px' }}>
                {error}
              </div>
            )}

            <div>
              <button
                type="submit"
                style={{ padding: '11px 28px', background: color.brand.base, border: 'none', borderRadius: radius.xl, color: color.surface.base, fontSize: size.base, fontWeight: weight.medium, cursor: 'pointer' }}
                onMouseEnter={e => (e.currentTarget.style.background = color.brand.hover)}
                onMouseLeave={e => (e.currentTarget.style.background = color.brand.base)}
              >
                Send message
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
