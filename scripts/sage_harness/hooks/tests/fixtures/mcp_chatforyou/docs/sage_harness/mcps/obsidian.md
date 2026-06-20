---
id: obsidian
kind: mcp
transport: stdio
runtime_targets: [claude, codex]
server_binding:
  command: npx
  args: ["-y", "@modelcontextprotocol/server-filesystem", "${OBSIDIAN_VAULT_PATH}"]
---
## intent
Obsidian vault filesystem access (knowledge capture / wiki).
ChatForYou shadow-pilot fixture — vault path is a generic placeholder (real config uses an
absolute path; SAGE WARNs on home-path username leakage for portability).
