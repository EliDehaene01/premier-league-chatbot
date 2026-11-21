# 0010: The chatbot reaches its tools over MCP, in-process by default

**Status:** accepted (2026-11-21)

## Context

The plan was to define the tool layer once and have the chatbot use it as an MCP client, so the server is a real product surface and the evals test what users get. The chat loop is synchronous (psycopg, the OpenAI SDK, worker threads in the API); the MCP SDK is async. A separate server process would be one more thing to start on the laptop.

## Decision

- The server serves `backend.tools.TOOL_SPECS` and `run_tool` unchanged (overriding `list_tools`/`call_tool`), rather than letting the SDK derive schemas from Python signatures.
- `McpTools` holds one MCP session on an anyio blocking portal and exposes sync `specs()`/`call()` to the chat loop.
- By default the API, the terminal chat and the eval runner run the server in-process (memory transport). `MCP_URL` switches to a running HTTP server; `TOOL_TRANSPORT=direct` bypasses MCP.

## Consequences

- One definition of every tool; a test fails if the MCP schemas drift from the chat's.
- Every chat tool call is a real MCP request and response, at the cost of JSON round-tripping (dates become strings, which the model saw as strings already).
- Calls on the shared API session are serialised by a lock; fine for one local user, and the HTTP transport is the way out if that ever matters.
- Claude Desktop, VS Code and any other MCP host get the same tools, resources and prompts with no extra code.
