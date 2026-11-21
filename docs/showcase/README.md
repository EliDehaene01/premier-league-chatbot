# Showcase

A demo recording (`10-chat-demo.gif`, shown first), screenshots (`*.png`) and recorded conversations (`conversations.json`) for the showcase page on
GitHub Pages. The chat needs the local API and Azure keys, so these are captured locally and
committed; `python -m digests publish` copies them into the site.

`conversations.json` is a list of `{"question", "answer", "sources": [{"title", "url"}]}`.

MCP demos: `mcp-claude-code.md` (Claude Code), `08-mcp-vscode.png` (VS Code Copilot Chat calling
`get_league_table`: Arsenal top on 27 points) and `09-mcp-claude-desktop.png` (Claude Desktop
calling `get_results`: Newcastle 2-2 Liverpool, matchweek 1, 1-0 at half-time). Each answer was
checked against the database. In Claude Desktop, name the server in the question ("Use the
premier-league tools: ..."), or it may answer from its built-in sports scores or web search.

The GIF is the full 74 s screen recording at 900 px wide and 10 fps (about 9.5 MB). The source MP4
stays out of git (`*.mp4` is ignored here); remake it with:

```powershell
ffmpeg -i premier-league-chatbot-demo.mp4 -vf "fps=10,scale=900:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" 10-chat-demo.gif
```
