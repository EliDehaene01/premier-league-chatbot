import { FileText, ListOrdered, Shield, Trophy } from "lucide-react"
import type { Source } from "@/lib/types"
import { formatDate } from "@/lib/format"

const ICON = { article: FileText, match: Trophy, table: ListOrdered, club: Shield }

export function Sources({ sources, id }: { sources: Source[]; id: string }) {
  if (!sources.length) return null
  return (
    <ol className="mt-3 grid gap-2 sm:grid-cols-2" aria-label="Sources">
      {sources.map((s) => {
        const Icon = ICON[s.kind] ?? FileText
        return (
          <li key={s.n} id={`source-${id}-${s.n}`}>
            <a
              href={s.url}
              target="_blank"
              rel="noreferrer"
              className="flex h-full gap-2 rounded-lg border bg-card p-2.5 text-xs transition-colors hover:border-primary/50 hover:bg-secondary target:ring-2"
            >
              <span className="grid size-5 shrink-0 place-items-center rounded bg-accent text-[10px] font-semibold text-accent-foreground">
                {s.n}
              </span>
              <span className="min-w-0">
                <span className="line-clamp-2 font-medium text-foreground">{s.title}</span>
                <span className="mt-0.5 flex items-center gap-1 text-muted-foreground">
                  <Icon className="size-3" aria-hidden="true" />
                  {s.kind}
                  {s.date ? ` · ${formatDate(s.date)}` : ""}
                </span>
              </span>
            </a>
          </li>
        )
      })}
    </ol>
  )
}
