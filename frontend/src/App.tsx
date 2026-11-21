import { useEffect, useState } from "react"
import { Chat } from "@/components/Chat"
import { HealthBadge } from "@/components/HealthBadge"
import { ThisWeek } from "@/components/ThisWeek"
import { getHealth } from "@/lib/api"
import type { Health } from "@/lib/types"
import { cn } from "@/lib/utils"

type View = "chat" | "week"

function viewFromHash(): View {
  return window.location.hash === "#/week" ? "week" : "chat"
}

export default function App() {
  const [view, setView] = useState<View>(viewFromHash)
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    const onHash = () => setView(viewFromHash())
    window.addEventListener("hashchange", onHash)
    return () => window.removeEventListener("hashchange", onHash)
  }, [])

  useEffect(() => {
    let alive = true
    const load = () => getHealth().then((h) => alive && setHealth(h)).catch(() => {})
    load()
    const t = window.setInterval(load, 60_000)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [])

  return (
    <div className="flex h-dvh flex-col">
      <header className="border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-4 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
              <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
                <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
                <path d="M12 7l4 3-1.5 5h-5L8 10z" fill="currentColor" />
              </svg>
            </span>
            <div className="leading-tight">
              <h1 className="text-sm font-bold">PL Chat</h1>
              <p className="text-xs text-muted-foreground">Premier League 2026-27</p>
            </div>
          </div>
          <nav className="ml-4 flex gap-1 text-sm">
            {(["chat", "week"] as const).map((v) => (
              <a
                key={v}
                href={v === "chat" ? "#/" : "#/week"}
                className={cn(
                  "rounded-md px-3 py-1.5 font-medium transition-colors",
                  view === v ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {v === "chat" ? "Chat" : "This week"}
              </a>
            ))}
          </nav>
          <div className="ml-auto">
            <HealthBadge health={health} />
          </div>
        </div>
      </header>
      <main className="min-h-0 flex-1">
        {view === "chat" ? (
          <Chat />
        ) : (
          <ThisWeek />
        )}
      </main>
    </div>
  )
}
