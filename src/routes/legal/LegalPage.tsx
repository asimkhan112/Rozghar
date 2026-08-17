import type { ReactNode } from 'react'
import Navbar from '@/components/Navbar'
import SiteFooter from '@/components/SiteFooter'
import { color, radius, size, tracking, weight } from '@/design-system'

/**
 * Shared shell for the policy pages.
 *
 * They are long documents rather than product screens, so they get a narrower
 * measure and a plain vertical rhythm: this layout's job is to be read.
 */
export function LegalPage({
  title,
  intro,
  updated,
  children,
}: {
  title: string
  intro: string
  updated: string
  children: ReactNode
}) {
  return (
    <div style={{ minHeight: '100vh', background: color.surface.canvas, display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <div style={{ flex: 1, maxWidth: 760, width: '100%', margin: '0 auto', padding: '40px 24px 64px' }}>
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: size['5xl'], fontWeight: weight.bold, color: color.text.primary, margin: '0 0 6px', letterSpacing: tracking.tight }}>
            {title}
          </h1>
          <p style={{ fontSize: size.base, color: color.text.secondary, margin: '0 0 8px' }}>{intro}</p>
          <p style={{ fontSize: size.xs, color: color.text.muted, margin: 0 }}>Last updated {updated}</p>
        </div>
        <div style={{ background: color.surface.base, border: `1px solid ${color.border.base}`, borderRadius: radius['5xl'], padding: '8px 32px 28px' }}>
          {children}
        </div>
      </div>
      <SiteFooter />
    </div>
  )
}

export function Section({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section style={{ marginTop: 26 }}>
      <h2 style={{ fontSize: size.xl, fontWeight: weight.bold, color: color.text.primary, margin: '0 0 10px' }}>
        {heading}
      </h2>
      {children}
    </section>
  )
}

export function P({ children }: { children: ReactNode }) {
  return (
    <p style={{ fontSize: size.md, color: color.text.strong, lineHeight: 1.7, margin: '0 0 12px' }}>{children}</p>
  )
}

export function List({ items }: { items: ReactNode[] }) {
  return (
    // `listStyle` is set explicitly: Tailwind's preflight strips list markers
    // from every `ul`, and an unmarked list of policy clauses reads as prose.
    <ul style={{ margin: '0 0 12px', paddingLeft: 22, listStyle: 'disc' }}>
      {items.map((item, i) => (
        <li key={i} style={{ fontSize: size.md, color: color.text.strong, lineHeight: 1.7, marginBottom: 6 }}>
          {item}
        </li>
      ))}
    </ul>
  )
}

/**
 * States plainly that this text has not been through a lawyer.
 *
 * On the page rather than only in a commit message, because the person who
 * needs to act on it is whoever is about to launch, and they will read the
 * page long before they read the history.
 */
export function ReviewNotice() {
  return (
    <div style={{ marginTop: 28, padding: '14px 18px', background: color.warning.tintAlt, border: `1px solid ${color.warning.tintSoft}`, borderRadius: radius['2xl'] }}>
      <p style={{ fontSize: size.sm, color: color.warning.ochre, lineHeight: 1.6, margin: 0 }}>
        <strong>Not yet reviewed by a lawyer.</strong> This document describes how
        Rozgar.pk actually works and is a drafting starting point, not legal advice.
        Have it checked against Pakistan's data-protection and consumer legislation,
        and replace every placeholder marked in [square brackets], before launch.
      </p>
    </div>
  )
}
