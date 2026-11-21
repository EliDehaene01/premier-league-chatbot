import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { Sources } from "@/components/Sources"
import { getLatestDigests } from "@/lib/api"
import { formatDate } from "@/lib/format"
import type { Digest, DigestItem } from "@/lib/types"
import { cn } from "@/lib/utils"
import { WidgetCard } from "./widgets/WidgetCard"

const LABEL = { matchweek_recap: "Matchweek recap", news_highlights: "News highlights" }

function Cited({ item, id }: { item: DigestItem; id: string }) {
  return (
    <>
      {item.text}
      {(item.cites ?? []).map((n) => (
        <a
          key={n}
          href={`#source-${id}-${n}`}
          className="mx-0.5 inline-grid h-4 min-w-4 place-items-center rounded bg-accent px-1 align-super text-[10px] font-semibold text-accent-foreground no-underline hover:bg-primary hover:text-primary-foreground"
        >
          {n}
        </a>
      ))}
    </>
  )
}

function Movement({ gained }: { gained: number }) {
  if (!gained) return null
  return (
    <span className={cn("text-[11px] font-semibold", gained > 0 ? "text-emerald-600" : "text-red-600")}>
      {gained > 0 ? `▲${gained}` : `▼${-gained}`}
    </span>
  )
}

export function DigestView({ digest }: { digest: Digest }) {
  const id = `d${digest.id}`
  return (
    <article className="space-y-4">
      <header>
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {LABEL[digest.kind]} · {formatDate(digest.created_at)}
        </p>
        <h2 className="mt-1 text-2xl font-bold tracking-tight">{digest.headline}</h2>
        {digest.content.intro && (
          <p className="mt-2 text-sm leading-relaxed">
            <Cited item={digest.content.intro} id={id} />
          </p>
        )}
      </header>
      {digest.content.sections.map((s) => (
        <WidgetCard key={s.title} title={s.title}>
          <ul className="list-disc space-y-1.5 py-2 pr-3 pl-8 text-sm">
            {s.bullets.map((b, i) => (
              <li key={i}>
                <Cited item={b} id={id} />
              </li>
            ))}
          </ul>
        </WidgetCard>
      ))}
      {digest.table && (
        <WidgetCard title="Table" meta={`After matchweek ${digest.table.after_matchweek}`}>
          <table className="w-full text-xs tabular-nums">
            <tbody>
              {digest.table.rows.map((r) => (
                <tr key={r.club} className="border-t text-center [&>td]:px-2 [&>td]:py-1.5">
                  <td className="w-6 text-left text-muted-foreground">{r.position}</td>
                  <td className="text-left font-medium">{r.club}</td>
                  <td>{r.played}</td>
                  <td>{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</td>
                  <td className="font-bold">{r.points}</td>
                  <td className="w-8">
                    <Movement gained={r.places_gained} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </WidgetCard>
      )}
      <Sources sources={digest.sources} id={id} />
    </article>
  )
}

export function ThisWeek() {
  const [digests, setDigests] = useState<Partial<Record<Digest["kind"], Digest>> | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    getLatestDigests().then(setDigests).catch(() => setError(true))
  }, [])

  if (error) return <p className="py-16 text-center text-sm text-destructive">Could not load the digests.</p>
  if (!digests)
    return (
      <p className="flex justify-center py-16 text-muted-foreground">
        <Loader2 className="size-5 animate-spin" aria-label="Loading" />
      </p>
    )
  const list = (["matchweek_recap", "news_highlights"] as const).map((k) => digests[k]).filter(Boolean) as Digest[]
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-12 px-4 py-8">
        {list.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No digests yet. The matchweek recap arrives on Tuesday morning and the news highlights on Friday.
          </p>
        ) : (
          list.map((d) => <DigestView key={d.id} digest={d} />)
        )}
      </div>
    </div>
  )
}
