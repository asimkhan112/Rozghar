import type { ReactNode, CSSProperties } from 'react'
import { adminFieldLabel, adminInput, adminStatusTone, color, radius, size, weight } from '@/design-system'

/** Shared admin field style. Re-exported under its historical name. */
export const IS = adminInput

export function StatusPill({ status }: { status: string }) {
  const cfg = adminStatusTone[status] ?? { bg: color.surface.muted, color: color.text.muted }
  return (
    <span style={{ fontSize: size['2xs'], padding: '3px 8px', borderRadius: radius.sm, fontWeight: weight.semibold, background: cfg.bg, color: cfg.color, textTransform: 'capitalize', whiteSpace: 'nowrap' }}>
      {status}
    </span>
  )
}

export function FormSection({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ marginBottom: 4 }}>
        <div style={{ fontSize: size.lg, fontWeight: weight.bold, color: color.text.primary }}>{title}</div>
        {subtitle && <div style={{ fontSize: size.sm, color: color.text.muted, marginTop: 2 }}>{subtitle}</div>}
      </div>
      {children}
    </div>
  )
}

export function FRow({ children, cols = 1 }: { children: ReactNode; cols?: number }) {
  return <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 16 }}>{children}</div>
}

export function FField({ label, children, style: extStyle }: { label: string; children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={extStyle}>
      <label style={adminFieldLabel}>{label}</label>
      {children}
    </div>
  )
}



