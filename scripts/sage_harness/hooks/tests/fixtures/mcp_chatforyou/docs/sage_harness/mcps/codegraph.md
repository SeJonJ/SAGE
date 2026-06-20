---
id: codegraph
kind: mcp
transport: stdio
runtime_targets: [claude, codex]
server_binding:
  command: codegraph
  args: ["serve", "--mcp"]
---
## intent
Code intelligence knowledge graph over the indexed workspace (symbols, edges, files).
ChatForYou shadow-pilot fixture — real server shape, no live config mutation.
