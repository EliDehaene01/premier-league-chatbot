import { readSse, type SseEvent } from "./sse"
import type { Digest, Health, Role } from "./types"

export async function streamChat(
  conversationId: string,
  messages: Array<{ role: Role; content: string }>,
  onEvent: (e: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, messages }),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = typeof body.detail === "string" ? body.detail : detail
    } catch {
      /* not JSON */
    }
    throw new Error(detail)
  }
  for await (const e of readSse(res.body)) onEvent(e)
}

export async function sendFeedback(turnId: string, rating: "up" | "down", comment?: string) {
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turn_id: turnId, rating, comment: comment || null }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health")
  if (!res.ok) return { status: "down", db: false }
  return res.json()
}

export async function getSuggestions(): Promise<string[]> {
  const res = await fetch("/api/suggestions")
  if (!res.ok) return []
  return (await res.json()).suggestions ?? []
}

export async function getLatestDigests(): Promise<Partial<Record<Digest["kind"], Digest>>> {
  const res = await fetch("/api/digests/latest")
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
