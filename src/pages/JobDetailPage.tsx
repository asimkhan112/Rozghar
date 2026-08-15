import { useState } from 'react'
import { Link, useParams } from 'react-router'
import Navbar from '../components/Navbar'
import { getJobBySlug, getRelatedJobs } from '@/data/queries'
import { badgeLabel, badgeStyle, logoPalette, color, linkReset, radius, shadow, size, tracking, weight } from '@/design-system'
import { useIsSaved, useToggleSave } from '@/stores/useSavedJobsStore'
import NotFoundPage from '@/routes/NotFoundPage'

export default function JobDetailPage() {
  const { slug } = useParams()
  const job = getJobBySlug(slug)
  const [applied, setApplied] = useState(false)
  const [showShareMenu, setShowShareMenu] = useState(false)
  const isSaved = useIsSaved(job?.id ?? '')
  const toggleSave = useToggleSave()

  // An unknown slug renders the 404 surface rather than throwing. Phase 8
  // moves this into a route loader so the status code is correct for crawlers.
  if (!job) return <NotFoundPage />

  const logoColor = logoPalette[job.logoPalette]
  const related = getRelatedJobs(job)

  const handleApply = () => {
    setApplied(true)
    window.open(job.applyUrl, '_blank', 'noopener')
  }

  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas }}>
      <Navbar />

      {/* Breadcrumb */}
      <div style={{ background: color.surface.base, borderBottom: `1px solid ${color.border.base}`, padding: '12px 24px' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 8, fontSize: size.sm, color: color.text.muted }}>
          <Link to="/" style={{ ...linkReset, background: 'none', border: 'none', cursor: 'pointer', color: color.text.muted, padding: 0, fontSize: size.sm }}>Home</Link>
          <span>/</span>
          <Link to="/jobs" style={{ ...linkReset, background: 'none', border: 'none', cursor: 'pointer', color: color.text.muted, padding: 0, fontSize: size.sm }}>Jobs</Link>
          <span>/</span>
          <span style={{ color: color.text.primary, fontWeight: weight.medium }}>{job.title}</span>
        </div>
      </div>

      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '32px 24px 120px', display: 'grid', gridTemplateColumns: '1fr 340px', gap: 32, alignItems: 'start' }} className="detail-grid">

        {/* Main content */}
        <div>
          {/* Job header */}
          <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: '28px', marginBottom: 20 }}>
            <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', marginBottom: 20 }}>
              <div style={{
                width: 64, height: 64, borderRadius: radius['4xl'], flexShrink: 0,
                background: logoColor.bg, color: logoColor.text,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: size['2xl'], fontWeight: weight.extrabold, letterSpacing: 0.5,
              }}>
                {job.logo}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                  <div>
                    <h1 style={{ margin: '0 0 4px', fontSize: 'clamp(18px, 3vw, 24px)', fontWeight: weight.bold, color: color.text.primary, lineHeight: 1.2, letterSpacing: tracking.tight }}>
                      {job.title}
                    </h1>
                    <div style={{ fontSize: size.md, color: color.brand.base, fontWeight: weight.semibold }}>{job.company}</div>
                  </div>
                  <span style={{ ...badgeStyle(job.badge, 'md'), flexShrink: 0 }}>
                    {badgeLabel.detail[job.badge]}
                  </span>
                </div>
              </div>
            </div>

            {/* Meta grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, padding: '16px 0', borderTop: `1px solid ${color.surface.muted}`, borderBottom: `1px solid ${color.surface.muted}`, marginBottom: 20 }}>
              {[
                { icon: '📍', label: 'Location', value: job.location },
                { icon: '💼', label: 'Work Type', value: job.workType },
                { icon: '⏱️', label: 'Employment', value: job.employmentType },
                { icon: '💰', label: 'Salary', value: job.salary },
                { icon: '📈', label: 'Experience', value: job.experience },
                { icon: '🏷️', label: 'Category', value: job.category },
              ].map(m => (
                <div key={m.label}>
                  <div style={{ fontSize: size['2xs'], color: color.text.muted, fontWeight: weight.semibold, textTransform: 'uppercase', letterSpacing: tracking.wide, marginBottom: 3 }}>{m.label}</div>
                  <div style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary, display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span>{m.icon}</span>{m.value}
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop apply actions */}
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={handleApply}
                style={{
                  flex: 1, padding: '14px', background: applied ? color.success.base : color.brand.base,
                  border: 'none', borderRadius: radius['2xl'], color: color.surface.base, fontSize: size.md,
                  fontWeight: weight.semibold, cursor: 'pointer', transition: 'all 0.2s',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                }}
              >
                {applied ? (
                  <><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12" /></svg> Applied! Opening site...</>
                ) : (
                  <>Apply Now <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg></>
                )}
              </button>
              <button
                onClick={() => toggleSave(job.id)}
                style={{
                  padding: '14px 18px', border: `1px solid ${isSaved ? color.brand.base : color.border.base}`,
                  background: isSaved ? color.brand.tint : color.surface.base, borderRadius: radius['2xl'],
                  color: isSaved ? color.brand.base : color.text.secondary, cursor: 'pointer', transition: 'all 0.2s',
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill={isSaved ? color.brand.base : 'none'} stroke="currentColor" strokeWidth="2">
                  <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                </svg>
              </button>
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => setShowShareMenu(!showShareMenu)}
                  style={{ padding: '14px 18px', border: `1px solid ${color.border.base}`, background: color.surface.base, borderRadius: radius['2xl'], color: color.text.secondary, cursor: 'pointer' }}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                  </svg>
                </button>
                {showShareMenu && (
                  <div style={{ position: 'absolute', right: 0, top: '100%', marginTop: 4, background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['2xl'], padding: 8, boxShadow: shadow.menu, zIndex: 10, minWidth: 160 }}>
                    {[
                      { label: '📱 WhatsApp', color: color.external.whatsapp },
                      { label: '💼 LinkedIn', color: color.external.linkedin },
                      { label: '📋 Copy Link', color: color.text.secondary },
                    ].map(s => (
                      <button key={s.label} onClick={() => setShowShareMenu(false)} style={{ display: 'block', width: '100%', padding: '8px 12px', border: 'none', background: 'none', cursor: 'pointer', fontSize: size.sm, fontWeight: weight.medium, color: s.color, textAlign: 'left', borderRadius: radius.md }}>
                        {s.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <p style={{ margin: '12px 0 0', fontSize: size.xs, color: color.text.muted, textAlign: 'center' }}>
              You will be redirected to the company's official website to apply
            </p>
          </div>

          {/* Description */}
          <ContentSection title="About the Role">
            <p style={{ fontSize: size.md, color: color.text.strong, lineHeight: 1.7, margin: 0 }}>{job.description}</p>
          </ContentSection>

          <ContentSection title="Responsibilities">
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {job.responsibilities.map((r, i) => (
                <li key={i} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', fontSize: size.md, color: color.text.strong, lineHeight: 1.5 }}>
                  <span style={{ width: 6, height: 6, borderRadius: radius.full, background: color.brand.base, flexShrink: 0, marginTop: 8 }} />
                  {r}
                </li>
              ))}
            </ul>
          </ContentSection>

          <ContentSection title="Requirements">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {job.requirements.map((r, i) => (
                <span key={i} style={{ fontSize: size.sm, padding: '6px 12px', borderRadius: radius.xl, background: color.surface.canvas, border: `1px solid ${color.border.base}`, color: color.text.strong, fontWeight: weight.medium }}>
                  {r}
                </span>
              ))}
            </div>
          </ContentSection>

          <ContentSection title="Benefits & Perks">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
              {job.benefits.map((b, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: color.brand.tint, borderRadius: radius.xl, border: `1px solid ${color.brand.alpha20}` }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color.brand.base} strokeWidth="2.5"><polyline points="20 6 9 17 4 12" /></svg>
                  <span style={{ fontSize: size.sm, color: color.text.strong, fontWeight: weight.medium }}>{b}</span>
                </div>
              ))}
            </div>
          </ContentSection>
        </div>

        {/* Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Quick info */}
          <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], padding: 20 }}>
            <h3 style={{ margin: '0 0 16px', fontSize: size.base, fontWeight: weight.bold, color: color.text.primary }}>Quick Info</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { label: 'Posted', value: job.postedDate },
                { label: 'Source', value: 'Company website' },
                { label: 'Apply via', value: 'Direct company link' },
              ].map(i => (
                <div key={i.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: size.sm }}>
                  <span style={{ color: color.text.muted }}>{i.label}</span>
                  <span style={{ color: color.text.primary, fontWeight: weight.medium }}>{i.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Related jobs */}
          {related.length > 0 && (
            <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['3xl'], overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: `1px solid ${color.border.base}` }}>
                <h3 style={{ margin: 0, fontSize: size.base, fontWeight: weight.bold, color: color.text.primary }}>Similar Jobs</h3>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                {related.map((rj, i) => (
                  <Link
                    key={rj.id}
                    to={`/jobs/${rj.slug}`}
                    style={{
                      ...linkReset,
                      display: 'flex', alignItems: 'flex-start', gap: 12, padding: '14px 20px',
                      borderBottom: i < related.length - 1 ? `1px solid ${color.surface.subtle}` : 'none',
                      background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = color.surface.canvas)}
                    onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                  >
                    <div style={{ width: 32, height: 32, borderRadius: radius.xl, background: logoPalette[rj.logoPalette].bg, color: logoPalette[rj.logoPalette].text, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: size['3xs'], fontWeight: weight.bold, flexShrink: 0 }}>
                      {rj.logo}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary, marginBottom: 2 }}>{rj.title}</div>
                      <div style={{ fontSize: size.xs, color: color.text.secondary }}>{rj.company}</div>
                      <div style={{ fontSize: size['2xs'], color: color.brand.base, marginTop: 3, fontWeight: weight.medium }}>{rj.salary}</div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Mobile sticky apply bar */}
      <div style={{
        position: 'fixed', bottom: 0, left: 0, right: 0,
        background: color.surface.base, borderTop: `1px solid ${color.border.base}`,
        padding: '12px 20px', zIndex: 50,
        display: 'flex', gap: 10, alignItems: 'center',
      }} className="mobile-apply-bar">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: size.sm, fontWeight: weight.semibold, color: color.text.primary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{job.title}</div>
          <div style={{ fontSize: size.xs, color: color.text.secondary }}>{job.company}</div>
        </div>
        <button
          onClick={handleApply}
          style={{
            padding: '11px 24px', background: applied ? color.success.base : color.brand.base,
            border: 'none', borderRadius: radius['2xl'], color: color.surface.base, fontSize: size.base,
            fontWeight: weight.semibold, cursor: 'pointer', flexShrink: 0,
          }}
        >
          {applied ? '✓ Applied' : 'Apply Now →'}
        </button>
      </div>

      <style>{`
        @media (min-width: 900px) { .mobile-apply-bar { display: none !important; } }
        @media (max-width: 900px) { .detail-grid { grid-template-columns: 1fr !important; } }
      `}</style>
    </div>
  )
}

function ContentSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: '24px 28px', marginBottom: 16 }}>
      <h2 style={{ margin: '0 0 16px', fontSize: size.lg, fontWeight: weight.bold, color: color.text.primary }}>{title}</h2>
      {children}
    </div>
  )
}
