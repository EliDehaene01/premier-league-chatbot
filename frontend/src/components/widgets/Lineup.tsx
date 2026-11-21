import { useState } from "react"
import type { LineupPlayer, LineupTeam, MatchRow } from "@/lib/types"
import { cn } from "@/lib/utils"
import { hasScore } from "./MatchList"
import { WidgetCard } from "./WidgetCard"

/** Starters grouped by formation row, goalkeeper (row 1) first. Players without a row go last. */
export function formationRows(starters: LineupPlayer[]): LineupPlayer[][] {
  const rows = new Map<number, LineupPlayer[]>()
  for (const p of starters) {
    const r = p.row ?? 99
    rows.set(r, [...(rows.get(r) ?? []), p])
  }
  return [...rows.entries()].sort(([a], [b]) => a - b).map(([, ps]) => ps)
}

function surname(name: string): string {
  const parts = name.split(" ")
  return parts.length > 1 ? parts.slice(1).join(" ") : name
}

function Marks({ p }: { p: LineupPlayer }) {
  const marks = [
    ...(p.goals ?? []).map(() => "⚽"),
    ...(p.cards ?? []).map((c) => (/red/i.test(c) ? "🟥" : "🟨")),
  ]
  return marks.length ? <span className="text-[9px] leading-none">{marks.join("")}</span> : null
}

function Pitch({ team }: { team: LineupTeam }) {
  // attack at the top, goalkeeper at the bottom
  const rows = formationRows(team.starting_xi_gk_to_attack).reverse()
  return (
    <div
      className="relative mx-3 my-3 flex aspect-[3/4] max-h-[26rem] flex-col justify-around rounded-lg border-2 border-pitch-line bg-pitch py-2 sm:mx-auto sm:w-80"
      role="list"
      aria-label={`${team.club} starting eleven`}
    >
      <div className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-pitch-line/60" />
      <div className="pointer-events-none absolute inset-x-1/4 bottom-0 h-[14%] border-x border-t border-pitch-line/60" />
      {rows.map((row, i) => (
        <div key={i} className="relative flex justify-around px-1">
          {row.map((p) => (
            <div key={p.name} role="listitem" className="flex w-16 flex-col items-center gap-0.5 text-center">
              <span
                className={cn(
                  "grid size-7 place-items-center rounded-full bg-white text-[11px] font-bold text-neutral-900 shadow",
                  p.row === 1 && "bg-amber-300",
                )}
              >
                {p.shirt ?? ""}
              </span>
              <span className="w-full truncate text-[10px] leading-tight font-medium text-white drop-shadow">
                {surname(p.name)}
                {p.captain ? " (C)" : ""}
              </span>
              <Marks p={p} />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export function Lineup({ data }: { data: { match: MatchRow; teams: LineupTeam[] } }) {
  const [active, setActive] = useState(0)
  const team = data.teams[active]
  const m = data.match
  const title = `${m.home_club} ${hasScore(m) ? `${m.home_score}-${m.away_score}` : "v"} ${m.away_club}`
  if (!team) return null
  return (
    <WidgetCard title="Line-ups" meta={title}>
      <div className="flex gap-1 border-b px-3 py-2" role="tablist">
        {data.teams.map((t, i) => (
          <button
            key={t.club}
            role="tab"
            aria-selected={i === active}
            onClick={() => setActive(i)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium",
              i === active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary",
            )}
          >
            {t.club}
            {t.formation ? ` · ${t.formation}` : ""}
          </button>
        ))}
      </div>
      <Pitch team={team} />
      <div className="border-t px-3 py-2 text-xs text-muted-foreground">
        {team.manager && <p>Manager: {team.manager}</p>}
        {team.substitutes.length > 0 && (
          <p className="mt-1">
            Subs:{" "}
            {team.substitutes
              .map((s) => `${s.name}${s.came_on ? ` (on ${s.came_on}')` : ""}`)
              .join(", ")}
          </p>
        )}
      </div>
    </WidgetCard>
  )
}
