import type { Health } from "@/lib/types"
import { formatDate } from "@/lib/format"
import { cn } from "@/lib/utils"

const DOT = { ok: "bg-emerald-500", degraded: "bg-amber-500", down: "bg-red-500" }

export function HealthBadge({ health }: { health: Health | null }) {
  if (!health) return null
  const parts = [
    health.table_after_matchweek ? `Table after MW${health.table_after_matchweek}` : null,
    health.latest_article ? `news to ${formatDate(health.latest_article)}` : null,
  ].filter(Boolean)
  const label = health.status === "down" ? "API offline" : parts.join(", ") || "Connected"
  const problems = (health.checks ?? []).filter((c) => c.status !== "ok")
  const title = [`Data status: ${health.status}`, ...problems.map((c) => `${c.name}: ${c.detail}`)]
  return (
    <span
      className="flex items-center gap-2 text-xs text-muted-foreground"
      title={title.join("\n")}
    >
      <span className={cn("size-2 rounded-full", DOT[health.status])} aria-hidden="true" />
      <span className="hidden sm:inline">{label}</span>
    </span>
  )
}
