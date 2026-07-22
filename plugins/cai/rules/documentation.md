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
- For flowcharts, set the `elk` layout renderer to reduce edge crossings
  automatically instead of leaving Mermaid on its default `dagre` layout:
  ```
  ---
  config:
    flowchart:
      defaultRenderer: "elk"
  ---
  ```
  Confirm the target renderer actually honors it (Mermaid ≥10.5 with
  `layout-elk`, or Claude Artifacts) — some renderers (e.g. GitHub's Markdown
  preview) silently ignore it and fall back to `dagre`. If so, or if
  crossings remain, reduce them manually: reorder node/edge declarations,
  group related nodes in a `subgraph`, or switch `TD`/`LR` direction.
- Don't hand-escape special characters (`<`, `>`, `&`, etc.) as HTML entities
  (`&lt;`, `&gt;`) or URL-encoded sequences inside Mermaid source. Instead
  wrap the label in double quotes (`A["text"]`), which Mermaid parses
  literally, or reword to avoid the character. Only use Mermaid's own numeric
  entity syntax (`#60;`, `#62;`) as a last resort if the character is
  unavoidable and quoting still fails to parse.
- When a diagram shows a change, color-code nodes by change type so the delta is
  obvious at a glance. Use `classDef` with a stable convention:
  - Added → green (`classDef added fill:#d4edda,stroke:#28a745,color:#155724`)
  - Modified → amber (`classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404`)
  - Existing/unchanged → gray (`classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057`)
