import type { Widget } from "@/lib/types"
import { LeagueTable } from "./LeagueTable"
import { Leaders } from "./Leaders"
import { Lineup } from "./Lineup"
import { MatchList } from "./MatchList"
import { PlayerCard } from "./PlayerCard"

export function WidgetView({ widget }: { widget: Widget }) {
  switch (widget.type) {
    case "table":
      return <LeagueTable data={widget.data} />
    case "matches":
      return <MatchList data={widget.data} />
    case "lineup":
      return <Lineup data={widget.data} />
    case "player":
      return <PlayerCard data={widget.data} />
    case "leaders":
      return <Leaders data={widget.data} />
    default:
      return null
  }
}
