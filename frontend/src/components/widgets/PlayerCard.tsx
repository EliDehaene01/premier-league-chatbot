import { statLabel, formatDate } from "@/lib/format"
import { WidgetCard } from "./WidgetCard"

const ORDER = ["appearances", "starts", "minutes", "goals", "assists", "clean_sheets", "yellow_cards", "red_cards"]

export function PlayerCard({
  data,
}: {
  data: { player: string; club?: string; position?: string; as_of?: string; season_stats: Record<string, unknown> | null }
}) {
  const stats = data.season_stats ?? {}
  const shown = ORDER.filter((k) => typeof stats[k] === "number")
  return (
    <WidgetCard
      title={data.player}
      meta={[data.club, data.position].filter(Boolean).join(" · ")}
    >
      {shown.length ? (
        <dl className="grid grid-cols-4 gap-px bg-border text-center">
          {shown.map((k) => (
            <div key={k} className="bg-card px-2 py-2">
              <dt className="text-[10px] text-muted-foreground">{statLabel(k)}</dt>
              <dd className="text-base font-bold tabular-nums">{String(stats[k])}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="px-3 py-2 text-xs text-muted-foreground">No league minutes yet this season.</p>
      )}
      {data.as_of && <p className="px-3 py-1.5 text-[11px] text-muted-foreground">As of {formatDate(data.as_of)}</p>}
    </WidgetCard>
  )
}
