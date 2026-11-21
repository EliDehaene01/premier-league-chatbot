import { formatDate, statLabel } from "@/lib/format"
import { WidgetCard } from "./WidgetCard"

export function Leaders({
  data,
}: {
  data: { stat: string; as_of?: string; players: Array<Record<string, string | number>> }
}) {
  return (
    <WidgetCard title={`Top ${statLabel(data.stat).toLowerCase()}`} meta={data.as_of ? `As of ${formatDate(data.as_of)}` : undefined}>
      <ol className="divide-y text-sm">
        {data.players.map((p) => (
          <li key={`${p.rank}-${p.player_name}`} className="flex items-center gap-3 px-3 py-1.5">
            <span className="w-5 text-xs text-muted-foreground tabular-nums">{p.rank}</span>
            <span className="min-w-0 flex-1 truncate">
              <span className="font-medium">{p.player_name}</span>{" "}
              <span className="text-xs text-muted-foreground">{p.club}</span>
            </span>
            <span className="font-bold tabular-nums">{p[data.stat]}</span>
          </li>
        ))}
      </ol>
    </WidgetCard>
  )
}
