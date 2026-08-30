import { useMemo, useState } from "react"
import { Link, useNavigate } from "react-router"
import {
  actionTone,
  adminStatusTone,
  bareInput,
  color,
  linkReset,
  pillTone,
  radius,
  size,
  tracking,
  weight,
} from "@/design-system"
import { StatusPill } from "@/components/ui/AdminForm"
import { useToast } from "@/stores/useToastStore"
import {
  useAdminJobs,
  useSuggest,
  useDeleteJob,
  useExpireJob,
  useFeatureJob,
  useImportUsajobs,
  usePublishDraftJobs,
  usePublishJob,
  usePurgeExpiredJobs,
  useVerifyJob,
} from "@/hooks/queries"
import { describeError } from "@/lib/http"
import { ErrorPanel } from "@/components/QueryState"
import { toAdminRow } from "../adminRow"
import type { AdminJobRow } from "@/types/admin"
import Icon from "@/components/Icon"
import ShareJobModal from "@/components/ShareJobModal"
import SearchSuggest, { type SuggestChoice, useSuggestNavigation } from "@/components/SearchSuggest"

/**
 * Admin jobs table.
 *
 * Previously received thirteen loosely-typed props from the parent page. All of
 * that state is local to this table, so it owns it now and the `any` goes away.
 */
export default function JobsSection() {
  const showToast = useToast()
  const navigate = useNavigate()

  // The listing whose share sheet is open. Published only — the card
  // renderer refuses drafts, deliberately, so offering it earlier would hand
  // the editor a button that always fails.
  const [sharingJobId, setSharingJobId] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [suggestOpen, setSuggestOpen] = useState(false)
  // The admin variant: includes drafts and expired listings, and adds sources.
  const suggest = useSuggest(search, { admin: true })

  /** Every group narrows the table rather than navigating: an editor working
   *  the queue wants the list filtered, not to be thrown onto another screen.
   *  Jobs are the exception — picking a specific listing opens it for edit. */
  const applySuggestion = ({ group, item }: SuggestChoice) => {
    setSuggestOpen(false)
    setPage(1)
    if (group === "jobs" && item.slug) {
      const match = (data?.items ?? []).find(j => j.slug === item.slug)
      if (match) {
        navigate(`/admin/dashboard/add-job?edit=${match.id}`)
        return
      }
    }
    setSearch(item.text)
  }

  const nav = useSuggestNavigation(suggest.groups, {
    open: suggestOpen,
    onChoose: applySuggestion,
    onDismiss: () => setSuggestOpen(false),
  })
  const [statusFilter, setStatusFilter] = useState("All")

  const importJobs = useImportUsajobs()

  /**
   * One import run, reported plainly.
   *
   * A second press is expected to create nothing — everything already imported
   * is recognised and skipped — so the toast names both numbers rather than
   * letting "0 new" read as a failure.
   */
  const runImport = async () => {
    try {
      const run = await importJobs.mutateAsync()
      const parts = [`${run.created} new draft${run.created === 1 ? "" : "s"}`]
      if (run.skipped) parts.push(`${run.skipped} already imported`)
      if (run.failed) parts.push(`${run.failed} could not be read`)
      // Said out loud rather than left implicit: a run that stopped at the page
      // cap looks identical to one that saw everything.
      if (run.available > run.fetched) parts.push(`${run.available - run.fetched} more available`)
      showToast(parts.join(", "))
      if (run.created > 0) setStatusFilter("Draft")
    } catch (err) {
      showToast(describeError(err))
    }
  }
  const purgeExpired = usePurgeExpiredJobs()
  const publishDrafts = usePublishDraftJobs()

  /**
   * Which bulk action is armed, if any.
   *
   * Both are two-step. Neither acts on the rows in front of you — they act on
   * every expired or draft listing in the catalogue, including the hundreds on
   * pages nobody has looked at — so a single press is not consent. The armed
   * state is what puts the real number in front of the admin before it runs.
   */
  const [bulkArmed, setBulkArmed] = useState<null | "purge" | "publish">(null)

  /**
   * How many listings each button would touch.
   *
   * One row is fetched purely for its `total`; the table's own query is
   * filtered and paginated and cannot answer "how many drafts exist" from the
   * page it happens to be showing. Both are invalidated by every job write, so
   * the counts follow the actions rather than going stale behind them.
   */
  const expiredTotal = useAdminJobs({ page: 1, per_page: 1, status: "expired" }).data?.total ?? 0
  const draftTotal = useAdminJobs({ page: 1, per_page: 1, status: "draft" }).data?.total ?? 0

  /**
   * Permanently deletes every expired listing.
   *
   * The toast names the remainder as well as the count, because the server caps
   * one call at 500 — and a run that stopped at the cap looks exactly like one
   * that finished.
   */
  const runPurgeExpired = async () => {
    setBulkArmed(null)
    try {
      const result = await purgeExpired.mutateAsync()
      const parts = [`${result.deleted} expired listing${result.deleted === 1 ? "" : "s"} deleted`]
      if (result.remaining) parts.push(`${result.remaining} left — press again to continue`)
      showToast(parts.join(", "))
    } catch (err) {
      showToast(describeError(err))
    }
  }

  const runPublishDrafts = async () => {
    setBulkArmed(null)
    try {
      const result = await publishDrafts.mutateAsync()
      const parts = [`${result.published} draft${result.published === 1 ? "" : "s"} published`]
      if (result.remaining) parts.push(`${result.remaining} left — press again to continue`)
      showToast(parts.join(", "))
      if (result.published > 0) setStatusFilter("Published")
    } catch (err) {
      showToast(describeError(err))
    }
  }

  const bulkBusy = purgeExpired.isPending || publishDrafts.isPending

  // Ids, not row indices. Indices are positions in a filtered, paginated view
  // that shifts under the selection the moment a mutation lands — selecting
  // row 3 and then expiring it would apply the next action to whatever slid
  // into that position.
  const [selected, setSelected] = useState<string[]>([])
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  //: The server page size, not a slice of an already-loaded array. It used to
  //: be the latter, which quietly capped the whole table at one request's
  //: worth of rows.
  const perPage = 25

  const STATUS_TO_API: Record<string, string | undefined> = {
    Published: "published",
    Draft: "draft",
    Expired: "expired",
    // Not lifecycle states: `featured` and `verified` are boolean columns and
    // `expiring` is derived from the expiry date. They filter client-side over
    // the loaded page rather than pretending to be a status the API knows.
    Featured: undefined,
    Verified: undefined,
    Expiring: undefined,
  }


  // The editorial view: drafts, scheduled and archived listings alongside
  // published ones. Requires JOB_VIEW_ALL, which the router enforces.
  const { data, isPending, isError, error, refetch } = useAdminJobs({
    page,
    per_page: perPage,
    status: statusFilter === "All" ? undefined : STATUS_TO_API[statusFilter],
  })

  const publish = usePublishJob()
  const expire = useExpireJob()
  const verify = useVerifyJob()
  const feature = useFeatureJob()
  const remove = useDeleteJob()

  const jobsById = useMemo(
    () => new Map((data?.items ?? []).map((job) => [job.id, job])),
    [data],
  )
  const rows = useMemo(() => (data?.items ?? []).map(toAdminRow), [data])

  /**
   * Runs a mutation and reports what actually happened.
   *
   * Every toast in this table is now downstream of a resolved promise. The
   * previous ones fired on click and said "applied" whether or not anything
   * had been.
   */
  async function run(id: string, label: string, action: () => Promise<unknown>) {
    setBusy(id)
    try {
      await action()
      showToast(`${label} — saved`)
    } catch (err) {
      showToast(describeError(err))
    } finally {
      setBusy(null)
    }
  }

  /**
   * Refinements the API cannot express.
   *
   * `Published`/`Draft`/`Expired` are sent to the server, so re-applying them
   * here would be a second, weaker filter over one page. What is left is the
   * search box and the three pills that are not lifecycle states — and those
   * can only narrow the page in front of you, which the footer says out loud
   * rather than letting the counts look wrong.
   */
  const localOnly =
    search.trim().length > 0 || ["Featured", "Verified", "Expiring"].includes(statusFilter)

  const jobs = useMemo(() => {
    const term = search.trim().toLowerCase()
    return rows.filter((j) => {
      const matchSearch =
        !term ||
        j.title.toLowerCase().includes(term) ||
        j.company.toLowerCase().includes(term)
      const matchPill =
        statusFilter !== "Featured" && statusFilter !== "Verified"
          ? true
          : statusFilter === "Featured"
            ? jobsById.get(j.id)?.featured === true
            : jobsById.get(j.id)?.verified === true
      return matchSearch && matchPill
    })
  }, [rows, search, statusFilter, jobsById])

  const total = data?.total ?? 0
  const totalPages = data?.totalPages ?? 1
  const firstOnPage = total === 0 ? 0 : (page - 1) * perPage + 1
  const lastOnPage = Math.min(page * perPage, total)
  const paginated = jobs
  const setSection = (section: string) =>
    navigate(`/admin/dashboard/${section}`)

  /**
   * Applies an action to every selected listing and reports the real tally.
   *
   * Sequential rather than parallel: these are audited writes against rows an
   * operator is watching, and forty concurrent PATCHes would give the database
   * a burst for no benefit a person could perceive. Failures are counted
   * rather than aborting — one listing in an illegal state should not stop the
   * other nine from being processed.
   */
  async function runBulk(
    label: string,
    ids: string[],
    action: (id: string) => Promise<unknown>,
  ) {
    let ok = 0
    const failures: string[] = []
    for (const id of ids) {
      try {
        await action(id)
        ok++
      } catch (err) {
        failures.push(describeError(err))
      }
    }
    setSelected([])
    showToast(
      failures.length === 0
        ? `${label}d ${ok} job${ok === 1 ? "" : "s"}`
        : `${label}d ${ok} of ${ids.length} — ${failures[0]}`,
    )
  }

  const STATUS_FILTERS = [
    "All",
    "Published",
    "Featured",
    "Verified",
    "Draft",
    "Expiring",
    "Expired",
  ]
  const allSelected =
    paginated.length > 0 && paginated.every((row) => selected.includes(row.id))

  const toggleAll = () =>
    setSelected(allSelected ? [] : paginated.map((row) => row.id))

  if (isError) {
    return (
      <ErrorPanel
        message={describeError(error)}
        onRetry={() => void refetch()}
      />
    )
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ flex: 1, minWidth: 200, position: "relative" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            border: `1px solid ${color.border.base}`,
            borderRadius: radius.xl,
            padding: "8px 14px",
            background: color.surface.base,
          }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke={color.text.muted}
            strokeWidth="2"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              // The search reads the loaded page, so start from the first one.
              setPage(1)
              setSuggestOpen(true)
            }}
            onFocus={() => setSuggestOpen(true)}
            onKeyDown={(e) => {
              nav.onKeyDown(e)
              if (e.key === "Enter" && !e.defaultPrevented) setSuggestOpen(false)
            }}
            role="combobox"
            aria-expanded={suggestOpen}
            aria-autocomplete="list"
            placeholder="Search jobs, companies, locations, sources…"
            style={bareInput(size.sm, { width: "100%" })}
          />
        </div>
          <SearchSuggest
            query={search}
            groups={suggest.groups}
            choices={nav.choices}
            active={nav.active}
            onActiveChange={nav.setActive}
            open={suggestOpen && suggest.enabled}
            loading={suggest.isFetching}
            onChoose={applySuggestion}
            onDismiss={() => setSuggestOpen(false)}
            showBadges
          />
        </div>
        {selected.length > 0 && (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: size.sm, color: color.text.secondary }}>
              {selected.length} selected
            </span>
            {[
              {
                label: "Feature",
                color: color.warning.text,
                run: (id: string) => feature.mutateAsync({ id, featured: true }),
              },
              {
                label: "Verify",
                color: color.info.text,
                run: (id: string) => verify.mutateAsync({ id, verified: true }),
              },
              {
                label: "Expire",
                color: color.warning.base,
                run: (id: string) => expire.mutateAsync({ id }),
              },
              {
                label: "Delete",
                color: color.danger.base,
                run: (id: string) => remove.mutateAsync(id),
              },
            ].map((a) => (
              <button
                key={a.label}
                onClick={() => void runBulk(a.label, selected, a.run)}
                style={{
                  padding: "6px 12px",
                  border: `1px solid ${a.color}30`,
                  background: `${a.color}0A`,
                  borderRadius: radius.md,
                  fontSize: size.xs,
                  fontWeight: weight.medium,
                  color: a.color,
                  cursor: "pointer",
                }}
              >
                {a.label}
              </button>
            ))}
          </div>
        )}
        {/* Bulk actions. Disabled at zero rather than hidden — a greyed
            "Publish drafts (0)" answers "are there any drafts?" without the
            admin having to switch filters to find out. */}
        <button
          onClick={() => setBulkArmed(bulkArmed === "publish" ? null : "publish")}
          disabled={draftTotal === 0 || bulkBusy}
          title="Publish every draft listing. Expired listings are not touched."
          style={{
            padding: "8px 14px",
            background: bulkArmed === "publish" ? color.brand.tint : color.surface.base,
            border: `1px solid ${bulkArmed === "publish" ? color.brand.base : color.border.base}`,
            borderRadius: radius.xl,
            color: draftTotal === 0 ? color.text.muted : color.brand.base,
            fontSize: size.sm,
            fontWeight: weight.medium,
            cursor: draftTotal === 0 || bulkBusy ? "not-allowed" : "pointer",
            opacity: draftTotal === 0 ? 0.55 : 1,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Icon name="check" size={14} />
          {publishDrafts.isPending ? "Publishing…" : `Publish drafts (${draftTotal})`}
        </button>
        <button
          onClick={() => setBulkArmed(bulkArmed === "purge" ? null : "purge")}
          disabled={expiredTotal === 0 || bulkBusy}
          title="Permanently delete every expired listing. This cannot be undone."
          style={{
            padding: "8px 14px",
            background: bulkArmed === "purge" ? color.danger.tint : color.surface.base,
            border: `1px solid ${bulkArmed === "purge" ? color.danger.base : color.border.base}`,
            borderRadius: radius.xl,
            color: expiredTotal === 0 ? color.text.muted : color.danger.text,
            fontSize: size.sm,
            fontWeight: weight.medium,
            cursor: expiredTotal === 0 || bulkBusy ? "not-allowed" : "pointer",
            opacity: expiredTotal === 0 ? 0.55 : 1,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Icon name="close" size={14} />
          {purgeExpired.isPending ? "Deleting…" : `Delete expired (${expiredTotal})`}
        </button>
        <button
          onClick={() => void runImport()}
          disabled={importJobs.isPending}
          title="Pull open federal listings from USAJOBS. They arrive as drafts for you to review."
          style={{
            padding: "8px 16px",
            background: color.surface.base,
            border: `1px solid ${color.border.base}`,
            borderRadius: radius.xl,
            color: color.text.primary,
            fontSize: size.sm,
            fontWeight: weight.medium,
            cursor: importJobs.isPending ? "wait" : "pointer",
            opacity: importJobs.isPending ? 0.6 : 1,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Icon name="download" size={14} />
          {importJobs.isPending ? "Fetching…" : "Fetch jobs"}
        </button>
        <button
          onClick={() => setSection("add-job")}
          style={{
            padding: "8px 16px",
            background: color.brand.base,
            border: "none",
            borderRadius: radius.xl,
            color: color.surface.base,
            fontSize: size.sm,
            fontWeight: weight.medium,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Add Job
        </button>
      </div>

      {/* Armed bulk action.
          Deliberately a banner rather than a browser `confirm()`: it has to
          state the count, say what is and is not reversible, and survive being
          read twice. The purge wording leads with the consequence, because
          "are you sure?" is the one question everybody answers yes to. */}
      {bulkArmed && (
        <div
          role="alertdialog"
          aria-label={bulkArmed === "purge" ? "Confirm permanent deletion" : "Confirm publish"}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            padding: "12px 16px",
            borderRadius: radius["3xl"],
            border: `1px solid ${bulkArmed === "purge" ? color.danger.border : color.border.base}`,
            background: bulkArmed === "purge" ? color.danger.tint : color.surface.muted,
          }}
        >
          <span style={{ fontSize: size.sm, color: color.text.primary, flex: 1, minWidth: 260 }}>
            {bulkArmed === "purge" ? (
              <>
                <strong>Permanently delete {expiredTotal} expired listing
                {expiredTotal === 1 ? "" : "s"}.</strong>{" "}
                The rows are removed from the database, along with any reports filed
                against them and their per-job analytics. This cannot be undone.
                {expiredTotal > 500 && " Up to 500 are removed per press."}
              </>
            ) : (
              <>
                <strong>Publish {draftTotal} draft{draftTotal === 1 ? "" : "s"}.</strong>{" "}
                They go live on the site immediately. Expired listings are not affected,
                and anything published here can be moved back to draft.
                {draftTotal > 500 && " Up to 500 are published per press."}
              </>
            )}
          </span>
          <button
            onClick={() => void (bulkArmed === "purge" ? runPurgeExpired() : runPublishDrafts())}
            style={{
              padding: "7px 16px",
              border: "none",
              borderRadius: radius.md,
              background: bulkArmed === "purge" ? color.danger.base : color.brand.base,
              color: color.surface.base,
              fontSize: size.sm,
              fontWeight: weight.medium,
              cursor: "pointer",
            }}
          >
            {bulkArmed === "purge" ? `Delete ${expiredTotal} permanently` : `Publish ${draftTotal}`}
          </button>
          <button
            onClick={() => setBulkArmed(null)}
            style={{
              padding: "7px 14px",
              border: `1px solid ${color.border.base}`,
              borderRadius: radius.md,
              background: color.surface.base,
              color: color.text.secondary,
              fontSize: size.sm,
              fontWeight: weight.medium,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Status filter pills */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => {
              setStatusFilter(f)
              // Page 9 of the drafts is not page 9 of anything else.
              setPage(1)
            }}
            style={{
              padding: "5px 14px",
              ...pillTone(statusFilter === f),
              borderRadius: radius.pill,
              fontSize: size.xs,
              fontWeight: statusFilter === f ? weight.semibold : weight.regular,
              cursor: "pointer",
            }}
          >
            {f}
          </button>
        ))}
        <span
          style={{
            marginLeft: "auto",
            fontSize: size.xs,
            color: color.text.muted,
            alignSelf: "center",
          }}
        >
          {isPending
            ? "Loading…"
            : localOnly
              ? `${jobs.length} on this page`
              : `${total} result${total === 1 ? "" : "s"}`}
        </span>
      </div>

      {/* Table */}
      <div
        style={{
          background: color.surface.base,
          border: `1px solid ${color.border.base}`,
          borderRadius: radius["3xl"],
          overflow: "hidden",
        }}
      >
        <div style={{ overflowX: "auto" }}>
          <table
            style={{ width: "100%", borderCollapse: "collapse", minWidth: 900 }}
          >
            <thead>
              <tr style={{ background: color.surface.subtle }}>
                <th style={{ padding: "10px 16px", width: 36 }}>
                  <div
                    onClick={toggleAll}
                    style={{
                      width: 16,
                      height: 16,
                      borderRadius: radius.sm,
                      border: `2px solid ${
                        allSelected ? color.brand.base : color.text.disabled
                      }`,
                      background: allSelected
                        ? color.brand.base
                        : color.surface.base,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {allSelected && (
                      <svg
                        width="10"
                        height="10"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke={color.surface.base}
                        strokeWidth="3"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </div>
                </th>
                {[
                  "Job Title",
                  "Category",
                  "Location",
                  "Status",
                  "Published",
                  "Expiry",
                  "Clicks",
                  "Views",
                  "Actions",
                ].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "10px 12px",
                      textAlign: "left",
                      fontSize: size["2xs"],
                      fontWeight: weight.semibold,
                      color: color.text.muted,
                      textTransform: "uppercase",
                      letterSpacing: tracking.wide,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paginated.map((j: AdminJobRow) => {
                const isSelected = selected.includes(j.id)
                const isBusy = busy === j.id
                return (
                  <tr
                    key={j.id}
                    style={{
                      borderTop: `1px solid ${color.surface.muted}`,
                      background: isSelected ? color.brand.tint : "none",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected)
                        e.currentTarget.style.background = color.surface.hover
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.background = "none"
                    }}
                  >
                    <td style={{ padding: "12px 16px" }}>
                      <div
                        onClick={() =>
                          setSelected((prev) =>
                            isSelected
                              ? prev.filter((x) => x !== j.id)
                              : [...prev, j.id],
                          )
                        }
                        style={{
                          width: 16,
                          height: 16,
                          borderRadius: radius.sm,
                          border: `2px solid ${
                            isSelected ? color.brand.base : color.text.disabled
                          }`,
                          background: isSelected
                            ? color.brand.base
                            : color.surface.base,
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        {isSelected && (
                          <svg
                            width="10"
                            height="10"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke={color.surface.base}
                            strokeWidth="3"
                          >
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: "12px 12px" }}>
                      <div
                        style={{
                          fontSize: size.sm,
                          fontWeight: weight.semibold,
                          color: color.text.primary,
                        }}
                      >
                        {j.title}
                      </div>
                      <div
                        style={{
                          fontSize: size["2xs"],
                          color: color.text.muted,
                        }}
                      >
                        {j.company}
                      </div>
                    </td>
                    <td
                      style={{
                        padding: "12px 12px",
                        fontSize: size.xs,
                        color: color.text.secondary,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {j.category}
                    </td>
                    <td
                      style={{
                        padding: "12px 12px",
                        fontSize: size.xs,
                        color: color.text.secondary,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {j.location}
                    </td>
                    <td style={{ padding: "12px 12px" }}>
                      <StatusPill status={j.status} />
                    </td>
                    <td
                      style={{
                        padding: "12px 12px",
                        fontSize: size.xs,
                        color: color.text.secondary,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {j.published}
                    </td>
                    <td
                      style={{
                        padding: "12px 12px",
                        fontSize: size.xs,
                        color:
                          j.expiry !== "—" &&
                          new Date(j.expiry) < new Date("2026-08-20")
                            ? color.danger.base
                            : color.text.secondary,
                        whiteSpace: "nowrap",
                        fontWeight:
                          j.expiry !== "—" &&
                          new Date(j.expiry) < new Date("2026-08-20")
                            ? weight.semibold
                            : weight.regular,
                      }}
                    >
                      {j.expiry}
                    </td>
                    <td
                      style={{
                        padding: "12px 12px",
                        fontSize: size.sm,
                        fontWeight: weight.bold,
                        color: color.brand.base,
                      }}
                    >
                      {j.clicks}
                    </td>
                    <td
                      style={{
                        padding: "12px 12px",
                        fontSize: size.sm,
                        color: color.text.strong,
                      }}
                    >
                      {j.views.toLocaleString()}
                    </td>
                    <td style={{ padding: "12px 12px" }}>
                      {deleteConfirm === j.id ? (
                        <div style={{ display: "flex", gap: 6 }}>
                          <button
                            onClick={() => {
                              setDeleteConfirm(null)
                              void run(j.id, "Deleted", () => remove.mutateAsync(j.id))
                            }}
                            style={{
                              fontSize: size["2xs"],
                              padding: "4px 8px",
                              border: `1px solid ${color.danger.base}`,
                              background: color.danger.tint,
                              color: color.danger.base,
                              borderRadius: radius.smd,
                              cursor: "pointer",
                              fontWeight: weight.semibold,
                            }}
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(null)}
                            style={{
                              fontSize: size["2xs"],
                              padding: "4px 8px",
                              border: `1px solid ${color.border.base}`,
                              background: color.surface.base,
                              color: color.text.secondary,
                              borderRadius: radius.smd,
                              cursor: "pointer",
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <div style={{ display: "flex", gap: 4 }}>
                          {[
                            {
                              icon: "pen" as const,
                              title: "Edit",
                              run: () => navigate(`/admin/dashboard/add-job?edit=${j.id}`),
                            },
                            {
                              icon: "star" as const,
                              title: jobsById.get(j.id)?.featured ? "Unfeature" : "Feature",
                              run: () =>
                                run(j.id, "Feature", () =>
                                  feature.mutateAsync({
                                    id: j.id,
                                    featured: !jobsById.get(j.id)?.featured,
                                  }),
                                ),
                            },
                            {
                              icon: "check" as const,
                              title: jobsById.get(j.id)?.verified ? "Unverify" : "Verify",
                              run: () =>
                                run(j.id, "Verify", () =>
                                  verify.mutateAsync({
                                    id: j.id,
                                    verified: !jobsById.get(j.id)?.verified,
                                  }),
                                ),
                            },
                            ...(j.status === "published"
                              ? [
                                  {
                                    icon: "link" as const,
                                    title: "Share",
                                    run: async () => setSharingJobId(j.id),
                                  },
                                  {
                                    icon: "clock" as const,
                                    title: "Expire",
                                    run: () =>
                                      run(j.id, "Expire", () =>
                                        expire.mutateAsync({ id: j.id }),
                                      ),
                                  },
                                ]
                              : [
                                  {
                                    icon: "upload" as const,
                                    title: "Publish",
                                    run: () =>
                                      run(j.id, "Publish", () =>
                                        publish.mutateAsync({ id: j.id }),
                                      ),
                                  },
                                ]),
                          ].map((a) => (
                            <button
                              key={a.title}
                              title={a.title}
                              disabled={isBusy}
                              onClick={a.run}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                padding: "5px 7px",
                                border: `1px solid ${color.border.base}`,
                                background: color.surface.base,
                                color: color.text.secondary,
                                borderRadius: radius.smd,
                                cursor: "pointer",
                              }}
                            >
                              <Icon name={a.icon} size={13} />
                            </button>
                          ))}
                          <button
                            title="Delete"
                            onClick={() => setDeleteConfirm(j.id)}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              padding: "5px 7px",
                              border: `1px solid ${color.danger.border}`,
                              background: color.danger.tint,
                              color: color.danger.base,
                              borderRadius: radius.smd,
                              cursor: "pointer",
                            }}
                          >
                            <Icon name="close" size={13} />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div
          style={{
            padding: "12px 20px",
            borderTop: `1px solid ${color.surface.muted}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span style={{ fontSize: size.xs, color: color.text.muted }}>
            {total === 0
              ? "No listings"
              : `Showing ${firstOnPage}–${lastOnPage} of ${total}`}
            {localOnly && ` · ${jobs.length} match this page`}
          </span>
          {totalPages > 1 && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: size.xs, color: color.text.muted }}>
                Page {page} of {totalPages}
              </span>
              {[
                { label: "Previous", to: page - 1, off: page <= 1 },
                { label: "Next", to: page + 1, off: page >= totalPages },
              ].map((control) => (
                <button
                  key={control.label}
                  onClick={() => setPage(control.to)}
                  disabled={control.off}
                  style={{
                    fontSize: size.sm,
                    padding: "6px 16px",
                    border: `1px solid ${color.border.base}`,
                    borderRadius: radius.lg,
                    background: color.surface.base,
                    color: control.off ? color.text.muted : color.text.strong,
                    cursor: control.off ? "not-allowed" : "pointer",
                    opacity: control.off ? 0.5 : 1,
                    fontWeight: weight.medium,
                  }}
                >
                  {control.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <ShareJobModal jobId={sharingJobId} onClose={() => setSharingJobId(null)} />
    </div>
  )
}
