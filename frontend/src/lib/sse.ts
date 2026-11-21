// Minimal server-sent events parser for a fetch() body (EventSource cannot POST).

export interface SseEvent {
  event: string
  data: unknown
}

export function parseSseChunk(buffer: string): { events: SseEvent[]; rest: string } {
  const events: SseEvent[] = []
  const blocks = buffer.split("\n\n")
  const rest = blocks.pop() ?? ""
  for (const block of blocks) {
    let event = "message"
    const data: string[] = []
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim()
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart())
    }
    if (data.length) {
      try {
        events.push({ event, data: JSON.parse(data.join("\n")) })
      } catch {
        events.push({ event, data: data.join("\n") })
      }
    }
  }
  return { events, rest }
}

export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n")
    const { events, rest } = parseSseChunk(buffer)
    buffer = rest
    yield* events
  }
  if (buffer.trim()) yield* parseSseChunk(buffer + "\n\n").events
}
