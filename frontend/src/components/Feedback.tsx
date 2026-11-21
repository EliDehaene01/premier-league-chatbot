import { useState } from "react"
import { ThumbsDown, ThumbsUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { sendFeedback } from "@/lib/api"
import { cn } from "@/lib/utils"

export function Feedback({ turnId }: { turnId: string }) {
  const [rating, setRating] = useState<"up" | "down" | null>(null)
  const [comment, setComment] = useState("")
  const [state, setState] = useState<"idle" | "asking" | "sent" | "error">("idle")

  async function submit(r: "up" | "down", text?: string) {
    try {
      await sendFeedback(turnId, r, text)
      setState("sent")
    } catch {
      setState("error")
    }
  }

  function rate(r: "up" | "down") {
    if (state === "sent") return
    setRating(r)
    if (r === "up") void submit(r)
    else setState("asking")
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
      {(["up", "down"] as const).map((r) => {
        const Icon = r === "up" ? ThumbsUp : ThumbsDown
        return (
          <Button
            key={r}
            variant="ghost"
            size="icon-xs"
            aria-label={r === "up" ? "Good answer" : "Bad answer"}
            aria-pressed={rating === r}
            disabled={state === "sent"}
            onClick={() => rate(r)}
            className={cn(rating === r && "text-primary")}
          >
            <Icon />
          </Button>
        )
      })}
      {state === "asking" && (
        <form
          className="flex flex-1 gap-1"
          onSubmit={(e) => {
            e.preventDefault()
            void submit("down", comment)
          }}
        >
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What was wrong? (optional)"
            maxLength={500}
            className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 text-xs"
          />
          <Button type="submit" size="xs" variant="outline">
            Send
          </Button>
        </form>
      )}
      {state === "sent" && <span>Thanks for the feedback.</span>}
      {state === "error" && <span className="text-destructive">Could not save feedback.</span>}
    </div>
  )
}
