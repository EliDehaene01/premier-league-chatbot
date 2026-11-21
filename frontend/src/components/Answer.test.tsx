import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { Answer, stripRawMarkers } from "./Answer"
import type { Source } from "@/lib/types"

afterEach(cleanup)

const sources: Source[] = [
  { n: 1, id: "m123", kind: "match", title: "Arsenal 2-1 Chelsea", date: "2026-11-08", url: "https://www.premierleague.com/en/match/123" },
]

describe("Answer", () => {
  it("links known [n] markers to their source card", () => {
    render(<Answer text="Arsenal won 2-1 [1]." sources={sources} id="abc-def" />)
    const link = screen.getByRole("link", { name: "1" })
    expect(link.getAttribute("href")).toBe("#source-abc-def-1")
    expect(link.getAttribute("title")).toBe("Arsenal 2-1 Chelsea")
  })

  it("leaves unknown markers as text", () => {
    render(<Answer text="Something [7]." sources={sources} id="x" />)
    expect(screen.queryByRole("link")).toBeNull()
    expect(screen.getByText("Something [7].")).toBeTruthy()
  })

  it("renders bullets and bold", () => {
    const { container } = render(<Answer text={"Top three:\n\n- **Arsenal** 28\n- City 26"} sources={[]} id="x" />)
    expect(container.querySelectorAll("li")).toHaveLength(2)
    expect(container.querySelector("strong")?.textContent).toBe("Arsenal")
  })
})

describe("stripRawMarkers", () => {
  it("hides model markers while streaming", () => {
    expect(stripRawMarkers("Arsenal won [m123] and lead [t11].")).toBe("Arsenal won and lead.")
  })
  it("hides grouped markers", () => {
    expect(stripRawMarkers("Arsenal won [m123, a456].")).toBe("Arsenal won.")
  })
  it("keeps renumbered markers", () => {
    expect(stripRawMarkers("Arsenal won [1].")).toBe("Arsenal won [1].")
  })
})
