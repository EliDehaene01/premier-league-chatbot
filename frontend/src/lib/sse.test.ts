import { describe, expect, it } from "vitest"
import { parseSseChunk } from "./sse"

describe("parseSseChunk", () => {
  it("parses complete events and keeps the partial rest", () => {
    const { events, rest } = parseSseChunk('event: token\ndata: {"text":"Hi"}\n\nevent: usage\ndata: {"cost')
    expect(events).toEqual([{ event: "token", data: { text: "Hi" } }])
    expect(rest).toBe('event: usage\ndata: {"cost')
  })
})
