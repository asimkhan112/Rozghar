import { Link } from 'react-router'
import { color, linkReset, radius, size, weight } from '@/design-system'

/**
 * Site footer.
 *
 * Added because About, Contact and the policy pages existed as routes with
 * nothing linking to them — reachable only by typing the URL. A footer is also
 * where a reader expects to find the legal pages, and where a search engine
 * expects them to be linked from.
 */

const COLUMNS: { heading: string; links: { label: string; to: string }[] }[] = [
  {
    heading: 'Find work',
    links: [
      { label: 'Browse jobs', to: '/jobs' },
      { label: 'Categories', to: '/categories' },
      { label: 'Remote jobs', to: '/jobs?work_type=Remote' },
      { label: 'Saved jobs', to: '/saved-jobs' },
    ],
  },
  {
    heading: 'Rozgar.pk',
    links: [
      { label: 'About', to: '/about' },
      { label: 'Contact', to: '/contact' },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy Policy', to: '/privacy' },
      { label: 'Terms of Service', to: '/terms' },
    ],
  },
]

export default function SiteFooter() {
  const year = new Date().getFullYear()
  return (
    <footer
      style={{
        borderTop: `1px solid ${color.border.base}`,
        background: color.surface.base,
        marginTop: 'auto',
      }}
    >
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '36px 24px 28px' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 28,
            marginBottom: 28,
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10 }}>
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: radius.xl,
                  background: color.brand.base,
                  color: color.text.inverse,
                  fontSize: size['2xs'],
                  fontWeight: weight.bold,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                RZ
              </span>
              <span style={{ fontSize: size.md, fontWeight: weight.bold, color: color.text.primary }}>
                Rozgar.pk
              </span>
            </div>
            <p style={{ fontSize: size.xs, color: color.text.secondary, lineHeight: 1.6, margin: 0, maxWidth: 240 }}>
              Curated jobs from employers across Pakistan. Browse and apply without an account.
            </p>
          </div>

          {COLUMNS.map(column => (
            <div key={column.heading}>
              <div style={{ fontSize: size.xs, fontWeight: weight.semibold, color: color.text.primary, marginBottom: 10 }}>
                {column.heading}
              </div>
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 7 }}>
                {column.links.map(link => (
                  <li key={link.to}>
                    <Link
                      to={link.to}
                      style={{ ...linkReset, fontSize: size.xs, color: color.text.secondary }}
                      onMouseEnter={e => (e.currentTarget.style.color = color.brand.base)}
                      onMouseLeave={e => (e.currentTarget.style.color = color.text.secondary)}
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div
          style={{
            borderTop: `1px solid ${color.border.faint}`,
            paddingTop: 18,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <span style={{ fontSize: size['2xs'], color: color.text.muted }}>
            © {year} Rozgar.pk. All rights reserved.
          </span>
          <span style={{ fontSize: size['2xs'], color: color.text.muted }}>
            Listings link to the employer's own application page.
          </span>
        </div>
      </div>
    </footer>
  )
}
