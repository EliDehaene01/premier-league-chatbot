# Claude Code with the Premier League MCP server

Recorded 2026-11-21, 18:45 UTC, on the laptop (data as of the 17:53 UTC ingest: matchweek 11 in progress). Facts checked against the database: every matchweek 10 score and date matches `silver.matches`, and the table figures match the current table.

Server registered once from the repo root (PowerShell needs `claude.cmd`; the `claude.ps1` shim swallows `--`):

```powershell
claude.cmd mcp add --scope local premier-league -- "<path to python.exe>" -m mcp_server
```

Command:

```powershell
claude.cmd -p "Using the premier-league MCP tools: who is top of the league, and what were the results of matchweek 10?" --allowedTools "mcp__premier-league__*"
```

Answer, as printed:

**Arsenal are top of the league** with 27 points from 10 games (9 wins, 1 loss, goal difference +10). Brighton are second on 22 points from 10 games, and Manchester City are third, also on 22 points but from 11 games [t11]. Matchweek 11 is still being played: 6 of its 10 games are finished, and Arsenal haven't played theirs yet.

**Matchweek 10 results (6–8 Nov 2026):**

| Date | Home | Score | Away | Source |
|---|---|---|---|---|
| Fri 6 Nov | Everton | 3–1 | Coventry City | m2645288 |
| Sat 7 Nov | Leeds United | 1–0 | Tottenham Hotspur | m2645291 |
| Sat 7 Nov | Arsenal | 1–0 | Hull City | m2645285 |
| Sat 7 Nov | Fulham | 1–1 | Newcastle United | m2645289 |
| Sat 7 Nov | Nottingham Forest | 3–1 | Manchester City | m2645293 |
| Sun 8 Nov | Brighton | 2–0 | Brentford | m2645286 |
| Sun 8 Nov | Crystal Palace | 1–3 | Liverpool | m2645287 |
| Sun 8 Nov | Ipswich Town | 1–2 | Bournemouth | m2645290 |
| Sun 8 Nov | Sunderland | 1–0 | Chelsea | m2645294 |
| Sun 8 Nov | Manchester United | 4–4 | Aston Villa | m2645292 |

The highest-scoring game was the 4–4 draw between Manchester United and Aston Villa. Manchester City's 3–1 loss at Nottingham Forest was the main upset.
