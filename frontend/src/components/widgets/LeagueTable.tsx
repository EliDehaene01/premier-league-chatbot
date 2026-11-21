import type { TableRow } from "@/lib/types"
import { cn } from "@/lib/utils"
import { WidgetCard } from "./WidgetCard"

// Zones for 2026-27: top 4 Champions League (5th can qualify too), bottom 3 relegated.
function zone(pos: number, total: number): string {
  if (pos <= 4) return "border-l-primary"
  if (pos > total - 3) return "border-l-destructive"
  return "border-l-transparent"
}

export function LeagueTable({ data }: { data: { after_matchweek: number; table: TableRow[] } }) {
  const rows = data.table
  return (
    <WidgetCard title="Premier League table" meta={`After matchweek ${data.after_matchweek}`}>
      <table className="w-full text-xs tabular-nums">
        <thead className="text-muted-foreground">
          <tr className="[&>th]:px-2 [&>th]:py-1.5 [&>th]:font-medium">
            <th className="text-left">#</th>
            <th className="text-left">Club</th>
            <th>P</th>
            <th>W</th>
            <th>D</th>
            <th>L</th>
            <th className="hidden sm:table-cell">GF</th>
            <th className="hidden sm:table-cell">GA</th>
            <th>GD</th>
            <th>Pts</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.club} className={cn("border-t border-l-2 text-center [&>td]:px-2 [&>td]:py-1.5", zone(r.position, rows.length))}>
              <td className="text-left text-muted-foreground">{r.position}</td>
              <td className="text-left font-medium whitespace-nowrap">{r.club}</td>
              <td>{r.played}</td>
              <td>{r.won}</td>
              <td>{r.drawn}</td>
              <td>{r.lost}</td>
              <td className="hidden sm:table-cell">{r.goals_for}</td>
              <td className="hidden sm:table-cell">{r.goals_against}</td>
              <td>{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</td>
              <td className="font-bold">{r.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </WidgetCard>
  )
}
