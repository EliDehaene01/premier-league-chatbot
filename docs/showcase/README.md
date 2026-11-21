# Showcase

Screenshots (`*.png`) and recorded conversations (`conversations.json`) for the showcase page on
GitHub Pages. The chat needs the local API and Azure keys, so these are captured locally and
committed; `python -m digests publish` copies them into the site.

`conversations.json` is a list of `{"question", "answer", "sources": [{"title", "url"}]}`.

MCP demos: `mcp-claude-code.md` (Claude Code), `08-mcp-vscode.png` (VS Code Copilot Chat calling
`get_league_table`: Arsenal top on 27 points) and `09-mcp-claude-desktop.png` (Claude Desktop
calling `get_results`: Newcastle 2-2 Liverpool, matchweek 1, 1-0 at half-time). Each answer was
checked against the database. In Claude Desktop, name the server in the question ("Use the
premier-league tools: ..."), or it may answer from its built-in sports scores or web search.
