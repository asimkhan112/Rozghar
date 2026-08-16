import { Link } from "react-router"
import Navbar from "../components/Navbar"
import JobCard from "../components/JobCard"
import {
  color,
  linkReset,
  radius,
  size,
  tracking,
  weight,
} from "@/design-system"
import { useSavedIds } from "@/stores/useSavedJobsStore"
import { useJobsByIds } from "@/hooks/queries"
import { describeError } from "@/lib/http"
import { ErrorPanel, JobGridSkeleton } from "@/components/QueryState"

export default function SavedJobsPage() {
  const savedIds = useSavedIds()
  // Disabled when nothing is saved, so the empty state renders immediately
  // rather than after a round trip whose answer is already known.
  const { data, isPending, isError, error, refetch } = useJobsByIds(savedIds)

  // A saved listing that has since expired or been removed simply stops coming
  // back from the API. Reconciling the stored ids against what actually
  // resolved keeps the count honest instead of promising jobs that are gone.
  const saved = data?.items ?? []
  const loading = savedIds.length > 0 && isPending

  return (
    <div style={{ minHeight: "100vh", background: color.surface.canvas }}>
      <Navbar />
      <div
        style={{ maxWidth: 900, margin: "0 auto", padding: "40px 24px 80px" }}
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
            Saved Jobs
          </h1>
          <p
            style={{
              fontSize: size.base,
              color: color.text.secondary,
              margin: 0,
            }}
          >
            {loading
              ? "Loading your saved jobs…"
              : saved.length === 0
                ? "You haven't saved any jobs yet"
                : `${saved.length} job${saved.length === 1 ? "" : "s"} saved`}
          </p>
        </div>

        {loading ? (
          <JobGridSkeleton count={3} />
        ) : isError ? (
          <ErrorPanel
            message={describeError(error)}
            onRetry={() => void refetch()}
          />
        ) : saved.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "80px 24px",
              background: color.surface.base,
              border: `1px solid ${color.border.base}`,
              borderRadius: radius["5xl"],
            }}
          >
            <div style={{ fontSize: size["8xl"], marginBottom: 16 }}>🔖</div>
            <h3
              style={{
                fontSize: size["3xl"],
                fontWeight: weight.bold,
                color: color.text.primary,
                margin: "0 0 8px",
              }}
            >
              No saved jobs yet
            </h3>
            <p
              style={{
                fontSize: size.md,
                color: color.text.secondary,
                margin: "0 0 24px",
                maxWidth: 320,
                marginInline: "auto",
              }}
            >
              Tap the bookmark icon on any job card to save it here for later.
            </p>
            <Link
              to="/jobs"
              style={{
                ...linkReset,
                display: "inline-block",
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
              Browse Jobs
            </Link>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {saved.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
