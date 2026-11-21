import { Fragment, type ReactNode } from "react"
import type { Source } from "@/lib/types"

// Raw citation markers the model writes ([a123], [m456], [t11], ...) before the backend
// validates and renumbers them. Hidden while streaming; the final message has [n] instead.
const RAW_MARKER = /\s?\[\s*[a-z]\d[\w-]*(?:\s*[,;]\s*[a-z]\d[\w-]*)*\s*\]/g

export function stripRawMarkers(text: string): string {
  return text.replace(RAW_MARKER, "")
}

function inline(text: string, sources: Source[], msgId: string, key: string): ReactNode[] {
  const byN = new Map(sources.map((s) => [s.n, s]))
  const out: ReactNode[] = []
  const re = /\*\*(.+?)\*\*|\[(\d+)\]/g
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    if (m[1] !== undefined) {
      out.push(<strong key={`${key}-b${i++}`}>{m[1]}</strong>)
    } else {
      const src = byN.get(Number(m[2]))
      out.push(
        src ? (
          <a
            key={`${key}-c${i++}`}
            href={`#source-${msgId}-${src.n}`}
            title={src.title}
            className="mx-0.5 inline-grid h-4 min-w-4 place-items-center rounded bg-accent px-1 align-super text-[10px] font-semibold text-accent-foreground no-underline hover:bg-primary hover:text-primary-foreground"
          >
            {src.n}
          </a>
        ) : (
          m[0]
        ),
      )
    }
    last = re.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

/** Renders the small Markdown subset the prompt allows: paragraphs, bullets, bold, [n]. */
export function Answer({ text, sources, id }: { text: string; sources: Source[]; id: string }) {
  const blocks = text.trim().split(/\n{2,}/)
  return (
    <div className="space-y-3 leading-relaxed">
      {blocks.map((block, bi) => {
        const lines = block.split("\n")
        const key = `${id}-${bi}`
        if (lines.every((l) => /^\s*([-*]|\d+\.)\s+/.test(l))) {
          const ordered = /^\s*\d+\./.test(lines[0])
          const items = lines.map((l, li) => (
            <li key={li}>{inline(l.replace(/^\s*([-*]|\d+\.)\s+/, ""), sources, id, key)}</li>
          ))
          return ordered ? (
            <ol key={bi} className="list-decimal space-y-1 pl-5">{items}</ol>
          ) : (
            <ul key={bi} className="list-disc space-y-1 pl-5">{items}</ul>
          )
        }
        return (
          <p key={bi}>
            {lines.map((l, li) => (
              <Fragment key={li}>
                {li > 0 && <br />}
                {inline(l.replace(/^#+\s*/, ""), sources, id, key)}
              </Fragment>
            ))}
          </p>
        )
      })}
    </div>
  )
}
