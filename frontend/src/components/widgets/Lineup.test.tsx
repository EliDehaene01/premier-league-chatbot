import { cleanup, fireEvent, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { formationRows, Lineup } from "./Lineup"
import type { LineupTeam } from "@/lib/types"

afterEach(cleanup)

function team(club: string, formation: string, rows: number[]): LineupTeam {
  return {
    club,
    formation,
    manager: "A Manager",
    starting_xi_gk_to_attack: rows.map((row, i) => ({ name: `${club} Player${i + 1}`, shirt: i + 1, row })),
    substitutes: [{ name: `${club} Sub`, shirt: 20, came_on: 70 }],
  }
}

const home = team("Arsenal", "4-3-3", [1, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4])
const away = team("Chelsea", "4-2-3-1", [1, 2, 2, 2, 2, 3, 3, 4, 4, 4, 5])
const data = { match: { match_id: 1, home_club: "Arsenal", away_club: "Chelsea", home_score: 2, away_score: 1, period: "FullTime" }, teams: [home, away] }

describe("formationRows", () => {
  it("groups starters by row, goalkeeper first", () => {
    const rows = formationRows(home.starting_xi_gk_to_attack)
    expect(rows.map((r) => r.length)).toEqual([1, 4, 3, 3])
    expect(rows[0][0].shirt).toBe(1)
  })
  it("puts players without a row last", () => {
    const rows = formationRows([{ name: "A B", row: 2 }, { name: "C D" }, { name: "E F", row: 1 }])
    expect(rows.map((r) => r[0].name)).toEqual(["E F", "A B", "C D"])
  })
})

describe("Lineup", () => {
  it("draws eleven players and switches teams", () => {
    render(<Lineup data={data} />)
    const pitch = screen.getByRole("list", { name: "Arsenal starting eleven" })
    expect(within(pitch).getAllByRole("listitem")).toHaveLength(11)
    expect(screen.getByText(/Arsenal Sub \(on 70'\)/)).toBeTruthy()
    fireEvent.click(screen.getByRole("tab", { name: /Chelsea/ }))
    const other = screen.getByRole("list", { name: "Chelsea starting eleven" })
    // 4-2-3-1 has five rows including the goalkeeper
    expect(other.querySelectorAll(":scope > div.relative.flex")).toHaveLength(5)
  })
})
