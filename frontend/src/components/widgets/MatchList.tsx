import type { MatchRow } from "@/lib/types"
import { formatKickoff } from "@/lib/format"
import { WidgetCard } from "./WidgetCard"

export function hasScore(m: MatchRow): boolean {
  return m.home_score != null && m.away_score != null && m.period !== "PreMatch"
}

export function MatchList({ data }: { data: { title: string; matches: MatchRow[] } }) {
  return (
    <WidgetCard title={data.title} meta="Kick-offs in your local time">
      <ul className="divide-y text-sm">
        {data.matches.map((m) => (
          <li key={m.match_id}>
            <a
              href={`https://www.premierleague.com/en/match/${m.match_id}`}
              target="_blank"
              rel="noreferrer"
              className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-3 py-2 hover:bg-secondary"
            >
              <span className="truncate text-right font-medium">{m.home_club}</span>
              <span className="min-w-14 rounded-md bg-secondary px-2 py-0.5 text-center text-xs font-semibold tabular-nums">
                {hasScore(m) ? `${m.home_score} - ${m.away_score}` : "v"}
              </span>
              <span className="truncate font-medium">{m.away_club}</span>
              <span className="col-span-3 -mt-1 text-center text-[11px] text-muted-foreground">
                {[m.matchweek ? `MW${m.matchweek}` : null, formatKickoff(m.kickoff_utc), m.ground]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </WidgetCard>
  )
}
