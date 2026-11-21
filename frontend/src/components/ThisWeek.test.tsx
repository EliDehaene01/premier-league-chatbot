import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { DigestView } from "./ThisWeek"
import type { Digest } from "@/lib/types"

afterEach(cleanup)

const digest: Digest = {
  id: 7,
  kind: "matchweek_recap",
  period_key: "mw10",
  created_at: "2026-11-10T05:00:00Z",
  headline: "Arsenal stretch their lead",
  content: {
    intro: { text: "Arsenal won again.", sources: ["m1"], cites: [1] },
    sections: [{ title: "Title race", bullets: [{ text: "Brighton climbed to second.", sources: ["t10"], cites: [2] }] }],
  },
  sources: [
    { n: 1, id: "m1", kind: "match", title: "Arsenal 2-0 Spurs", date: "2026-11-08", url: "https://www.premierleague.com/en/match/1" },
    { n: 2, id: "t10", kind: "table", title: "Premier League table after matchweek 10", date: null, url: "https://www.premierleague.com/en/tables" },
  ],
  table: { after_matchweek: 10, rows: [{ position: 2, club: "Brighton", played: 10, goal_difference: 19, points: 22, places_gained: 1 }] },
}

describe("DigestView", () => {
  it("renders sections, citation links, table movement and sources", () => {
    render(<DigestView digest={digest} />)
    expect(screen.getByRole("heading", { name: "Arsenal stretch their lead" })).toBeTruthy()
    expect(screen.getByRole("link", { name: "2" }).getAttribute("href")).toBe("#source-d7-2")
    expect(screen.getByText("▲1")).toBeTruthy()
    expect(screen.getByRole("list", { name: "Sources" }).querySelectorAll("li")).toHaveLength(2)
  })
})
