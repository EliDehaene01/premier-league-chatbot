import { useEffect, useRef, useState } from "react"
import { ArrowUp, Loader2, RotateCcw, Square } from "lucide-react"
import { Answer, stripRawMarkers } from "@/components/Answer"
import { Feedback } from "@/components/Feedback"
import { Sources } from "@/components/Sources"
import { WidgetView } from "@/components/widgets"
import { Button } from "@/components/ui/button"
import { getSuggestions, streamChat } from "@/lib/api"
import { toolLabel } from "@/lib/format"
import type { ChatMessage, Source, ToolStatus, Usage, Widget } from "@/lib/types"

const MAX_CHARS = 1000
const MAX_HISTORY = 20 // the API accepts at most 20 messages
const FALLBACK_SUGGESTIONS = ["Who is top of the league?", "Who has scored the most goals this season?"]

const newId = () => crypto.randomUUID()

export function Chat() {
  const [conversationId, setConversationId] = useState(newId)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [busy, setBusy] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getSuggestions()
      .then((s) => setSuggestions(s.length ? s : FALLBACK_SUGGESTIONS))
      .catch(() => setSuggestions(FALLBACK_SUGGESTIONS))
  }, [])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [messages])

  function patch(id: string, fn: (m: ChatMessage) => ChatMessage) {
    setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)))
  }

  async function ask(question: string) {
    const text = question.trim()
    if (!text || busy) return
    const user: ChatMessage = { id: newId(), role: "user", content: text }
    const reply: ChatMessage = { id: newId(), role: "assistant", content: "", pending: true, tools: [] }
    const history = [...messages, user]
      .filter((m) => !m.error && m.content)
      .slice(-MAX_HISTORY)
      .map((m) => ({ role: m.role, content: m.content }))
    setMessages((ms) => [...ms, user, reply])
    setInput("")
    setBusy(true)
    const ctrl = new AbortController()
    abort.current = ctrl
    try {
      await streamChat(
        conversationId,
        history,
        ({ event, data }) => {
          const d = data as Record<string, unknown>
          if (event === "token") {
            patch(reply.id, (m) => ({ ...m, content: m.content + String(d.text ?? "") }))
          } else if (event === "tool_call") {
            const t = d as unknown as ToolStatus
            patch(reply.id, (m) => {
              const tools = [...(m.tools ?? [])]
              const open = tools.findIndex((x) => x.name === t.name && x.status === "started")
              if (t.status === "finished" && open >= 0) tools[open] = t
              else tools.push(t)
              // text streamed before a tool call was the model thinking aloud; drop it
              return { ...m, tools, content: "" }
            })
          } else if (event === "message") {
            patch(reply.id, (m) => ({
              ...m,
              pending: false,
              turnId: String(d.turn_id),
              content: String(d.answer ?? ""),
              sources: (d.sources as Source[]) ?? [],
              widgets: (d.widgets as Widget[]) ?? [],
            }))
          } else if (event === "usage") {
            patch(reply.id, (m) => ({ ...m, usage: d as Usage }))
          } else if (event === "error") {
            patch(reply.id, (m) => ({ ...m, pending: false, error: String(d.message ?? "Something went wrong.") }))
          }
        },
        ctrl.signal,
      )
      patch(reply.id, (m) => (m.pending ? { ...m, pending: false, error: m.error ?? "The answer was cut off." } : m))
    } catch (e) {
      const stopped = ctrl.signal.aborted
      patch(reply.id, (m) => ({
        ...m,
        pending: false,
        error: stopped ? "Stopped." : e instanceof Error ? e.message : "Could not reach the API.",
      }))
    } finally {
      setBusy(false)
      abort.current = null
    }
  }

  function reset() {
    abort.current?.abort()
    setMessages([])
    setConversationId(newId())
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
          {messages.length === 0 && <EmptyState suggestions={suggestions} onPick={ask} />}
          {messages.map((m) => (m.role === "user" ? <UserBubble key={m.id} m={m} /> : <AssistantTurn key={m.id} m={m} />))}
          <div ref={bottom} />
        </div>
      </div>
      <div className="border-t bg-card/80 backdrop-blur">
        <form
          className="mx-auto flex max-w-3xl items-end gap-2 px-4 py-3"
          onSubmit={(e) => {
            e.preventDefault()
            void ask(input)
          }}
        >
          {messages.length > 0 && (
            <Button type="button" variant="ghost" size="icon" onClick={reset} aria-label="New chat" title="New chat">
              <RotateCcw />
            </Button>
          )}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                void ask(input)
              }
            }}
            rows={1}
            maxLength={MAX_CHARS}
            placeholder="Ask about the table, fixtures, players or the latest news"
            aria-label="Your question"
            className="max-h-40 min-h-10 flex-1 resize-none rounded-lg border bg-background px-3 py-2 text-sm field-sizing-content focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          />
          {busy ? (
            <Button type="button" size="icon-lg" variant="secondary" onClick={() => abort.current?.abort()} aria-label="Stop">
              <Square />
            </Button>
          ) : (
            <Button type="submit" size="icon-lg" disabled={!input.trim()} aria-label="Send">
              <ArrowUp />
            </Button>
          )}
        </form>
        <p className="pb-2 text-center text-[11px] text-muted-foreground">
          Stats come from the Premier League's data; news from premierleague.com articles. No betting advice.
        </p>
      </div>
    </div>
  )
}

function EmptyState({ suggestions, onPick }: { suggestions: string[]; onPick: (q: string) => void }) {
  return (
    <div className="pt-10 text-center">
      <h2 className="text-2xl font-bold tracking-tight">Ask me about this Premier League season</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Table, fixtures, results, line-ups, players and the week's news, with sources for every answer.
      </p>
      <div className="mt-8 grid gap-2 sm:grid-cols-2">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="rounded-xl border bg-card px-4 py-3 text-left text-sm transition-colors hover:border-primary/50 hover:bg-secondary"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

function UserBubble({ m }: { m: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-sm whitespace-pre-wrap text-primary-foreground">
        {m.content}
      </p>
    </div>
  )
}

function ToolSteps({ tools, pending }: { tools: ToolStatus[]; pending?: boolean }) {
  if (!tools.length) return null
  return (
    <ul className="mb-2 flex flex-wrap gap-1.5" aria-label="Tools used">
      {tools.map((t, i) => (
        <li
          key={`${t.name}-${i}`}
          className="flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] text-secondary-foreground"
        >
          {t.status === "started" && pending ? <Loader2 className="size-3 animate-spin" aria-hidden="true" /> : null}
          {toolLabel(t.name)}
          {t.error ? " (failed)" : ""}
        </li>
      ))}
    </ul>
  )
}

function AssistantTurn({ m }: { m: ChatMessage }) {
  const text = m.pending ? stripRawMarkers(m.content) : m.content
  return (
    <article className="text-sm" aria-busy={m.pending}>
      <ToolSteps tools={m.tools ?? []} pending={m.pending} />
      {text ? (
        <Answer text={text} sources={m.sources ?? []} id={m.id} />
      ) : m.pending ? (
        <p className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Thinking
        </p>
      ) : null}
      {m.error && <p className="mt-2 text-destructive">{m.error}</p>}
      {!!m.widgets?.length && (
        <div className="mt-4 grid gap-3">
          {m.widgets.map((w, i) => (
            <WidgetView key={i} widget={w} />
          ))}
        </div>
      )}
      <Sources sources={m.sources ?? []} id={m.id} />
      {m.turnId && !m.pending && <Feedback turnId={m.turnId} />}
    </article>
  )
}
