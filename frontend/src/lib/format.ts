const TOOL_LABELS: Record<string, string> = {
  get_league_table: "Checking the league table",
  get_fixtures: "Looking up fixtures",
  get_results: "Looking up results",
  get_match_details: "Reading the match report data",
  get_match_lineup: "Fetching the line-ups",
  get_top_scorers: "Checking the leaderboard",
  get_player_stats: "Looking up player stats",
  compare_players: "Comparing players",
  get_club_info: "Looking up the club",
  get_head_to_head: "Checking head to head",
  search_news: "Searching Premier League news",
}

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ")
}

export function formatKickoff(iso?: string): string {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function formatDate(iso?: string | null): string {
  if (!iso) return ""
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
}

export function statLabel(key: string): string {
  return key
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .replace(/\bInc\b/, "incl.")
    .toLowerCase()
    .replace(/^./, (c) => c.toUpperCase())
}
