import { Link } from "react-router"
import Navbar from "@/components/Navbar"
import { useCategories } from "@/hooks/queries"
import { describeError } from "@/lib/http"
import { EmptyPanel, ErrorPanel } from "@/components/QueryState"
import {
  color,
  linkReset,
  radius,
  size,
  tracking,
  weight,
} from "@/design-system"
import { categoryIcon, IconBadge } from "@/components/Icon"
import SiteFooter from "@/components/SiteFooter"
import { usePageMeta } from "@/lib/seo"

/**
 * Category index.
 *
 * Reuses the homepage category tile exactly — same border, radius, padding,
 * icon size and hover treatment — so the page introduces no new visual
 * language. Each tile links into the jobs list with the category pre-applied.
 */
export default function CategoriesPage() {
  const { data, isPending, isError, error, refetch } = useCategories()
  const categories = data ?? []

  usePageMeta({
    title: "Job Categories",
    description:
      "Every field hiring on Plenilo.com — technology, design, finance, marketing, government and more — with a live count of open roles in each.",
  })

  return (
    <div style={{ minHeight: "100vh", background: color.surface.canvas }}>
      <Navbar />
      <div
        style={{ maxWidth: 1200, margin: "0 auto", padding: "40px 24px 80px" }}
      >
        <div style={{ marginBottom: 32 }}>
          <h1
            style={{
              fontSize: size["5xl"],
              fontWeight: weight.bold,
              color: color.text.primary,
              margin: "0 0 6px",
              letterSpacing: tracking.tight,
            }}
          >
            Browse by Category
          </h1>
          <p
            style={{
              fontSize: size.base,
              color: color.text.secondary,
              margin: 0,
            }}
          >
            {isPending
              ? "Loading categories…"
              : `${categories.length} categories across technology, government, finance and more`}
          </p>
        </div>

        {isError ? (
          <ErrorPanel
            message={describeError(error)}
            onRetry={() => void refetch()}
          />
        ) : !isPending && categories.length === 0 ? (
          <EmptyPanel
            icon="layers"
            title="No categories yet"
            message="Categories appear here once listings have been published against them."
          />
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            {categories.map((cat) => (
              <Link
                key={cat.name}
                to={`/jobs?category=${encodeURIComponent(cat.name)}`}
                style={{
                  ...linkReset,
                  background: color.surface.base,
                  border: `1px solid ${color.border.base}`,
                  borderRadius: radius["3xl"],
                  padding: "20px 24px",
                  cursor: "pointer",
                  textAlign: "left",
                  transition: "all 0.15s",
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = color.brand.alpha40
                  e.currentTarget.style.background = color.brand.tint
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = color.border.base
                  e.currentTarget.style.background = color.surface.base
                }}
              >
                <IconBadge name={categoryIcon(cat.icon, cat.slug)} size="md" />
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: size.md,
                      fontWeight: weight.semibold,
                      color: color.text.primary,
                      marginBottom: 3,
                    }}
                  >
                    {cat.name}
                  </div>
                  <div style={{ fontSize: size.xs, color: color.text.muted }}>
                    {cat.count > 0 ? (
                      <span
                        style={{
                          color: color.brand.base,
                          fontWeight: weight.medium,
                        }}
                      >
                        {cat.count.toLocaleString()} live now
                      </span>
                    ) : (
                      "No open roles"
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
      <SiteFooter />
    </div>
  )
}
