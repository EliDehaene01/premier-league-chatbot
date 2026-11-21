# 0004: Own Premier League MCP server

**Status:** accepted (2026-11-21)

## Context

The chatbot's tools (table, matches, players, article search) are useful outside the chat UI, for example from Claude or other MCP clients.

## Decision

Build an own MCP server with FastMCP in Phase 5 that exposes the same tool functions the chat loop uses, reading from the same gold tables.

## Consequences

- Tools must be plain functions with typed inputs and outputs, shared by the chat loop and the MCP server.
- Changes to `mcp_server` run the eval suite like other LLM-facing code.
