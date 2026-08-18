import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { Job } from '@/types/job'
import {
  badgeLabel, badgeStyle, color, linkReset, logoPalette, neutralChip,
  radius, shadow, size, weight, workTypeChip,
} from '@/design-system'
import { useIsSaved, useToggleSave } from '@/stores/useSavedJobsStore'
import { trackJobSaved } from '@/lib/analytics'

interface JobCardProps {
  job: Job
  compact?: boolean
}

export default function JobCard({ job, compact }: JobCardProps) {
  const [saving, setSaving] = useState(false)
  const isSaved = useIsSaved(job.id)
  const toggleSave = useToggleSave()
  const navigate = useNavigate()
  const logoColor = logoPalette[job.logoPalette]
  const href = `/jobs/${job.slug}`

  const handleSave = (e: React.MouseEvent) => {
    e.stopPropagation()
    setSaving(true)
    // The save is the event; the un-save is not. A negative counter would let
    // `jobs.save_count` drift below the number of saves that happened.
    if (!isSaved) trackJobSaved(job.id)
    toggleSave(job.id)
    setTimeout(() => setSaving(false), 600)
  }

  // The whole card stays clickable, but clicks that originated on the title
  // anchor are left to the router — handling both would push two history
  // entries for one click.
  const handleCardClick = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('a')) return
    navigate(href)
  }

  return (
    <article
      onClick={handleCardClick}
      style={{
        background: color.surface.base,
        border: `1px solid ${color.border.base}`,
        borderRadius: radius['3xl'],
        padding: compact ? '16px' : '20px',
        cursor: 'pointer',
        transition: 'box-shadow 0.15s, border-color 0.15s, transform 0.1s',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        position: 'relative',
      }}
      onMouseEnter={e => {
        ;(e.currentTarget as HTMLElement).style.boxShadow = shadow.card
        ;(e.currentTarget as HTMLElement).style.borderColor = color.brand.alpha40
        ;(e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={e => {
        ;(e.currentTarget as HTMLElement).style.boxShadow = 'none'
        ;(e.currentTarget as HTMLElement).style.borderColor = color.border.base
        ;(e.currentTarget as HTMLElement).style.transform = 'translateY(0)'
      }}
    >
      {/* Top row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{
          width: 44, height: 44, borderRadius: radius['2xl'],
          background: logoColor.bg, color: logoColor.text,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: size.xs, fontWeight: weight.bold, flexShrink: 0, letterSpacing: 0.5,
        }}>
          {job.logo}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: compact ? size.base : size.md, fontWeight: weight.semibold, color: color.text.primary, lineHeight: 1.3, marginBottom: 2 }}>
            <Link to={href} style={linkReset}>{job.title}</Link>
          </h3>
          <p style={{ margin: 0, fontSize: size.sm, color: color.text.secondary, fontWeight: weight.regular }}>{job.company}</p>
        </div>
        <button
          onClick={handleSave}
          title={isSaved ? 'Unsave' : 'Save job'}
          style={{
            background: isSaved ? color.brand.tint : 'none',
            border: 'none', cursor: 'pointer', padding: 6, borderRadius: radius.md,
            color: isSaved ? color.brand.base : color.text.disabled,
            transform: saving ? 'scale(1.3)' : 'scale(1)',
            transition: 'transform 0.2s, color 0.2s',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill={isSaved ? color.brand.base : 'none'} stroke="currentColor" strokeWidth="2">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      </div>

      {/* Tags row */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <span style={workTypeChip(job.workType)}>
          {job.workType}
        </span>
        <span style={neutralChip}>
          {job.employmentType}
        </span>
        <span style={{ ...badgeStyle(job.badge, 'sm'), marginLeft: 'auto' }}>
          {badgeLabel.card[job.badge]}
        </span>
      </div>

      {/* Details */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: size.sm, color: color.text.secondary }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" />
          </svg>
          {job.location}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: size.sm, color: color.text.strong, fontWeight: weight.medium }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="1" x2="12" y2="23" /><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
          </svg>
          {job.salary}
        </div>
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 4, borderTop: `1px solid ${color.border.faint}` }}>
        <span style={{ fontSize: size.xs, color: color.text.muted }}>{job.postedDate}</span>
        <span style={{ fontSize: size.xs, color: color.text.secondary, background: color.surface.subtle, padding: '2px 8px', borderRadius: radius.sm }}>
          {job.experience}
        </span>
      </div>
    </article>
  )
}
