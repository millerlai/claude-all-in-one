# CAI v2 補充設計

## Skill-First, Agent-Optional Execution Architecture

**版本：** Draft v1  
**日期：** 2026-10-30  
**適用專案：** `millerlai/claude-all-in-one`

---

# 1. Executive Summary

CAI v2 原本的方向已經從：

```
Chief Orchestrator
      ↓
Many Specialized Agents
```

修正為：

```
Context-Rich Main Session
      ↓
Adaptive Delegation
      ↓
Subagent only when beneficial
```

進一步研究後，可以再做一個重要的架構修正：

> **不要把 Role、Skill、Agent 視為同一件事情。**

例如：

```
Architect
Designer
Implementer
Reviewer
Security Reviewer
Debugger
Verifier
```

這些名稱描述的其實首先是：

```
Capability
```

而不是：

```
Agent Instance
```

因此 CAI v2 建議採用：

# Skill-First, Agent-Optional

核心原則：

> **Skill 定義「如何完成工作」，Agent 定義「在哪個 Context 中執行工作」。**

也就是：

```
Capability ≠ Agent
```

更精確地說：

```
Skill
=
Procedure / Expertise / Workflow

Agent
=
Execution Context / Reasoning Instance
```

因此不應：

```
Need Security Review
        ↓
Spawn Security Agent
```

而應：

```
Need Security Review
        ↓
Select security-review Skill
        ↓
Determine execution context
        ↓
Main or Subagent
```

---

# 2. 為什麼需要這個改變

Multi-Agent 最大成本之一不是「啟動另一個 Agent」本身，而是 Context Boundary。

當 Main 已經理解：

```
Requirement
Architecture
Constraints
Previous Decisions
Relevant Code
Current Hypothesis
Failed Attempts
Current Diff
```

如果建立 Fresh Subagent：

```
Main Context
     │
     ▼
Context Selection
     │
     ▼
Context Handoff
     │
     ▼
Fresh Subagent
     │
     ▼
Context Reconstruction
     │
     ▼
Execute
     │
     ▼
Result Compression
     │
     ▼
Main
```

會增加：

```
Context Transfer Cost
Context Reconstruction Cost
Coordination Cost
Result Compression Cost
Verification Duplication
```

如果工作其實高度依賴 Main 已經建立的 Context，這些成本可能超過 Delegation Benefit。

因此：

> **只有「角色不同」不足以構成建立 Subagent 的理由。**

---

# 3. Skill 模型

Skill 應被視為：

```
Capability Definition
+
Procedure
+
Heuristics
+
Tool Strategy
+
Input Contract
+
Output Contract
+
Verification Rules
```

例如：

```
skill:
  name: security-review

purpose:
  detect security regressions

inputs:
  - requirement
  - diff
  - relevant_code
  - security_constraints

procedure:
  - identify trust boundaries
  - inspect changed attack surface
  - inspect authentication
  - inspect authorization
  - inspect input validation
  - inspect secret handling
  - inspect dependency changes

output:
  schema: security-findings

execution:
  context_requirement: low
  isolation_benefit: high
  parallelizable: true
```

這個 Skill 本身並沒有指定：

```
必须建立 Security Agent
```

它只描述：

```
How to perform Security Review
```

---

# 4. Agent 模型

Agent 則應重新定義為：

# Execution Context

例如：

```
MAIN
FRESH
FORK
```

Agent 不再代表：

```
Role
```

而代表：

```
Where reasoning happens
```

因此：

```
Security Review
```

可以有：

```
security-review Skill
        +
MAIN Context
```

也可以：

```
security-review Skill
        +
FRESH Subagent
```

同一個 Capability，可以根據 Task 特性選擇不同 Execution Context。

---

# 5. 核心架構原則

CAI v2 應正式加入：

# Agent is not a Role. Agent is an Execution Context.

例如：

```
Architect
```

不是 Agent Type。

它是：

```
architect Skill
```

而：

```
Main Session
Fresh Subagent
Forked Context
```

才是 Execution Context。

因此：

```
Capability
        │
        ▼
Skill
        │
        ▼
Execution Context
        │
        ▼
Main / Fresh / Fork
```

---

# 6. Tool、Skill、Agent 三層模型

CAI v2 建議建立三層 Capability Architecture。

---

## Layer 1 — Deterministic Tools

處理可確定性執行的工作。

例如：

```
git
grep
ripgrep
AST
pytest
lint
type checker
compiler
schema validation
codemap
dependency scan
```

特性：

```
Deterministic
Cheap
Repeatable
Inspectable
Low reasoning requirement
```

原則：

> 如果 deterministic tool 可以完成，就不要使用 LLM Agent。

---

## Layer 2 — Skills

處理需要 reasoning，但不一定需要新 Context 的工作。

例如：

```
architect
design
debug
implement
refactor
review
security-review
verify
ship
```

Skill 定義：

```
How to think
How to inspect
How to execute
How to verify
How to report
```

但不決定：

```
Where to execute
```

---

## Layer 3 — Agents

只有需要：

```
Context Isolation
Parallel Exploration
Independent Judgment
Independent Workstream
Additional Context Capacity
```

時才建立。

例如：

```
Fresh Explorer
Independent Reviewer
Security Reviewer
Architecture Candidate
Independent Implementation Worker
```

因此整體模型：

```
             ┌─────────────────────┐
             │       AGENTS        │
             │                     │
             │ Context isolation   │
             │ Parallelism         │
             │ Independent view    │
             │ Context capacity    │
             └──────────┬──────────┘
                        │
             ┌──────────▼──────────┐
             │       SKILLS        │
             │                     │
             │ Procedures          │
             │ Expertise           │
             │ Workflows           │
             │ Heuristics          │
             └──────────┬──────────┘
                        │
             ┌──────────▼──────────┐
             │       TOOLS         │
             │                     │
             │ Deterministic       │
             │ Execution           │
             │ Verification        │
             └─────────────────────┘
```

Main Session 控制三層：

```
                 MAIN
                  │
           Context Owner
           Decision Owner
           Integration Owner
                  │
          ┌───────┼───────┐
          ▼       ▼       ▼
        Tools   Skills   Agents
```

---

# 7. Skill-First Routing

CAI 不應再首先問：

```
Which Agent should handle this?
```

應改成：

```
What capability does this Task require?
```

流程：

```
Task
 │
 ▼
Capability Selection
 │
 ▼
Skill Selection
 │
 ▼
Can deterministic tools handle part/all of it?
 │
 ▼
Context Requirement Analysis
 │
 ▼
Execution Context Selection
 │
 ▼
Main / Fresh / Fork
 │
 ▼
Parallelization Decision
 │
 ▼
Model Routing
 │
 ▼
Execute
 │
 ▼
Evidence
```

---

# 8. Skill 與 Agent 的關係

不是：

```
Skill OR Agent
```

而是：

```
Skill
+
Execution Context
```

例如：

```
debug
+
main
```

或：

```
security-review
+
fresh
```

或：

```
architecture-analysis
+
fork
```

因此可以表示：

```
execution:
  capability: security-review
  context: fresh
```

而不是：

```
agent:
  type: security-reviewer
```

---

# 9. Same-Context Skill Execution

假設 Main 已經花大量 Context debugging：

```
Main Context

Requirement
Architecture
Relevant Code
Logs
Previous Attempts
Current Hypothesis
Failed Hypothesis
Current Diff
```

如果使用：

```
debug Skill
```

流程：

```
Main Context
     │
     ▼
Load debug Skill
     │
     ▼
Apply debugging procedure
     │
     ▼
Continue reasoning
```

Context 不跨 Boundary。

因此不存在：

```
Context Handoff
Context Reconstruction
Result Handoff
```

可以表示為：

[  
C\_{next} = Skill(C\_{main})  
]

而不是：

[  
C\_{sub} = H(C\_{main}, Task)  
]

---

# 10. Fresh-Context Skill Execution

Security Review 則可能不同。

Main 已經完成 Implementation：

```
Main
 │
 ├── implementation reasoning
 ├── architecture assumptions
 ├── chosen solution
 └── current diff
```

如果希望 Security Review 不被 Implementation reasoning anchoring：

```
Main
 │
 ▼
Context Handoff
 │
 ▼
Fresh Context
 │
 ▼
security-review Skill
 │
 ▼
Independent Findings
 │
 ▼
Evidence
 │
 ▼
Main
```

這時 Context Isolation 本身就是 Benefit。

---

# 11. Skill vs Subagent 的成本模型

不應簡化為：

```
Skill is cheaper than Agent
```

真正需要比較：

## Same-Context Skill

```
Cost_same =
SkillReasoning
+
ToolUsage
```

## Fresh Subagent + Skill

```
Cost_fresh =
ContextSelection
+
ContextTransfer
+
ContextReconstruction
+
SkillReasoning
+
ToolUsage
+
ResultCompression
+
Coordination
```

但 Fresh Context 有額外 Benefit：

```
IsolationBenefit
ParallelismBenefit
IndependentJudgmentBenefit
ContextCapacityBenefit
```

因此：

```
FreshExecutionValue
=
IsolationBenefit
+
ParallelismBenefit
+
IndependentJudgmentBenefit
+
ContextCapacityBenefit
-
ContextTransferCost
-
ContextReconstructionCost
-
CoordinationCost
-
ResultCompressionCost
```

只有：

```
FreshExecutionValue > Threshold
```

才建立 Subagent。

---

# 12. Skill-First 的主要 Token 優勢

假設 Main 已經使用：

```
40K tokens
```

建立 debugging context。

Fresh Debug Agent：

```
Main 40K
   │
   ▼
Context Pack
   │
   ▼
Debug Agent
   │
   ▼
Re-read Code
   │
   ▼
Reconstruct Architecture
   │
   ▼
Reconstruct Hypothesis
```

可能大量重複工作。

Skill-first：

```
Main 40K
   │
   ▼
debug Skill
   │
   ▼
Continue from existing context
```

避免：

```
Repeated File Reads
Repeated Architecture Discovery
Repeated Hypothesis Building
Context Serialization
Result Re-synthesis
```

因此對高度 Context-Coupled Task 特別有價值。

---

# 13. 但 Fresh Context 有時反而更有效率

如果 Main Context 已非常大：

```
80K tokens
```

而 Review 只需要：

```
Requirement
Design
Diff
Relevant Files
```

例如只需要：

```
15K tokens
```

Fresh Subagent 可以：

```
15K Focused Context
+
review Skill
```

而 Main：

```
80K Historical Context
+
review Skill
```

未必更有效率。

因此 Routing 不能只看：

```
是否已經有 Main Context
```

還需要考慮：

```
MainContextSize
RelevantContextSize
IsolationBenefit
ContextReconstructionCost
```

---

# 14. Context Efficiency Ratio

可以增加：

```
ContextEfficiency =
RelevantContext / LoadedContext
```

例如：

```
Main Context = 80K
Relevant Review Context = 15K
```

則：

```
ContextEfficiency = 15 / 80
                  = 18.75%
```

如果比例很低：

```
Fresh Context
```

可能反而比較合理。

---

# 15. Context Coupling

另一方面，需要計算：

```
ContextCoupling
```

表示 Task 對 Main Context 的依賴程度。

---

## LOW

例如：

```
Search all usages of API X.
```

適合：

```
Fresh
```

---

## MEDIUM

例如：

```
Review this isolated adapter.
```

適合：

```
Main or Fresh
```

---

## HIGH

例如：

```
Implement authentication feature across modules.
```

適合：

```
Main
```

---

## VERY HIGH

例如：

```
Continue debugging intermittent distributed race
after several failed hypotheses.
```

適合：

```
Main
```

---

# 16. Isolation Benefit

新增：

```
IsolationBenefit
```

衡量 Task 是否因為 Clean Context 而受益。

例如：


| Task                      | Isolation Benefit |
| ------------------------- | ----------------- |
| Implementation            | Low               |
| Debugging                 | Low               |
| Architecture continuation | Low               |
| Code Review               | High              |
| Security Review           | High              |
| Architecture alternative  | High              |
| Independent Verification  | High              |
| Research exploration      | High              |


因此：

```
ContextCoupling HIGH
+
IsolationBenefit LOW
```

通常：

```
MAIN
```

而：

```
ContextCoupling LOW
+
IsolationBenefit HIGH
```

通常：

```
FRESH
```

---

# 17. Parallelism Benefit

再加入：

```
ParallelismBenefit
```

例如：

```
Search frontend architecture
Search backend architecture
Search database architecture
Search test architecture
```

彼此：

```
Low Dependency
High Independence
```

非常適合：

```
Explorer Skill
+
Fresh Subagents
+
Parallel
```

---

# 18. Skill Metadata

每個 Skill 應包含 execution metadata。

例如：

```
skill:
  name: explorer

execution:
  context_coupling: low
  isolation_benefit: medium
  parallelizable: high
  deterministic_support: medium
  default_context: fresh
```

而：

```
skill:
  name: debug

execution:
  context_coupling: very_high
  isolation_benefit: low
  parallelizable: low
  deterministic_support: medium
  default_context: main
```

---

# 19. Architect

原本：

```
architect Agent
```

建議：

```
architect Skill
```

預設：

```
context: main
```

原因：

Architecture 通常高度依賴：

```
User Intent
Existing Architecture
Constraints
Previous Decisions
Tradeoffs
Rejected Alternatives
```

如果需要 Architecture Arena：

```
architect Skill
      │
      ├── Fresh Candidate A
      ├── Fresh Candidate B
      └── Fresh Candidate C
```

Main 最後：

```
Compare
Synthesize
Decide
```

因此：

```
Architect
=
Skill-first
+
optional independent execution
```

---

# 20. Designer

建議：

```
designer Skill
```

預設：

```
MAIN
```

因為 Design 高度依賴：

```
Requirement
Architecture
Constraints
Previous Decisions
```

只有：

```
Alternative Design Exploration
```

才使用 Fresh Context。

---

# 21. Implementer

這是最重要的改變之一。

原本：

```
Main
 ↓
Implementer Agent
```

現在：

```
Main
 ↓
implement Skill
```

預設：

```
context: main
```

原因：

Coding 往往需要持續：

```
Read
Understand
Modify
Test
Debug
Modify
Retest
```

這是一條 Context-rich sequential loop。

只有：

```
Bounded Scope
Clear Interface
Low Context Coupling
Low File Overlap
High Verifiability
```

才：

```
implement Skill
+
Fresh Subagent
```

---

# 22. Explorer

Explorer 是相反案例。

推薦：

```
explorer Skill
+
Fresh Subagent
```

原因：

Explorer 工作通常：

```
Read-heavy
Search-heavy
Parallelizable
Independent
Compressible
```

例如：

```
Main
 │
 ├── Explorer A → auth
 ├── Explorer B → persistence
 ├── Explorer C → tests
 └── Explorer D → API
```

最後回：

```
Findings
+
References
+
Evidence
```

---

# 23. Reviewer

Reviewer 應：

```
review Skill
```

但 execution context：

```
Main
```

或：

```
Fresh
```

皆可能。

小修改：

```
Main + review Skill
```

大型或高風險修改：

```
Fresh Subagent
+
review Skill
```

因為：

```
Independent Judgment
```

具有價值。

---

# 24. Security Reviewer

推薦：

```
security-review Skill
```

並偏向：

```
Fresh
```

尤其：

```
Authentication
Authorization
Cryptography
Secrets
External Input
Permission
Payment
Infrastructure
```

因為 Clean Context 可以降低：

```
Implementation Anchoring
```

---

# 25. Test Runner

`test-runner Agent` 大部分情況應被降級。

首先：

```
Tool
```

其次才是：

```
Skill
```

例如：

```
Main
 ↓
test Skill
 ↓
test_runner.py
 ↓
pytest
 ↓
structured result
```

而不是：

```
Main
 ↓
Test Agent
 ↓
LLM decides to run pytest
 ↓
pytest
```

可以 deterministic 的部分不應浪費 Agent reasoning。

---

# 26. Verifier

Verifier 建議：

```
verify Skill
```

其 execution context 依 Verification 類型決定。

Deterministic verification：

```
Main
 ↓
verify Skill
 ↓
Tools
```

Independent semantic verification：

```
Fresh Subagent
 ↓
verify Skill
```

---

# 27. Shipper

`shipper Agent` 大部分應改成：

```
ship Skill
+
Deterministic Tools
```

例如：

```
git status
validation
version check
release metadata
tag validation
artifact validation
```

都應由 deterministic script 處理。

LLM 只處理：

```
Risk interpretation
Release summary
Human approval coordination
```

---

# 28. Refactoring Detector

推薦：

```
refactoring-detector
```

優先：

```
Static Analysis
+
Skill
```

例如：

```
AST
complexity metrics
dependency analysis
duplication detection
```

先由 Tool 找 Candidate。

Skill 再判斷：

```
是否值得 refactor
```

---

# 29. CAI 現有 Agent 重新分類


| 現有角色                   | CAI v2 建議                         |
| ---------------------- | --------------------------------- |
| `architect`            | Skill-first                       |
| `designer`             | Skill-first                       |
| `implementer`          | Main + Skill-first                |
| `explorer`             | Skill + frequently Fresh Subagent |
| `reviewer`             | Skill + optional Fresh Subagent   |
| `security-reviewer`    | Skill + optional Fresh Subagent   |
| `test-runner`          | Tool / Skill                      |
| `verifier`             | Skill + optional Fresh Subagent   |
| `shipper`              | Skill + deterministic tools       |
| `refactoring-detector` | Tool + Skill                      |


這代表：

> CAI 現有 Agent Definition 不一定要全部刪除，但不應再假設每個 Role 都需要獨立 Agent Instance。

---

# 30. Skill 與 Agent 解耦

例如原本：

```
security-reviewer.md
```

同時包含：

```
Role
Prompt
Procedure
Execution Context
```

應拆成：

```
skills/security-review/
    SKILL.md
```

定義：

```
Capability
Procedure
Input
Output
Verification
```

Agent definition 則只處理：

```
Context Isolation
Tool Permission
Model
Execution Policy
```

---

# 31. Execution Router

原本規劃：

```
delegation.py
```

建議升級成：

```
execution_router.py
```

因為 Runtime 不只是判斷：

```
Should I delegate?
```

而是：

```
What capability?
Which Skill?
Which Context?
Parallel or Sequential?
Which Model?
Which Tools?
```

---

# 32. Execution Router Input

例如：

```
task:
  id: AUTH-004

  type: debugging

  context_coupling: very_high
  isolation_benefit: low
  parallelizability: low
  verifiability: medium
  risk: high

  main_context_size: large
  relevant_context_ratio: high
```

---

# 33. Execution Router Output

例如：

```
routing:
  capability: debug

  executor:
    type: skill

  context:
    mode: main

  parallel:
    enabled: false

  model:
    tier: think
```

另一個：

```
routing:
  capability: security-review

  executor:
    type: skill

  context:
    mode: fresh

  parallel:
    enabled: true

  model:
    tier: build
```

---

# 34. Routing Decision Dimensions

Execution Router 至少考慮：

```
ContextCoupling
IsolationBenefit
ParallelismBenefit
RelevantContextRatio
ContextReconstructionCost
ContextTransferCost
Verifiability
Risk
ToolSupport
TaskDependency
FileOverlap
```

---

# 35. Recommended Decision Matrix


| Context Coupling | Isolation | Parallelism | Recommendation         |
| ---------------- | --------- | ----------- | ---------------------- |
| High             | Low       | Low         | Main + Skill           |
| High             | High      | Low         | Main / Fork            |
| Low              | High      | Low         | Fresh + Skill          |
| Low              | High      | High        | Parallel Fresh + Skill |
| Low              | Low       | Low         | Main + Skill           |
| Medium           | High      | High        | Fresh preferred        |
| Very High        | Low       | Any         | Main                   |


---

# 36. Skill Router

新增：

```
skill_router.py
```

負責：

```
Task Type
   ↓
Capability
   ↓
Skill
```

例如：

```
bug investigation
      ↓
debug
```

```
security regression
      ↓
security-review
```

```
architecture decision
      ↓
architect
```

---

# 37. Runtime Pipeline

CAI v2 新 Pipeline：

```
User
 │
 ▼
Main Session
 │
 ▼
Goal / Intent
 │
 ▼
Task Graph
 │
 ▼
Capability Analysis
 │
 ▼
Skill Router
 │
 ▼
Deterministic Tool Check
 │
 ▼
Context Analysis
 │
 ▼
Execution Router
 │
 ├───────────────┬───────────────┐
 ▼               ▼               ▼
MAIN            FRESH           FORK
 │               │               │
 ▼               ▼               ▼
Skill           Skill           Skill
 │               │               │
 └───────────────┼───────────────┘
                 ▼
              Evidence
                 │
                 ▼
              Policy
                 │
                 ▼
               Main
```

---

# 38. Context Handoff 變成 Conditional Layer

之前 Context Handoff 幾乎是：

```
Task
 ↓
Subagent
 ↓
Context Handoff
```

現在改成：

```
Task
 ↓
Skill
 ↓
Execution Router
 ↓
Need Context Boundary?
```

如果：

```
NO
```

則：

```
Main
 ↓
Skill
```

完全沒有 Context Handoff。

只有：

```
YES
```

才：

```
Main
 ↓
Context Handoff
 ↓
Fresh/Fork Context
 ↓
Skill
```

因此：

> Context Handoff 不再是所有 Task 的標準流程，而是跨 Execution Context 時才啟動的機制。

---

# 39. Context Handoff 新定位

`context_[handoff.py](http://handoff.py)` 仍然重要。

但只處理：

```
MAIN → FRESH
MAIN → FORK
FRESH → MAIN
FORK → MAIN
```

而：

```
MAIN → Skill → MAIN
```

不需要它。

這可以顯著降低系統複雜度。

---

# 40. Task Graph 不指定 Agent

Task Graph 不應：

```
task:
  agent: security-reviewer
```

而應：

```
task:
  capability: security-review
```

Execution Router 再決定：

```
Main
or
Fresh
or
Fork
```

因此再次強調：

# Task Graph ≠ Agent Graph

---

# 41. Task Schema 更新

推薦：

```
task:

  id: AUTH-004

  capability:
    required: debug

  characteristics:
    context_coupling: very_high
    isolation_benefit: low
    parallelizable: false
    verifiability: medium

  scope:
    - auth/token.py
    - auth/cache.py

  constraints:
    - public API cannot change

  verification:
    - reproduce race
    - run auth concurrency tests
```

不指定：

```
Agent
```

---

# 42. Runtime 才決定 Agent

Runtime：

```
Task
 ↓
Skill Router
 ↓
debug
 ↓
Execution Router
 ↓
MAIN
```

另一個：

```
Task
 ↓
Skill Router
 ↓
security-review
 ↓
Execution Router
 ↓
FRESH
```

因此 Task Definition 與 Runtime Strategy 解耦。

---

# 43. Model Routing 也應解耦

同樣不要：

```
security-reviewer = Opus
```

而應：

```
Task
 ↓
Skill
 ↓
Complexity
Risk
Context
 ↓
Model Router
```

例如：

```
model:
  tier: think
```

或：

```
model:
  tier: build
```

因此：

```
Skill ≠ Model
Agent ≠ Model
Task ≠ Model
```

---

# 44. 完整 Routing 模型

最終：

```
Task
 │
 ▼
Capability
 │
 ▼
Skill
 │
 ▼
Tool Strategy
 │
 ▼
Context Strategy
 │
 ▼
Execution Strategy
 │
 ▼
Model Strategy
 │
 ▼
Verification Strategy
```

這些維度彼此獨立。

---

# 45. Architecture Arena

Architecture Arena 仍保留。

但不需要：

```
Architect Agent A
Architect Agent B
Architect Agent C
```

概念上應該是：

```
architect Skill
       │
       ├── Fresh Context A
       ├── Fresh Context B
       └── Fresh Context C
```

也就是：

```
Same Skill
Different Independent Reasoning Contexts
```

這個描述更精確。

---

# 46. Parallel Review

同理：

```
review Skill
       │
       ├── correctness context
       ├── security context
       └── regression context
```

甚至可以是不同 Skill：

```
review
security-review
performance-review
```

在 Fresh Context 平行執行。

---

# 47. Independent Judgment

Subagent 最重要的價值之一，不只是 Parallelism。

還包括：

```
Independent Judgment
```

例如：

```
Implementer Main
```

已經形成：

```
Solution Bias
```

Fresh Reviewer 沒有這些 reasoning history。

因此：

```
Fresh Context
```

本身可以是 Verification Strategy。

---

# 48. Skill Composition

Skill-first 另一個優勢是可以組合。

例如：

```
implement
   ↓
test
   ↓
review
   ↓
verify
```

全部可以：

```
Main Context
```

執行。

也可以：

```
implement → Main

test → Tool

review → Fresh

verify → Main + deterministic tools
```

Runtime 可以自由組合。

---

# 49. Skill Pipeline

例如：

```
pipeline:

  - skill: implement
    context: main

  - skill: test
    executor: tool

  - skill: review
    context: fresh

  - skill: verify
    context: main
```

這比固定 Agent Pipeline 更彈性。

---

# 50. Deterministic Before Skill

新的原則可以從：

```
Deterministic Before Agentic
```

進一步細化：

```
Tool before Skill
Skill before Agent
```

完整：

# Tool-First → Skill-First → Agent-When-Necessary

判斷：

```
Can deterministic tool solve it?
        │
      YES
        ↓
      TOOL

        NO
        ↓

Can Main + Skill solve it efficiently?
        │
      YES
        ↓
 MAIN + SKILL

        NO
        ↓

Does isolation / parallelism help?
        │
      YES
        ↓
SUBAGENT + SKILL
```

---

# 51. CAI v2 新核心公式

之前：

```
Reliable Agentic SDLC
=
Context Management
×
Adaptive Delegation
×
Deterministic Infrastructure
×
Evidence Verification
×
Risk-based Autonomy
```

現在建議修改為：

```
Reliable Agentic SDLC
=
Context Management
×
Capability Routing
×
Execution Routing
×
Deterministic Infrastructure
×
Evidence Verification
×
Risk-based Autonomy
```

其中：

```
Capability Routing
=
Tool / Skill Selection
```

而：

```
Execution Routing
=
Main / Fresh / Fork / Parallel
```

---

# 52. Effective Delegation 公式

保留：

```
DelegationValue
=
ParallelismBenefit
+
SpecializationBenefit
+
ContextIsolationBenefit
+
IndependentJudgmentBenefit
+
ContextCapacityBenefit
-
ContextTransferCost
-
ContextReconstructionCost
-
CoordinationCost
-
VerificationDuplication
```

只有：

```
DelegationValue > Threshold
```

才跨出 Main Context。

---

# 53. 更精確的 Skill Execution 公式

對任何 Skill：

```
ExecutionValue(context_mode)
```

比較：

```
EV_main
EV_fresh
EV_fork
```

Runtime 選：

```
argmax(EV)
```

概念上：

```
BestExecutionContext
=
argmax(
    Quality
  + Isolation
  + Parallelism
  + ContextEfficiency
  - TransferCost
  - ReconstructionCost
  - CoordinationCost
)
```

不需要一開始知道：

```
Which Agent?
```

---

# 54. Context Manager 的角色不變

```
context_manager.py
```

仍然負責：

```
Main Context Lifecycle
Reasoning Digest
Decisions
Discoveries
Constraints
Failures
Context Compaction
```

它的重要性甚至更高。

因為更多工作會留在：

```
Main
```

執行。

---

# 55. Context Handoff Manager 的角色縮小但更明確

```
context_handoff.py
```

只在：

```
ExecutionContext changes
```

時啟動。

負責：

```
Minimum Sufficient Context
Task Contract
Context References
Context Expansion
Result Contract
Evidence References
```

---

# 56. 新增 Skill Router

建議新增：

```
plugins/cai/scripts/skill_router.py
```

負責：

```
Task
 ↓
Capability Classification
 ↓
Skill Selection
```

---

# 57. 新增 Execution Router

建議：

```
plugins/cai/scripts/execution_router.py
```

取代或吸收原本：

```
delegation.py
```

負責：

```
MAIN
FRESH
FORK
PARALLEL
```

判斷。

---

# 58. Proposed Runtime Components

更新後：

```
plugins/cai/scripts/

context_manager.py
context_handoff.py

task_graph.py

skill_router.py
execution_router.py
model_router.py

scheduler.py

evidence.py
policy.py
events.py
```

---

# 59. 各 Component 責任

## `context_[manager.py](http://manager.py)`

```
What should Main remember?
```

---

## `skill_[router.py](http://router.py)`

```
What capability is needed?
```

---

## `execution_[router.py](http://router.py)`

```
Where should this capability execute?
```

---

## `context_[handoff.py](http://handoff.py)`

```
What context must cross the execution boundary?
```

---

## `model_[router.py](http://router.py)`

```
Which model tier should execute?
```

---

## [`scheduler.py`](http://scheduler.py)

```
When can it execute?
Can it execute in parallel?
```

---

## [`evidence.py`](http://evidence.py)

```
What proves the result?
```

---

## [`policy.py`](http://policy.py)

```
Can execution continue automatically?
```

---

# 60. CAI v2 最終 Runtime

```
                         USER
                           │
                           ▼
                    MAIN SESSION
                           │
                   Strategic Context
                           │
                           ▼
                   Context Manager
                           │
                           ▼
                       Task Graph
                           │
                           ▼
                    Skill Router
                           │
                  Required Capability
                           │
                           ▼
                Deterministic Check
                           │
                ┌──────────┴──────────┐
                │                     │
              TOOL                 REASONING
                │                     │
                │                     ▼
                │             Execution Router
                │                     │
                │        ┌────────────┼────────────┐
                │        │            │            │
                │       MAIN        FRESH         FORK
                │        │            │            │
                │        │            ▼            ▼
                │        │      Context Handoff Context Handoff
                │        │            │            │
                │        └────────────┼────────────┘
                │                     │
                │                     ▼
                │                   Skill
                │                     │
                └──────────┬──────────┘
                           ▼
                       Execution
                           │
                           ▼
                        Evidence
                           │
                           ▼
                         Policy
                           │
                           ▼
                    MAIN / HUMAN
```

---

# 61. Migration Strategy

這個架構不建議一次把所有 Agent 刪掉。

應逐步 migration。

---

## Phase 1 — Agent Inventory

分析目前：

```
agents/
```

每個 Agent：

```
What capability does it provide?
Does it require isolated context?
Does it require independent judgment?
Does it benefit from parallelism?
Can deterministic tools replace part of it?
```

---

## Phase 2 — Extract Skills

將 Agent 裡：

```
Procedure
Heuristics
Checklist
Workflow
Output Contract
```

抽成：

```
skills/
```

---

## Phase 3 — Same-Context Execution

讓 Main 可以直接：

```
Main + Skill
```

執行。

---

## Phase 4 — Execution Router

加入：

```
MAIN
FRESH
FORK
```

判斷。

---

## Phase 5 — Conditional Subagents

只有：

```
Isolation
Parallelism
Independent Judgment
Context Capacity
```

有明確 Benefit 才建立。

---

## Phase 6 — Evals

比較：

```
Main + Skill
```

vs

```
Fresh Subagent + Skill
```

---

# 62. Eval Design

這個問題不能只靠直覺。

CAI 應建立：

```
evals/execution-routing/
```

比較：

### Configuration A

```
Main + Skill
```

### Configuration B

```
Fresh Subagent + Skill
```

### Configuration C

```
Fork + Skill
```

---

# 63. Eval Metrics

至少測量：

```
Task Success Rate

Total Tokens

Wall Clock Time

Repeated File Reads

Context Reconstruction Tokens

Verification Failure Rate

Retry Rate

Human Intervention

Defect Escape Rate

Context Missing Rate
```

---

# 64. 最重要的效率指標

推薦：

```
Verified Output / Token
```

而不是：

```
Number of Agents
```

以及：

```
Verified Output / Wall Clock
```

再加：

```
Human Minutes / Completed Task
```

---

# 65. 需要驗證的核心假設

CAI 應透過 Evals 驗證：

### Hypothesis 1

高度 Context-Coupled coding task：

```
Main + Skill
```

比：

```
Fresh Subagent
```

更有效率。

---

### Hypothesis 2

Independent Review：

```
Fresh + Skill
```

比：

```
Main + Skill
```

更容易找到 Main 遺漏問題。

---

### Hypothesis 3

Explorer：

```
Parallel Fresh Subagents
```

在大型 repository exploration 中具有優勢。

---

### Hypothesis 4

Test execution：

```
Deterministic Tool
```

比：

```
Test Agent
```

更便宜、更穩定。

---

### Hypothesis 5

Architecture：

```
Main + architect Skill
```

適合 continuation。

而：

```
Multiple Fresh + architect Skill
```

適合 alternative generation。

---

# 66. Anti-Patterns

CAI v2 應明確避免：

## Agent per Role

```
Need review
→ spawn Reviewer Agent
```

錯誤。

---

## Agent per Stage

```
Design Agent
→ Build Agent
→ Verify Agent
→ Ship Agent
```

會造成大量 Context Handoff。

---

## Agent for Deterministic Work

```
Test Agent
→ pytest
```

通常沒有必要。

---

## Agent for Small Task

```
Rename function
→ Implementer Agent
```

沒有必要。

---

## Agent because Prompt is Specialized

```
Specialized Prompt
→ Must be Specialized Agent
```

錯誤。

Specialized Prompt 很可能只是：

```
Skill
```

---

# 67. 正確抽象

應改成：

```
Specialized Knowledge
        ↓
      Skill
```

```
Independent Context
        ↓
      Agent
```

```
Deterministic Action
        ↓
      Tool
```

三者不要混在一起。

---

# 68. 新的 CAI Design Principle

CAI v2 增加：

### Principle 1

**Capability is not Agent.**

---

### Principle 2

**Skill defines how; execution context defines where.**

---

### Principle 3

**Tool before Skill.**

---

### Principle 4

**Skill before Agent.**

---

### Principle 5

**Agent only when context separation creates measurable value.**

---

### Principle 6

**Main owns strategic context.**

---

### Principle 7

**Context boundaries must justify their cost.**

---

### Principle 8

**Fresh context is useful for independence, not merely specialization.**

---

### Principle 9

**Parallelize independent work, not dependent reasoning.**

---

### Principle 10

**Do not create an Agent just because a Role has a name.**

---

# 69. CAI v2 新核心哲學

原本可能是：

```
Find the right Agent for the Task.
```

現在改成：

```
Find the right Capability for the Task,
then choose the cheapest effective
Execution Context.
```

即：

```
Task
 ↓
Capability
 ↓
Tool / Skill
 ↓
Context
 ↓
Execution
 ↓
Evidence
```

---

# 70. 最終架構定位

CAI v2 不應被定位成：

# Multi-Agent SDLC Framework

更精確的定位應該是：

# Context-Aware Capability Orchestration Runtime

它可以使用：

```
0 Subagents
```

也可以：

```
1 Subagent
```

甚至：

```
N Parallel Subagents
```

但 Agent Count 不再是 Architecture Goal。

真正目標是：

```
Right Capability
      ×
Right Context
      ×
Right Execution
      ×
Right Model
      ×
Right Evidence
```

---

# 71. Final Recommendation

CAI v2 的預設策略應從：

```
Role
 ↓
Agent
```

正式改成：

```
Task
 ↓
Capability
 ↓
Tool / Skill
 ↓
Execution Context
 ↓
Main / Fresh / Fork
```

其中預設優先順序：

```
Tool
 ↓
Main + Skill
 ↓
Fresh/Fork + Skill
 ↓
Parallel Agents
```

只有當：

```
Parallelism Benefit
Isolation Benefit
Independent Judgment Benefit
Context Capacity Benefit
```

足以抵銷：

```
Context Transfer Cost
Context Reconstruction Cost
Coordination Cost
Result Compression Cost
Verification Duplication
```

才跨出 Main Session。

因此 CAI v2 的核心設計原則可以濃縮成：

> **Tool-First → Skill-First → Agent-When-Necessary**

以及：

> **Agent is not a Role. Agent is an Execution Context.**

最終 CAI 不需要追求「更多 Agent」。

應追求：

> **用最少的 Context Movement 與最少的 Agent Boundary，完成最多可驗證的軟體工程工作。**

---

# 72. References

## Anthropic — Effective Context Engineering for AI Agents

重點：

- Context 是有限且重要的資源。
- Compaction、external memory、subagent 都是不同的 Context Management Strategy。
- Subagent 適合使用獨立 Context 執行大量探索，再把濃縮資訊交回 Main。
- Iterative development 則更適合保持工作連續性的 context management。

## Anthropic — How We Built Our Multi-Agent Research System

重點：

- Multi-Agent 在高度可平行化的 research workload 特別有效。
- Subagent 使用自己的 Context Window。
- Multi-Agent 會顯著增加 Token 消耗。
- 需要共享大量 Context、具有大量 dependency 的工作，不一定適合 Multi-Agent。
- Coding 通常比 Research 少真正可以獨立平行化的工作。

## Anthropic — Effective Harnesses for Long-Running Agents

重點：

- Long-running coding 最大問題之一是 Context Continuity。
- 透過 persistent artifacts 將工作狀態交給下一個 Context。
- 是否 specialized multi-agent 一定優於 single general-purpose coding agent，仍然是需要實驗驗證的問題。

## Anthropic — Patterns and Problems in Emerging Multiagent Systems

重點：

- Independent workstream 較容易平行化。
- Agent 彼此存在 dependency 時，coordination difficulty 明顯提高。
- Software engineering project 通常具有持續變動且複雜的 interdependency。

---

# 73. 與 CAI v2 其他設計文件的關係

CAI v2 現在可以拆成三個核心 Architecture Layer：

```
┌─────────────────────────────────────────────┐
│  Context-Centric Adaptive SDLC Architecture │
│                                             │
│  What should Main own and coordinate?       │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│       Context Handoff Architecture          │
│                                             │
│  What information crosses Context Boundary? │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│    Skill-First Execution Architecture       │
│                                             │
│  Should a Context Boundary exist at all?    │
└─────────────────────────────────────────────┘
```

三個問題依序為：

```
1. Main 應該保留什麼 Context？

2. 如果跨 Context，
   應該傳什麼資訊？

3. 這個 Task 到底需不需要跨 Context？
```

第三個問題應該在 Runtime 中優先於第二個問題。

因為：

> **最便宜、最可靠的 Context Handoff，就是根本不需要發生的 Context Handoff。**