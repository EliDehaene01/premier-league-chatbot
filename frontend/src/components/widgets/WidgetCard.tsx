import type { ReactNode } from "react"

export function WidgetCard({ title, meta, children }: { title: string; meta?: string; children: ReactNode }) {
  return (
    <section className="overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm">
      <header className="flex items-baseline justify-between gap-2 border-b px-3 py-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {meta && <span className="text-xs text-muted-foreground">{meta}</span>}
      </header>
      <div className="overflow-x-auto">{children}</div>
    </section>
  )
}
