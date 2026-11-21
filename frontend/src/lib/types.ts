// Shapes sent by backend/api/main.py. Keep in step with ARCHITECTURE.md (API).

export type Role = "user" | "assistant"

export interface Source {
  n: number
  id: string
  kind: "article" | "match" | "table" | "club"
  title: string
  date: string | null
  url: string
}

export interface ToolStatus {
  name: string
  status: "started" | "finished"
  error?: string
}

export interface MatchRow {
  match_id: number
  matchweek?: number
  kickoff_utc?: string
  home_club: string
  away_club: string
  home_score?: number
  away_score?: number
  period?: string
  ground?: string
}

export interface TableRow {
  position: number
  club: string
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  goal_difference: number
  points: number
}

export interface LineupPlayer {
  name: string
  shirt?: number | string
  position?: string
  captain?: boolean
  row?: number
  goals?: string[]
  assists?: string[]
  cards?: string[]
  came_on?: number | string
  went_off?: number | string
}

export interface LineupTeam {
  club: string
  formation?: string
  manager?: string
  starting_xi_gk_to_attack: LineupPlayer[]
  substitutes: LineupPlayer[]
}

export type Widget =
  | { type: "table"; data: { after_matchweek: number; table: TableRow[] } }
  | { type: "matches"; data: { title: string; matches: MatchRow[] } }
  | { type: "lineup"; data: { match: MatchRow; teams: LineupTeam[] } }
  | {
      type: "player"
      data: {
        player: string
        club?: string
        position?: string
        as_of?: string
        season_stats: Record<string, number> | null
      }
    }
  | {
      type: "leaders"
      data: { stat: string; as_of?: string; players: Array<Record<string, string | number>> }
    }

export interface Usage {
  prompt_tokens?: number
  completion_tokens?: number
  cost_usd?: number | null
  latency_ms?: number
}

export interface ChatMessage {
  id: string
  role: Role
  content: string
  turnId?: string
  sources?: Source[]
  widgets?: Widget[]
  tools?: ToolStatus[]
  usage?: Usage
  pending?: boolean
  error?: string
}

export interface Health {
  status: "ok" | "degraded" | "down"
  db: boolean
  latest_article?: string | null
  latest_finished_match?: string | null
  table_after_matchweek?: number | null
  indexed_chunks?: number
  checks?: { name: string; status: "ok" | "warn" | "fail"; detail: string }[]
}

export interface DigestItem {
  text: string
  sources: string[]
  cites?: number[]
}

export interface Digest {
  id: number
  kind: "matchweek_recap" | "news_highlights"
  period_key: string
  created_at: string
  headline: string
  content: {
    intro: DigestItem | null
    sections: Array<{ title: string; bullets: DigestItem[]; generated_by?: string }>
  }
  sources: Source[]
  table?: {
    after_matchweek: number
    rows: Array<{ position: number; club: string; played: number; goal_difference: number; points: number; places_gained: number }>
  } | null
}
