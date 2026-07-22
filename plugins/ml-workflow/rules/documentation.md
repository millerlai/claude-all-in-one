---
paths:
  - "**/*.md"
---

# Documentation
- Write docs in Markdown.
- Use Mermaid for diagrams (flowcharts, sequence, ER, etc.) instead of prose-only
  descriptions when structure or flow matters.
- Validate every Mermaid block before delivering: check syntax, node/edge references,
  and that it renders — never ship a diagram you haven't confirmed parses.
- When a diagram shows a change, color-code nodes by change type so the delta is
  obvious at a glance. Use `classDef` with a stable convention:
  - Added → green (`classDef added fill:#d4edda,stroke:#28a745,color:#155724`)
  - Modified → amber (`classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404`)
  - Existing/unchanged → gray (`classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057`)
