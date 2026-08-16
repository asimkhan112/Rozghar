import { useState } from "react"
import Navbar from "../components/Navbar"
import JobCard from "../components/JobCard"
import {
  useJobFilters,
  ALL_CATEGORIES,
  ALL_LOCATIONS,
  LOCATIONS,
  CATEGORIES_LIST,
  WORK_TYPES,
  EMPLOYMENT_TYPES_LIST,
  EXP_LEVELS,
  DATE_FILTERS,
  SORT_OPTIONS,
} from "@/hooks/useJobFilters"
import { useCategories, useJobs, useLocations } from "@/hooks/queries"
import { toJobQuery } from "@/lib/api/filters"
import { describeError } from "@/lib/http"
import { ErrorPanel, JobGridSkeleton } from "@/components/QueryState"
import {
  bareInput,
  pillTone,
  color,
  radius,
  size,
  toolbarSelect,
  tracking,
  weight,
} from "@/design-system"
import { IconBadge } from "@/components/Icon"

export default function JobsPage() {
  const { filters, page, setFilter, setPage, reset, hasAdvancedFilters } =
    useJobFilters()
  const [filterOpen, setFilterOpen] = useState(false)
  const perPage = 8

  // Reference data drives the two taxonomy dropdowns and resolves the label in
  // the URL to the slug the API filters on.
  const categories = useCategories()
  const locations = useLocations()

  const query = toJobQuery(
    filters,
    { categories: categories.data ?? [], locations: locations.data ?? [] },
    // The list is cumulative — "Load more" appends rather than paging — so the
    // request always asks for everything up to the current page.
    { page: 1, perPage: page * perPage },
  )
  const { data, isPending, isError, error, isPlaceholderData, refetch } =
    useJobs(query)

  const jobs = data?.items ?? []
  const total = data?.total ?? 0
  const hasMore = data?.hasMore ?? false

  const categoryOptions = categories.data?.length
    ? [ALL_CATEGORIES, ...categories.data.map((c) => c.name)]
    : CATEGORIES_LIST
  const locationOptions = locations.data?.length
    ? [ALL_LOCATIONS, ...locations.data.map((l) => l.label)]
    : LOCATIONS

  return (
    <div style={{ minHeight: "100vh", background: color.surface.canvas }}>
      <Navbar />

      {/* Search bar strip */}
      <div
        style={{
          background: color.surface.base,
          borderBottom: `1px solid ${color.border.base}`,
          padding: "16px 24px",
        }}
      >
        <div
          style={{
            maxWidth: 1200,
            margin: "0 auto",
            display: "flex",
            gap: 12,
            alignItems: "center",
            flexWrap: "wrap",
          }}
        >
          <div
            style={{
              flex: 1,
              minWidth: 200,
              display: "flex",
              alignItems: "center",
              gap: 8,
              border: `1px solid ${color.border.base}`,
              borderRadius: radius.xl,
              padding: "9px 14px",
              background: color.surface.base,
            }}
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke={color.text.muted}
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              value={filters.q}
              onChange={(e) => setFilter("q", e.target.value)}
              placeholder="Search jobs..."
              style={bareInput(size.base, { width: "100%" })}
            />
          </div>
          <select
            value={filters.location}
            onChange={(e) => setFilter("location", e.target.value)}
            style={toolbarSelect}
          >
            {locationOptions.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
          <button
            onClick={() => setFilterOpen(!filterOpen)}
            style={{
              ...pillTone(filterOpen),
              borderRadius: radius.xl,
              padding: "9px 16px",
              fontSize: size.base,
              fontWeight: weight.medium,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="4" y1="6" x2="20" y2="6" />
              <line x1="8" y1="12" x2="16" y2="12" />
              <line x1="12" y1="18" x2="12" y2="18" strokeLinecap="round" />
            </svg>
            Filters
            {hasAdvancedFilters && (
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: radius.full,
                  background: color.brand.base,
                }}
              />
            )}
          </button>
          <select
            value={filters.sort}
            onChange={(e) => setFilter("sort", e.target.value)}
            style={toolbarSelect}
          >
            {SORT_OPTIONS.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </div>

        {/* Filter drawer */}
        {filterOpen && (
          <div
            style={{
              maxWidth: 1200,
              margin: "12px auto 0",
              borderTop: `1px solid ${color.border.base}`,
              paddingTop: 16,
              display: "flex",
              gap: 16,
              flexWrap: "wrap",
            }}
          >
            <FilterGroup
              label="Category"
              value={filters.category}
              options={categoryOptions}
              onChange={(v) => setFilter("category", v)}
            />
            <FilterGroup
              label="Work Type"
              value={filters.workType}
              options={WORK_TYPES}
              onChange={(v) => setFilter("workType", v)}
            />
            <FilterGroup
              label="Employment"
              value={filters.employmentType}
              options={EMPLOYMENT_TYPES_LIST}
              onChange={(v) => setFilter("employmentType", v)}
            />
            <FilterGroup
              label="Experience"
              value={filters.experience}
              options={EXP_LEVELS}
              onChange={(v) => setFilter("experience", v)}
            />
            <FilterGroup
              label="Date Posted"
              value={filters.datePosted}
              options={DATE_FILTERS}
              onChange={(v) => setFilter("datePosted", v)}
            />
            {hasAdvancedFilters && (
              <button
                onClick={() =>
                  reset([
                    "workType",
                    "employmentType",
                    "category",
                    "experience",
                    "datePosted",
                  ])
                }
                style={{
                  alignSelf: "flex-end",
                  padding: "7px 14px",
                  border: `1px solid ${color.border.base}`,
                  borderRadius: radius.xl,
                  background: color.surface.base,
                  fontSize: size.sm,
                  color: color.text.secondary,
                  cursor: "pointer",
                }}
              >
                Clear all
              </button>
            )}
          </div>
        )}
      </div>

      {/* Results */}
      <div
        style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 24px 80px" }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 16,
          }}
        >
          <div>
            <span
              style={{
                fontSize: size.md,
                fontWeight: weight.semibold,
                color: color.text.primary,
              }}
            >
              {isPending
                ? "Searching…"
                : `${total.toLocaleString()} jobs found`}
            </span>
            {(filters.q || filters.location !== ALL_LOCATIONS) && (
              <span
                style={{
                  fontSize: size.base,
                  color: color.text.secondary,
                  marginLeft: 8,
                }}
              >
                {filters.q && `for "${filters.q}"`}
                {filters.location !== ALL_LOCATIONS &&
                  ` in ${filters.location}`}
              </span>
            )}
          </div>
        </div>

        {isPending ? (
          <JobGridSkeleton count={perPage} />
        ) : isError ? (
          <ErrorPanel
            message={describeError(error)}
            onRetry={() => void refetch()}
          />
        ) : jobs.length === 0 ? (
          <EmptyState onReset={() => reset()} />
        ) : (
          <>
            {/* Dimmed while the next page is in flight. The previous results
                stay on screen rather than blanking, which reads as progress
                instead of breakage. */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                gap: 12,
                ...(isPlaceholderData
                  ? { opacity: 0.6, transition: "opacity 0.15s" }
                  : {}),
              }}
            >
              {jobs.map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
            </div>
            {hasMore && (
              <div style={{ textAlign: "center", marginTop: 32 }}>
                <button
                  onClick={() => setPage(page + 1)}
                  style={{
                    padding: "12px 32px",
                    border: `1px solid ${color.border.base}`,
                    borderRadius: radius["2xl"],
                    background: color.surface.base,
                    fontSize: size.base,
                    fontWeight: weight.medium,
                    color: color.text.primary,
                    cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = color.brand.tint
                    e.currentTarget.style.borderColor = color.brand.alpha40
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = color.surface.base
                    e.currentTarget.style.borderColor = color.border.base
                  }}
                >
                  Load more · {(total - jobs.length).toLocaleString()} remaining
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function FilterGroup({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <div>
      <div
        style={{
          fontSize: size["2xs"],
          fontWeight: weight.semibold,
          color: color.text.muted,
          textTransform: "uppercase",
          letterSpacing: tracking.wide,
          marginBottom: 6,
        }}
      >
        {label}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {options.map((opt) => (
          <button
            key={opt}
            onClick={() => onChange(opt)}
            style={{
              ...pillTone(value === opt),
              borderRadius: radius.md,
              padding: "5px 12px",
              fontSize: size.sm,
              fontWeight: value === opt ? weight.semibold : weight.regular,
              cursor: "pointer",
              transition: "all 0.1s",
            }}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  )
}

function EmptyState({ onReset }: { onReset: () => void }) {
  return (
    <div style={{ textAlign: "center", padding: "80px 24px" }}>
      <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
        <IconBadge name="search" size="xl" />
      </div>
      <h3
        style={{
          fontSize: size["3xl"],
          fontWeight: weight.bold,
          color: color.text.primary,
          margin: "0 0 8px",
        }}
      >
        No jobs found
      </h3>
      <p
        style={{
          fontSize: size.md,
          color: color.text.secondary,
          margin: "0 0 24px",
          maxWidth: 360,
          marginInline: "auto",
        }}
      >
        We couldn't find any jobs matching your search. Try different keywords
        or remove some filters.
      </p>
      <button
        onClick={onReset}
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
        Reset filters
      </button>
    </div>
  )
}
