import { useState } from "react"
import { Link, useNavigate } from "react-router"
import Navbar from "../components/Navbar"
import JobCard from "../components/JobCard"
import { useSuggest, useCategories, useJobs } from "@/hooks/queries"
import { describeError } from "@/lib/http"
import { ErrorPanel, JobGridSkeleton } from "@/components/QueryState"
import { bareInput, linkReset } from "@/design-system"
import {
  pillTone,
  color,
  radius,
  shadow,
  size,
  tracking,
  weight,
} from "@/design-system"
import Icon, { categoryIcon, IconBadge } from "@/components/Icon"
import SearchSuggest, { type SuggestChoice, useSuggestNavigation } from "@/components/SearchSuggest"
import SiteFooter from "@/components/SiteFooter"
import { DEFAULT_TITLE, usePageMeta } from "@/lib/seo"

const QUICK_FILTERS = [
  "Remote Jobs",
  "Internships",
  "Fresh Graduate",
  "Government Jobs",
  "IT Jobs",
  "Hybrid Jobs",
]

const TRUST_ITEMS = [
  { icon: "zap", label: "Updated Daily", sub: "Fresh listings every 24h" },
  { icon: "shield", label: "Verified Sources", sub: "Direct from employers" },
  { icon: "external", label: "Direct Apply", sub: "No middleman, no signup" },
  { icon: "lock", label: "No Registration", sub: "Browse freely, apply fast" },
] as const

export default function HomePage() {
  const navigate = useNavigate()

  // The landing page is the one page whose subject *is* the site, so it keeps
  // the brand title rather than prefixing a section name onto it.
  usePageMeta({ title: DEFAULT_TITLE })

  // Four requests rather than one, because these are four different questions
  // and the API answers each with an indexed filter. Fetching the catalogue and
  // slicing it client-side is what the mock did, and it does not survive a
  // catalogue larger than a page.
  const latest = useJobs({ sort: "recent", per_page: 4 })
  const featured = useJobs({ featured: true, per_page: 5 })
  const remote = useJobs({ work_type: "remote", per_page: 6 })
  const freshGrad = useJobs({ employment_type: "internship", per_page: 4 })
  const categories = useCategories()

  /** Search submits into the jobs route as query params, so results are shareable. */
  const handleSearch = (q: string, loc: string) => {
    const params = new URLSearchParams()
    if (q.trim()) params.set("q", q.trim())
    if (loc.trim()) params.set("location", loc.trim())
    const qs = params.toString()
    navigate(qs ? `/jobs?${qs}` : "/jobs")
  }

  const [query, setQuery] = useState("")
  const [location, setLocation] = useState("")
  const [suggestOpen, setSuggestOpen] = useState(false)
  const suggest = useSuggest(query)

  /** Where a suggestion takes the reader.
   *
   *  A job goes to the listing itself; everything else is a filtered search,
   *  because a company or a skill is a set of listings rather than a page. */
  const applySuggestion = ({ group, item }: SuggestChoice) => {
    setSuggestOpen(false)
    if (group === "jobs" && item.slug) {
      navigate(`/jobs/${item.slug}`)
      return
    }
    if (group === "locations") {
      setLocation(item.text)
      handleSearch(query, item.text)
      return
    }
    if (group === "categories") {
      navigate(`/jobs?category=${encodeURIComponent(item.text)}`)
      return
    }
    // Companies and skills are free-text searches.
    setQuery(item.text)
    handleSearch(item.text, location)
  }

  const nav = useSuggestNavigation(suggest.groups, {
    open: suggestOpen,
    onChoose: applySuggestion,
    onDismiss: () => setSuggestOpen(false),
  })
  const [activeFilter, setActiveFilter] = useState<string | null>(null)

  const latestJobs = latest.data?.items ?? []
  const remoteJobs = remote.data?.items ?? []
  const freshGradJobs = freshGrad.data?.items ?? []
  const featuredJobs = featured.data?.items ?? []
  const categoryList = categories.data ?? []
  /** Catalogue size, reported by the list response rather than counted client-side. */
  const totalJobs = latest.data?.total ?? 0

  return (
    <div style={{ minHeight: "100vh", background: color.surface.canvas }}>
      <Navbar />

      {/* Hero */}
      <section
        style={{
          background: color.surface.base,
          borderBottom: `1px solid ${color.border.base}`,
          padding: "56px 24px 40px",
        }}
      >
        <div style={{ maxWidth: 720, margin: "0 auto", textAlign: "center" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: color.brand.tint,
              border: `1px solid ${color.brand.alpha30}`,
              borderRadius: radius.pill,
              padding: "5px 14px",
              marginBottom: 24,
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: radius.full,
                background: color.brand.base,
                animation: "pulse 2s infinite",
              }}
            />
            <span
              style={{
                fontSize: size.sm,
                color: color.brand.base,
                fontWeight: weight.medium,
              }}
            >
              1,240+ new jobs this week
            </span>
          </div>

          <h1
            style={{
              fontSize: "clamp(28px, 5vw, 48px)",
              fontWeight: weight.bold,
              color: color.text.primary,
              margin: "0 0 12px",
              lineHeight: 1.15,
              letterSpacing: tracking.tighter,
            }}
          >
            Find your next opportunity
            <br />
            <span style={{ color: color.brand.base }}>
              anywhere in the world
            </span>
          </h1>
          <p
            style={{
              fontSize: size.xl,
              color: color.text.secondary,
              margin: "0 0 32px",
              fontWeight: weight.regular,
              lineHeight: 1.6,
            }}
          >
            Curated jobs from top employers. Apply directly - no account needed.
          </p>

          {/* Search box. The relative wrapper sits outside the bar's own
              `overflow: hidden`, which would otherwise clip the dropdown. */}
          <div style={{ position: "relative" }}>
          <div
            style={{
              display: "flex",
              gap: 0,
              background: color.surface.base,
              border: `2px solid ${color.brand.base}`,
              borderRadius: radius["3xl"],
              overflow: "hidden",
              boxShadow: shadow.search,
            }}
          >
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                padding: "0 16px",
                gap: 10,
                borderRight: `1px solid ${color.border.base}`,
              }}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke={color.text.muted}
                strokeWidth="2"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setSuggestOpen(true)
                }}
                onFocus={() => setSuggestOpen(true)}
                onKeyDown={(e) => {
                  nav.onKeyDown(e)
                  // Enter with a highlighted row is a selection, which
                  // `nav.onKeyDown` already consumed.
                  if (e.key === "Enter" && !e.defaultPrevented) {
                    setSuggestOpen(false)
                    handleSearch(query, location)
                  }
                }}
                role="combobox"
                aria-expanded={suggestOpen}
                aria-autocomplete="list"
                placeholder="Job title, company, or skill..."
                style={bareInput(size.md, { flex: 1, padding: "14px 0" })}
              />
            </div>
            <div
              style={{
                width: 160,
                display: "flex",
                alignItems: "center",
                padding: "0 16px",
                gap: 8,
              }}
              className="loc-field"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke={color.text.muted}
                strokeWidth="2"
              >
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="City or Remote"
                style={bareInput(size.base, { flex: 1 })}
              />
            </div>
            <button
              onClick={() => handleSearch(query, location)}
              className="search-btn"
              // The label disappears on a phone, so the button needs a name of
              // its own — an icon alone announces as "button" to a screen
              // reader.
              aria-label="Search jobs"
              style={{
                background: color.brand.base,
                border: "none",
                cursor: "pointer",
                padding: "0 28px",
                fontSize: size.md,
                fontWeight: weight.semibold,
                color: color.surface.base,
                transition: "background 0.15s",
                whiteSpace: "nowrap",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = color.brand.hover)
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = color.brand.base)
              }
            >
              <span className="search-btn-label">Search Jobs</span>
              <svg
                className="search-btn-icon"
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </button>
          </div>
            <SearchSuggest
              query={query}
              groups={suggest.groups}
              choices={nav.choices}
              active={nav.active}
              onActiveChange={nav.setActive}
              open={suggestOpen && suggest.enabled}
              loading={suggest.isFetching}
              onChoose={applySuggestion}
              onDismiss={() => setSuggestOpen(false)}
            />
          </div>

          {/* Quick filters */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              marginTop: 16,
              justifyContent: "center",
            }}
          >
            {QUICK_FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => {
                  setActiveFilter(f)
                  handleSearch(f, "")
                }}
                style={{
                  ...pillTone(activeFilter === f),
                  borderRadius: radius.pill,
                  padding: "5px 14px",
                  fontSize: size.sm,
                  fontWeight: weight.medium,
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Trust indicators */}
      <section
        style={{
          background: color.surface.base,
          borderBottom: `1px solid ${color.border.base}`,
        }}
      >
        <div
          className="trust-grid"
          style={{
            maxWidth: 1200,
            margin: "0 auto",
            padding: "0 24px",
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            borderLeft: `1px solid ${color.border.base}`,
          }}
        >
          {TRUST_ITEMS.map((item, i) => (
            <div
              key={i}
              style={{
                padding: "16px 20px",
                borderRight: `1px solid ${color.border.base}`,
                display: "flex",
                alignItems: "center",
                gap: 12,
              }}
            >
              <IconBadge name={item.icon} size="sm" />
              <div>
                <div
                  className="trust-label"
                  style={{
                    fontSize: size.sm,
                    fontWeight: weight.semibold,
                    color: color.text.primary,
                  }}
                >
                  {item.label}
                </div>
                <div
                  className="trust-sub"
                  style={{
                    fontSize: size["2xs"],
                    color: color.text.muted,
                    marginTop: 1,
                  }}
                >
                  {item.sub}
                </div>
              </div>
            </div>
          ))}
        </div>
        <style>{`
          /* Below the desktop breakpoint these become one swipeable row rather
             than a grid. Four cells at 1fr on a phone gives every card less
             width than its own caption needs, which is what wrapped "Updated
             Daily" onto two lines and pushed the fourth card off-screen.
             Scrolling keeps each card whole and legible. */
          @media(max-width:768px){
            .trust-grid{
              display:flex!important;
              gap:0;
              overflow-x:auto;
              scroll-snap-type:x proximity;
              -webkit-overflow-scrolling:touch;
              /* The row is visibly clipped mid-card, which is a better scroll
                 affordance than a bar that most mobile browsers hide anyway. */
              scrollbar-width:none;
            }
            .trust-grid::-webkit-scrollbar{display:none;}
            .trust-grid > *{flex:0 0 auto;scroll-snap-align:start;}
            .trust-label,.trust-sub{white-space:nowrap;}
          }
        `}</style>
      </section>

      <div
        style={{ maxWidth: 1200, margin: "0 auto", padding: "40px 24px 80px" }}
      >
        {/* Latest Jobs + Featured sidebar */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 320px",
            gap: 32,
            alignItems: "start",
          }}
          className="main-grid"
        >
          {/* Latest jobs */}
          <div>
            <SectionHeader
              title="Latest Jobs"
              count={totalJobs}
              viewAllTo="/jobs"
            />
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 12,
                marginTop: 16,
              }}
            >
              {latest.isPending ? (
                <JobGridSkeleton count={4} />
              ) : latest.isError ? (
                <ErrorPanel
                  message={describeError(latest.error)}
                  onRetry={() => void latest.refetch()}
                />
              ) : (
                latestJobs.map((job) => <JobCard key={job.id} job={job} />)
              )}
            </div>
            <Link
              to="/jobs"
              style={{
                ...linkReset,
                textAlign: "center",
                width: "100%",
                marginTop: 16,
                padding: "12px",
                border: `1px solid ${color.border.base}`,
                borderRadius: radius["2xl"],
                background: color.surface.base,
                cursor: "pointer",
                fontSize: size.base,
                fontWeight: weight.medium,
                color: color.brand.base,
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
              View all {totalJobs.toLocaleString()} jobs →
            </Link>
          </div>

          {/* Sidebar */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Featured */}
            <div
              style={{
                background: color.surface.base,
                border: `1px solid ${color.border.base}`,
                borderRadius: radius["3xl"],
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  padding: "16px 20px",
                  borderBottom: `1px solid ${color.border.base}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span
                  style={{
                    fontSize: size.base,
                    fontWeight: weight.semibold,
                    color: color.text.primary,
                  }}
                >
                  <Icon name="star" size={12} style={{ display: "inline-block", verticalAlign: "-1px", marginRight: 5 }} />
                  Featured
                </span>
                <span
                  style={{
                    fontSize: size["2xs"],
                    background: color.warning.tint,
                    color: color.warning.text,
                    borderRadius: radius.sm,
                    padding: "2px 8px",
                    fontWeight: weight.semibold,
                  }}
                >
                  Sponsored
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                {featuredJobs.map((job, i) => (
                  <Link
                    key={job.id}
                    to={`/jobs/${job.slug}`}
                    style={{
                      ...linkReset,
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "14px 20px",
                      borderBottom:
                        i < featuredJobs.length - 1
                          ? `1px solid ${color.surface.subtle}`
                          : "none",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "background 0.1s",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.background = color.surface.canvas)
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "none")
                    }
                  >
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: radius.xl,
                        background: color.brand.tint,
                        color: color.brand.deep,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: size["2xs"],
                        fontWeight: weight.bold,
                        flexShrink: 0,
                      }}
                    >
                      {job.logo}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: size.sm,
                          fontWeight: weight.semibold,
                          color: color.text.primary,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {job.title}
                      </div>
                      <div
                        style={{
                          fontSize: size.xs,
                          color: color.text.secondary,
                        }}
                      >
                        {job.company}
                      </div>
                      <div
                        style={{
                          fontSize: size["2xs"],
                          color: color.brand.base,
                          marginTop: 2,
                        }}
                      >
                        {job.salary}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>

            {/* Stats */}
            <div
              style={{
                background: `linear-gradient(135deg, ${color.brand.base} 0%, ${color.brand.hover} 100%)`,
                borderRadius: radius["3xl"],
                padding: 20,
                color: color.surface.base,
              }}
            >
              <div
                style={{
                  fontSize: size.sm,
                  fontWeight: weight.medium,
                  opacity: 0.85,
                  marginBottom: 16,
                }}
              >
                Platform stats
              </div>
              {[
                { label: "Active Jobs", value: "14,280" },
                { label: "Companies Hiring", value: "2,140" },
                { label: "Applications Today", value: "8,920" },
              ].map((s) => (
                <div
                  key={s.label}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 10,
                  }}
                >
                  <span style={{ fontSize: size.sm, opacity: 0.8 }}>
                    {s.label}
                  </span>
                  <span style={{ fontSize: size.lg, fontWeight: weight.bold }}>
                    {s.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Remote Opportunities */}
        <div style={{ marginTop: 48 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              marginBottom: 20,
            }}
          >
            <div>
              <SectionHeader
                title="Remote Opportunities"
                count={remoteJobs.length}
                viewAllTo="/jobs"
              />
              <p
                style={{
                  margin: "4px 0 0",
                  fontSize: size.sm,
                  color: color.text.secondary,
                }}
              >
                Work from anywhere. Roles from employers worldwide.
              </p>
            </div>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
              gap: 12,
            }}
          >
            {remoteJobs.map((job) => (
              <JobCard key={job.id} job={job} compact />
            ))}
          </div>
        </div>

        {/* Fresh Graduate */}
        <div style={{ marginTop: 48 }}>
          <div
            style={{
              background: color.surface.base,
              border: `1px solid ${color.border.base}`,
              borderRadius: radius["5xl"],
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "20px 24px",
                borderBottom: `1px solid ${color.border.base}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                background: color.surface.hover,
              }}
            >
              <div>
                <h2
                  style={{
                    margin: 0,
                    fontSize: size["2xl"],
                    fontWeight: weight.bold,
                    color: color.text.primary,
                  }}
                >
                  For Fresh Graduates
                </h2>
                <p
                  style={{
                    margin: "4px 0 0",
                    fontSize: size.sm,
                    color: color.text.secondary,
                  }}
                >
                  Entry-level and internship opportunities to launch your career
                </p>
              </div>
              <Link
                to="/jobs"
                style={{
                  ...linkReset,
                  fontSize: size.sm,
                  color: color.brand.base,
                  fontWeight: weight.medium,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                View all →
              </Link>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: 0,
              }}
            >
              {freshGradJobs.map((job, i) => (
                <div
                  key={job.id}
                  style={{
                    borderRight:
                      (i + 1) % 2 !== 0
                        ? `1px solid ${color.border.base}`
                        : "none",
                    borderBottom: `1px solid ${color.border.base}`,
                  }}
                >
                  <Link
                    to={`/jobs/${job.slug}`}
                    style={{
                      ...linkReset,
                      display: "block",
                      width: "100%",
                      padding: "20px 24px",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "background 0.1s",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.background = color.surface.canvas)
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "none")
                    }
                  >
                    <div
                      style={{
                        fontSize: size.base,
                        fontWeight: weight.semibold,
                        color: color.text.primary,
                        marginBottom: 4,
                      }}
                    >
                      {job.title}
                    </div>
                    <div
                      style={{
                        fontSize: size.sm,
                        color: color.text.secondary,
                        marginBottom: 8,
                      }}
                    >
                      {job.company} · {job.location}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <span
                        style={{
                          fontSize: size["2xs"],
                          padding: "2px 8px",
                          borderRadius: radius.sm,
                          background: color.success.tint,
                          color: color.success.text,
                          fontWeight: weight.medium,
                        }}
                      >
                        {job.employmentType}
                      </span>
                      <span
                        style={{
                          fontSize: size["2xs"],
                          padding: "2px 8px",
                          borderRadius: radius.sm,
                          background: color.surface.subtle,
                          color: color.text.secondary,
                        }}
                      >
                        {job.salary}
                      </span>
                    </div>
                  </Link>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Categories */}
        <div style={{ marginTop: 48 }}>
          <SectionHeader
            title="Browse by Category"
            count={categoryList.length}
          />
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: 12,
              marginTop: 16,
            }}
          >
            {categoryList.map((cat) => (
              <Link
                key={cat.name}
                to={`/jobs?category=${encodeURIComponent(cat.name)}`}
                style={{
                  ...linkReset,
                  background: color.surface.base,
                  border: `1px solid ${color.border.base}`,
                  borderRadius: radius["3xl"],
                  padding: "16px 20px",
                  cursor: "pointer",
                  textAlign: "left",
                  transition: "all 0.15s",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = color.brand.alpha40
                  e.currentTarget.style.boxShadow = shadow.tile
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = color.border.base
                  e.currentTarget.style.boxShadow = "none"
                }}
              >
                <IconBadge name={categoryIcon(cat.icon, cat.slug)} size="lg" />
                <div>
                  <div
                    style={{
                      fontSize: size.sm,
                      fontWeight: weight.semibold,
                      color: color.text.primary,
                    }}
                  >
                    {cat.name}
                  </div>
                  <div
                    style={{
                      fontSize: size.xs,
                      color: color.text.muted,
                      marginTop: 2,
                    }}
                  >
                    {cat.count.toLocaleString()} jobs
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer
        style={{
          borderTop: `1px solid ${color.border.base}`,
          background: color.surface.base,
          padding: "32px 24px",
        }}
      >
        <div
          style={{
            maxWidth: 1200,
            margin: "0 auto",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 16,
          }}
        >
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 6,
              }}
            >
              <div
                style={{
                  width: 24,
                  height: 24,
                  background: color.brand.base,
                  borderRadius: radius.md,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <span
                  style={{
                    color: color.surface.base,
                    fontSize: size["3xs"],
                    fontWeight: weight.bold,
                  }}
                >
                  PL
                </span>
              </div>
              <span
                style={{
                  fontSize: size.base,
                  fontWeight: weight.semibold,
                  color: color.text.primary,
                }}
              >
                Plenilo.com
              </span>
            </div>
            <p
              style={{ margin: 0, fontSize: size.xs, color: color.text.muted }}
            >
              Trusted job discovery, worldwide
            </p>
          </div>
          <div style={{ display: "flex", gap: 24 }}>
            {["About", "Privacy", "Terms", "Contact"].map((l) => (
              <a
                key={l}
                href="#"
                style={{
                  fontSize: size.sm,
                  color: color.text.secondary,
                  textDecoration: "none",
                }}
              >
                {l}
              </a>
            ))}
          </div>
        </div>
      </footer>

      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        @media (max-width: 900px) {
          .main-grid { grid-template-columns: 1fr !important; }
        }
        /* The icon is the phone-sized form of this control; the label is the
           desktop one. Exactly one is ever displayed. */
        .search-btn-icon { display: none; }
        @media (max-width: 600px) {
          .loc-field { display: none !important; }
          .search-btn { padding: 0 18px !important; }
          .search-btn-label { display: none; }
          .search-btn-icon { display: block; }
        }
      `}</style>
      <SiteFooter />
    </div>
  )
}

function SectionHeader({
  title,
  count,
  viewAllTo,
}: {
  title: string
  count?: number
  viewAllTo?: string
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <h2
          style={{
            margin: 0,
            fontSize: size["2xl"],
            fontWeight: weight.bold,
            color: color.text.primary,
          }}
        >
          {title}
        </h2>
        {count !== undefined && (
          <span
            style={{
              fontSize: size.xs,
              background: color.surface.muted,
              color: color.text.secondary,
              borderRadius: radius["2xl"],
              padding: "2px 8px",
              fontWeight: weight.medium,
            }}
          >
            {count.toLocaleString()}
          </span>
        )}
      </div>
      {viewAllTo && (
        <Link
          to={viewAllTo}
          style={{
            ...linkReset,
            fontSize: size.sm,
            color: color.brand.base,
            fontWeight: weight.medium,
            background: "none",
            border: "none",
            cursor: "pointer",
          }}
        >
          View all →
        </Link>
      )}
    </div>
  )
}
