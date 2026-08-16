/**
 * Post-publish share modal.
 *
 * Opens the moment a listing goes live, because that is the only moment an
 * editor is certain to be looking — a "share this" button on a list screen is
 * one nobody clicks.
 *
 * **The LinkedIn flow is two steps and cannot be one.** LinkedIn removed
 * prefilled text from its share endpoint; it scrapes the destination page's own
 * metadata instead. So the caption is copied to the clipboard *before* the tab
 * opens, and the modal says so. Pretending otherwise would leave people staring
 * at an empty composer wondering what went wrong.
 */

import { useEffect, useState } from 'react'
import { color, radius, shadow, size, weight } from '@/design-system'
import { useShareAssets } from '@/hooks/queries'
import { describeError } from '@/lib/http'
import type { ShareAssets } from '@/lib/api/share'
import Icon from '@/components/Icon'

type Platform = 'linkedin' | 'whatsapp' | 'facebook' | 'twitter'

const PLATFORMS: { key: Platform; label: string; tint: string; captionOf: (a: ShareAssets) => string }[] = [
  { key: 'linkedin', label: 'LinkedIn', tint: '#0A66C2', captionOf: a => a.linkedin_caption },
  { key: 'whatsapp', label: 'WhatsApp', tint: '#25D366', captionOf: a => a.whatsapp_message },
  { key: 'facebook', label: 'Facebook', tint: '#1877F2', captionOf: a => a.facebook_caption },
  { key: 'twitter', label: 'X', tint: '#0F1419', captionOf: a => a.twitter_caption },
]

/** Clipboard access needs a secure context; `http://` on a LAN IP is not one. */
async function copy(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export default function ShareJobModal({
  jobId,
  onClose,
}: {
  jobId: string | null
  onClose: () => void
}) {
  const { data, isPending, isError, error } = useShareAssets(jobId)
  const [platform, setPlatform] = useState<Platform>('linkedin')
  const [copied, setCopied] = useState(false)

  // Escape closes. A modal that traps someone who published by accident is a
  // worse problem than the one it solves.
  useEffect(() => {
    if (!jobId) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [jobId, onClose])

  useEffect(() => setCopied(false), [platform])

  if (!jobId) return null

  const active = PLATFORMS.find(p => p.key === platform)!
  const caption = data ? active.captionOf(data) : ''

  const handleShare = async () => {
    if (!data) return
    // Copy first, then open. Reversing the order loses the clipboard write in
    // some browsers once focus moves to the new tab.
    if (platform === 'linkedin' || platform === 'facebook') {
      const ok = await copy(caption)
      setCopied(ok)
    }
    window.open(data.share_urls[platform], '_blank', 'noopener,noreferrer')
  }

  const handleDownload = () => {
    if (!data) return
    // A plain anchor rather than fetch+blob: the image is same-origin and the
    // browser streams it straight to disk without holding it in memory.
    const link = document.createElement('a')
    link.href = data.image_url
    link.download = `${data.job_title.replace(/\s+/g, '-').toLowerCase()}-share.png`
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Share this listing"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(17, 24, 39, 0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24, zIndex: 1000,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: color.surface.base, borderRadius: radius['4xl'], boxShadow: shadow.menu,
          width: '100%', maxWidth: 880, maxHeight: '90vh', overflow: 'auto',
        }}
      >
        {/* Header */}
        <div style={{ padding: '24px 28px 0', display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <div style={{ fontSize: size['3xl'], fontWeight: weight.bold, color: color.text.primary }}>
              Job published successfully
            </div>
            <div style={{ fontSize: size.sm, color: color.text.muted, marginTop: 4 }}>
              Share it while it is fresh — most applications arrive in the first 48 hours.
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              border: 'none', background: 'none', cursor: 'pointer',
              fontSize: size['3xl'], color: color.text.muted, lineHeight: 1, padding: 0,
            }}
          >
            ×
          </button>
        </div>

        {isError ? (
          <div style={{ padding: '28px', fontSize: size.sm, color: color.danger.base }}>
            {describeError(error)}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 24, padding: 28 }}>
            {/* Card preview */}
            <div>
              <div
                style={{
                  border: `1px solid ${color.border.base}`, borderRadius: radius['2xl'],
                  overflow: 'hidden', background: color.surface.canvas, aspectRatio: '1 / 1',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                {isPending || !data ? (
                  <span style={{ fontSize: size.sm, color: color.text.muted }}>Generating…</span>
                ) : (
                  <img
                    src={data.image_url}
                    alt={`Share card for ${data.job_title}`}
                    style={{ width: '100%', display: 'block' }}
                  />
                )}
              </div>
              <button
                onClick={handleDownload}
                disabled={!data}
                style={{
                  width: '100%', marginTop: 10, padding: '10px 16px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  border: `1px solid ${color.border.base}`, borderRadius: radius.xl,
                  background: color.surface.base, color: color.text.strong,
                  fontSize: size.sm, fontWeight: weight.medium, cursor: 'pointer',
                }}
              >
                <Icon name="download" size={15} />
                Download image
              </button>
            </div>

            {/* Caption + actions */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {PLATFORMS.map(p => (
                  <button
                    key={p.key}
                    onClick={() => setPlatform(p.key)}
                    style={{
                      padding: '6px 14px', borderRadius: radius.lg, cursor: 'pointer',
                      fontSize: size.sm, fontWeight: weight.medium,
                      border: `1px solid ${platform === p.key ? p.tint : color.border.base}`,
                      background: platform === p.key ? `${p.tint}12` : color.surface.base,
                      color: platform === p.key ? p.tint : color.text.secondary,
                    }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              <textarea
                readOnly
                value={isPending ? 'Generating caption…' : caption}
                rows={12}
                style={{
                  width: '100%', resize: 'vertical', padding: '14px 16px',
                  border: `1px solid ${color.border.base}`, borderRadius: radius['2xl'],
                  background: color.surface.canvas, color: color.text.primary,
                  fontSize: size.sm, lineHeight: 1.55, fontFamily: 'inherit',
                }}
              />

              {(platform === 'linkedin' || platform === 'facebook') && (
                <div style={{ fontSize: size.xs, color: color.text.muted, lineHeight: 1.5 }}>
                  {active.label} does not accept prefilled text — it reads the job page instead.
                  The caption is copied to your clipboard when you click share; paste it into the
                  composer, then attach the downloaded image.
                </div>
              )}

              <div style={{ display: 'flex', gap: 8, marginTop: 'auto', flexWrap: 'wrap' }}>
                <button
                  onClick={() => void handleShare()}
                  disabled={!data}
                  style={{
                    flex: 1, minWidth: 180, padding: '11px 20px', border: 'none',
                    borderRadius: radius.xl, background: active.tint, color: '#fff',
                    fontSize: size.base, fontWeight: weight.semibold, cursor: 'pointer',
                  }}
                >
                  Share on {active.label}
                </button>
                <button
                  onClick={async () => setCopied(await copy(caption))}
                  disabled={!data}
                  style={{
                    padding: '11px 20px', border: `1px solid ${color.border.base}`,
                    display: 'inline-flex', alignItems: 'center', gap: 8,
                    borderRadius: radius.xl, background: color.surface.base,
                    color: color.text.strong, fontSize: size.base,
                    fontWeight: weight.medium, cursor: 'pointer',
                  }}
                >
                  {copied ? <><Icon name="check" size={15} /> Copied</> : <><Icon name="copy" size={15} /> Copy caption</>}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
