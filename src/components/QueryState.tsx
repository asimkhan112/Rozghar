/**
 * Loading, error and empty surfaces for data-backed pages.
 *
 * Three states the prototype never had, because its data was a synchronous
 * array that always existed. Real data has all three, and a page that renders
 * nothing while it waits is indistinguishable from a page that is broken.
 *
 * Styling reuses the design tokens rather than introducing new values, so
 * these read as part of the same product and not as developer scaffolding.
 */

import type { CSSProperties, ReactNode } from "react"
import { color, radius, size, weight } from "@/design-system"
import { IconBadge, type IconName, type IconTone } from "@/components/Icon"

/**
 * A card-shaped placeholder.
 *
 * Matching the real card's footprint matters: a skeleton that is the wrong
 * height makes the page jump when results arrive, which is the layout shift
 * the skeleton existed to prevent.
 */
export function JobCardSkeleton() {
  return (
    <div
      aria-hidden
      style={{
        background: color.surface.base,
        border: `1px solid ${color.border.base}`,
        borderRadius: radius["3xl"],
        padding: "18px 20px",
        minHeight: 168,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <div
          style={{ ...shimmer, width: 40, height: 40, borderRadius: radius.xl }}
        />
        <div
          style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}
        >
          <div style={{ ...shimmer, width: "70%", height: 14 }} />
          <div style={{ ...shimmer, width: "45%", height: 11 }} />
        </div>
      </div>
      <div style={{ ...shimmer, width: "100%", height: 11 }} />
      <div style={{ ...shimmer, width: "60%", height: 11 }} />
      <div style={{ display: "flex", gap: 8, marginTop: "auto" }}>
        <div
          style={{ ...shimmer, width: 72, height: 20, borderRadius: radius.md }}
        />
        <div
          style={{ ...shimmer, width: 88, height: 20, borderRadius: radius.md }}
        />
      </div>
    </div>
  )
}

/** A neutral block. Deliberately static — a pulsing animation on a slow
 * connection is a distraction, not information. */
const shimmer: CSSProperties = {
  background: color.border.base,
  borderRadius: radius.sm,
  opacity: 0.55,
}

export function JobGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
        gap: 12,
      }}
    >
      {Array.from({ length: count }, (_, i) => (
        <JobCardSkeleton key={i} />
      ))}
    </div>
  )
}

const panel: CSSProperties = {
  background: color.surface.base,
  border: `1px solid ${color.border.base}`,
  borderRadius: radius["3xl"],
  padding: "60px 24px",
  textAlign: "center",
}

export function EmptyPanel({
  icon,
  tone = "brand",
  title,
  message,
  action,
}: {
  icon: IconName
  tone?: IconTone
  title: string
  message: string
  action?: ReactNode
}) {
  return (
    <div style={panel}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
        <IconBadge name={icon} size="lg" tone={tone} />
      </div>
      <div
        style={{
          fontSize: size.lg,
          fontWeight: weight.bold,
          color: color.text.primary,
          marginBottom: 6,
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontSize: size.sm,
          color: color.text.muted,
          maxWidth: 420,
          margin: "0 auto",
        }}
      >
        {message}
      </div>
      {action ? <div style={{ marginTop: 20 }}>{action}</div> : null}
    </div>
  )
}

/**
 * A failure the visitor can act on.
 *
 * Always offers a retry: most failures here are transient — a dropped
 * connection, a restarting server — and a dead end with no way forward makes a
 * five-second outage feel permanent.
 */
export function ErrorPanel({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div style={panel} role="alert">
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
        <IconBadge name="alert" size="lg" tone="danger" />
      </div>
      <div
        style={{
          fontSize: size.lg,
          fontWeight: weight.bold,
          color: color.text.primary,
          marginBottom: 6,
        }}
      >
        Could not load this
      </div>
      <div
        style={{
          fontSize: size.sm,
          color: color.text.muted,
          maxWidth: 420,
          margin: "0 auto 20px",
        }}
      >
        {message}
      </div>
      {onRetry ? (
        <button
          onClick={onRetry}
          style={{
            padding: "10px 24px",
            background: color.brand.base,
            border: "none",
            borderRadius: radius.xl,
            color: color.surface.base,
            fontSize: size.base,
            fontWeight: weight.medium,
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      ) : null}
    </div>
  )
}
