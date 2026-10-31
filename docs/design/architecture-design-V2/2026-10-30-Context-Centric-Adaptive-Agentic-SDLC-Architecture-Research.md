# Claude All-in-One v2

## Context-Centric Adaptive Agentic SDLC Architecture

**版本：** Draft v2  
**日期：** 2026-10-30  
**專案：** `millerlai/claude-all-in-one`

---

# 1. Executive Summary

Claude All-in-One（CAI）目前已經不是單純的 prompt collection，而是一套具有：

- Persistent Track State
- SDLC Stage
- Specialized Agent
- Model Tier Routing
- Deterministic Guard
- Human Gate
- Code Map
- Verification
- Token / Cost Tracking

能力的 Agentic SDLC 系統。

目前核心流程為：

```
/cai:track <feature>

        ↓

     design

        ↓
   Human Gate

        ↓

      build

        ↓

     verify

        ↓

      ship

        ↓
   Human Gate
```

CAI v2 不建議演進成：

```
Chief Agent
    ↓
Managers
    ↓
50 Subagents
    ↓
Verifiers
    ↓
Judge
```

原因是近期 Multi-Agent 與 Software Engineering Agent 研究顯示：

1. Multi-Agent 並非 Agent 越多效果越好。
2. Multi-Agent 最適合可高度平行化、低 context coupling 的工作。
3. Sequential / high-context-coupling task 可能因 Multi-Agent coordination 而退化。
4. Coding task 通常不像 Research task 那麼容易平行化。
5. Subagent 必須重新建立 context，存在 Context Reconstruction Cost。
6. Agent handoff 會產生 Coordination Cost。
7. Main Agent 若必須重新閱讀、理解與驗證 Subagent 工作，會產生 Verification Duplication Cost。
8. 長時間 Single Agent 同樣存在 Context Pollution 與 Context Explosion 問題。
9. 因此真正需要最佳化的不是 Agent Count，而是：

> **Context Placement + Compute Allocation + Verification Strategy**

CAI v2 因此改採：

# Context-Centric Adaptive Agent Orchestration

核心原則：

> **Keep strategic context centralized; parallelize bounded exploration, evidence gathering, and independently verifiable work.**

中文：

> **集中核心理解與決策，平行化資訊探索、驗證與低耦合工作。**

---

# 2. Research Findings

## 2.1 More Agents ≠ Better Performance

Google Research 於 2026 年針對 180 種 Agent configuration 進行 controlled evaluation。

研究比較：

- Single Agent
- Independent Multi-Agent
- Centralized Multi-Agent
- Decentralized Multi-Agent
- Hybrid Multi-Agent

結果顯示：

```
Parallelizable Task
        ↓
Multi-Agent can help

Sequential Task
        ↓
Multi-Agent can hurt
```

在可平行化工作上，Centralized coordination 可以帶來明顯提升。

但在高度 sequential 的工作上，Multi-Agent coordination 反而造成：

- communication overhead
- reasoning fragmentation
- coordination cost
- cognitive budget dilution

因此：

```
Agent Count ↑
```

不代表：

```
Performance ↑
```

真正重要的是：

```
Task Decomposability
Task Dependency
Tool Density
Context Coupling
Coordination Cost
```

---

# 3. Coding 與 Research 的差異

Anthropic 在其 Multi-Agent Research System 的工程經驗中指出：

Multi-Agent 特別適合：

```
Research
Search
Information Gathering
Independent Investigation
```

例如：

```
Research Topic
     │
 ┌───┼────┬────┐
 ↓   ↓    ↓    ↓
A    B    C    D
```

各 Agent 可以獨立搜尋。

Coding 則常見：

```
Architecture
     ↓
Interface
     ↓
Implementation
     ↓
Integration
     ↓
Debug
```

這些工作之間存在大量 dependency。

因此 Coding 的：

```
True Parallelism
```

通常低於 Research。

Anthropic 也觀察到 Multi-Agent 系統會大量增加 token consumption。

因此 Multi-Agent 必須被視為：

```
Inference Compute Scaling
```

而不是免費的：

```
Parallelism
```

---

# 4. Context 是 Software Agent 的核心資源

Software Engineering Agent 的工作品質高度依賴：

```
User Intent

Architecture

Previous Decisions

Files Already Inspected

Rejected Alternatives

Current Hypothesis

Previous Failures

Current Diff

Tests

Runtime Observations
```

這些資訊共同形成：

# Working Context

---

# 5. Context Reconstruction Problem

假設 Main Agent 已經理解：

```
Module A
   ↓
Module B
   ↓
callback
   ↓
legacy compatibility
   ↓
Module C
```

Main Agent 已經花費大量 reasoning 建立 mental model。

如果此時 spawn：

```
Subagent
```

Subagent 並沒有這些 implicit knowledge。

它必須：

```
Read CLAUDE.md
      ↓
Read Design
      ↓
Read Code
      ↓
Search References
      ↓
Understand Architecture
      ↓
Reconstruct Mental Model
```

因此產生：

# Context Reconstruction Cost

---

# 6. Context Pack 並不能完全解決問題

可以建立：

```
Main Context
     ↓
Context Builder
     ↓
Context Pack
     ↓
Subagent
```

但 Context Pack 本質上是：

# Lossy Compression

因為 Main Agent 必須先知道：

```
What information matters?
```

才能建立 Context Pack。

然而複雜 debugging 最大的困難經常正是：

```
We don't know what matters yet.
```

因此 Context Pack 適合：

```
Well-defined bounded task
```

例如：

```
Implement this interface.
```

不適合：

```
Find why this distributed transaction
occasionally loses state.
```

---

# 7. Context Explosion 也是問題

另一個極端也不正確：

```
Everything stays in Main forever.
```

長時間 coding session 會逐漸累積：

```
planning
logs
tool output
failed tests
debugging
old hypotheses
obsolete assumptions
implementation details
```

最後：

```
Strategic Context

+

Execution Noise
```

混在一起。

這稱為：

# Context Pollution

---

# 8. Dynamic Reasoning Context

SWE-AGILE 提出一個重要方向：

```
Recent Reasoning
      ↓
keep detailed

Historical Reasoning
      ↓
compress

Important Decisions
      ↓
persist
```

形成：

```
┌───────────────────────────┐
│ Recent Working Context    │
│                           │
│ Current hypothesis        │
│ Current files             │
│ Current implementation    │
│ Current debugging         │
└───────────────────────────┘

            +

┌───────────────────────────┐
│ Reasoning Digest          │
│                           │
│ Decisions                 │
│ Discoveries               │
│ Rejected approaches       │
│ Previous failures         │
└───────────────────────────┘
```

CAI v2 應把這個概念提升成核心架構能力。

---

# 9. CAI v2 Architecture Principle

CAI v2 不再以：

```
Agent Management
```

為中心。

而是：

```
Context Management
       +
Adaptive Delegation
       +
Verification
```

---

# 10. Proposed Architecture

```
                         USER
                           │
                           ▼
                ┌───────────────────┐
                │   MAIN SESSION    │
                │                   │
                │ Context Owner     │
                │ Decision Owner    │
                │ Integration Owner │
                └─────────┬─────────┘
                          │
                    Goal / Intent
                          │
                          ▼
                ┌───────────────────┐
                │   Task Analysis   │
                │                   │
                │ Dependency        │
                │ Coupling          │
                │ Risk              │
                │ Verifiability     │
                └─────────┬─────────┘
                          │
             ┌────────────┴────────────┐
             │                         │
        KEEP IN MAIN               DELEGATE
             │                         │
             │               ┌─────────┼─────────┐
             │               │         │         │
             │            Explorer  Reviewer  Specialist
             │               │         │         │
             │               └─────────┼─────────┘
             │                         │
             └─────────────┬───────────┘
                           ▼
                  Deterministic Evidence
                           │
                           ▼
                      Main Decision
                           │
                           ▼
                         Ship
```

---

# 11. Main Session 的角色

Main Agent 不只是 Orchestrator。

Main Agent 是：

# Context Owner

負責維持：

```
User Goal
Architecture
Current State
Important Decisions
Current Hypothesis
Integration State
Risk
```

同時也是：

# Decision Owner

負責：

```
architecture decision
implementation strategy
delegation decision
integration decision
accept/reject evidence
```

以及：

# Integration Owner

負責：

```
cross-module consistency
contract compatibility
final integration
```

---

# 12. Subagent 的重新定位

CAI v2 不把 Subagent 當成：

```
Employee
```

而應視為：

# Temporary Compute

也就是：

```
Main
  ↓
Need additional compute?
  ↓
Spawn bounded specialist
  ↓
Return evidence/result
  ↓
Terminate
```

Subagent 不應長期擁有 project knowledge。

---

# 13. Adaptive Delegation

不是每一個 Task 都應 spawn Agent。

CAI 應建立：

# Delegation Decision

每個 Task 計算：

```
Parallelism Benefit
Specialization Benefit
Context Isolation Benefit

vs

Context Transfer Cost
Coordination Cost
Verification Duplication
```

概念公式：

```
DV =
ParallelismBenefit
+ SpecializationBenefit
+ ContextIsolationBenefit
- ContextTransferCost
- CoordinationCost
- VerificationDuplication
```

只有：

```
DV > threshold
```

才 delegate。

---

# 14. Context Coupling

增加：

```
context_coupling
```

屬性。

值：

```
LOW
MEDIUM
HIGH
VERY_HIGH
```

例如：


| Task                   | Coupling   |
| ---------------------- | ---------- |
| Search API usage       | LOW        |
| Research library       | LOW        |
| Security review        | LOW        |
| Independent adapter    | MEDIUM     |
| Feature implementation | HIGH       |
| Cross-module refactor  | HIGH       |
| Complex debugging      | VERY\_HIGH |
| Architecture migration | VERY\_HIGH |


---

# 15. Parallelizability

增加：

```
parallelizability
```

例如：

```
HIGH
MEDIUM
LOW
```

Research：

```
parallelizability = HIGH
```

Complex Debugging：

```
parallelizability = LOW
```

---

# 16. Verifiability

第三個重要變數：

```
verifiability
```

例如：

```
Run pytest
```

屬於：

```
HIGH
```

但：

```
Improve architecture quality
```

可能只有：

```
MEDIUM
```

---

# 17. Agent Suitability

可以定義：

```
AgentSuitability =
(Parallelism × Verifiability × Specialization)
/
(ContextCoupling × CoordinationCost)
```

不需要把它實作成精確數學模型。

第一版可以使用 heuristic。

---

# 18. Delegation Matrix


| Task                   | Parallel | Context Coupling | Verification | Recommendation |
| ---------------------- | -------- | ---------------- | ------------ | -------------- |
| Research               | High     | Low              | Medium       | Delegate       |
| Code Search            | High     | Low              | High         | Delegate       |
| Documentation Search   | High     | Low              | High         | Delegate       |
| Security Review        | High     | Low              | Medium       | Delegate       |
| Code Review            | High     | Low              | Medium       | Delegate       |
| Test Execution         | High     | Low              | High         | Delegate       |
| Independent Adapter    | Medium   | Medium           | High         | Optional       |
| Unit Test Generation   | Medium   | Medium           | High         | Optional       |
| Feature Implementation | Medium   | High             | High         | Main preferred |
| Cross-module Feature   | Low      | High             | Medium       | Main           |
| Debugging              | Low      | Very High        | Medium       | Main           |
| Architecture Refactor  | Low      | Very High        | Medium       | Main           |
| Integration            | Low      | Very High        | High         | Main           |


---

# 19. Task Graph 的重新定位

原本容易把 Task Graph 理解成：

```
Task
 ↓
Agent Assignment
```

CAI v2 應改成：

```
Task Graph
=
Reasoning
+
Dependency
+
Progress
```

Task 不一定需要 Agent。

例如：

```
A ──→ B ──→ C
          │
          └──→ D
```

可以全部：

```
Main
```

執行。

只有 D 符合 delegation policy：

```
D → Subagent
```

---

# 20. Proposed Task Schema

```
id: task-004

title: implement OAuth adapter

type: implementation

dependencies:
  - task-002

context_coupling: medium

parallelizability: medium

verifiability: high

risk: low

execution:
  preferred: main
  delegation_allowed: true

scope:
  - src/auth/google.py

definition_of_done:
  - callback implemented
  - tests pass

verification:
  - pytest tests/auth/test_google.py
```

---

# 21. Main-first Build Strategy

目前 `/cai:build` 應從：

```
Decompose
    ↓
Delegate implementation
```

改成：

```
Understand Design
      ↓
Build Task Graph
      ↓
Evaluate Task
      ↓
┌───────────────┐
│ Delegate?     │
└───────┬───────┘
        │
   ┌────┴────┐
   │         │
  NO        YES
   │         │
 Main      Worker
   │         │
   └────┬────┘
        ↓
     Evidence
        ↓
      Main
```

預設：

```
execution = main
```

而不是：

```
execution = subagent
```

---

# 22. `/cai:design` 反而可以增加 Parallel Agent

Design / Research 是 Multi-Agent 更適合的位置。

例如：

```
/cai:design OAuth
```

可以：

```
                    Main
                     │
       ┌─────────────┼─────────────┐
       ↓             ↓             ↓
   Explorer       Architect     Researcher
       │             │             │
 existing code    design A     external docs

       └─────────────┼─────────────┘
                     ↓
                   Main
                     ↓
                 Synthesis
                     ↓
                  Design
```

---

# 23. Architecture Arena

對重大設計問題：

```
Main
 │
 ├─ Architect A
 │
 ├─ Architect B
 │
 └─ Architect C
```

三者不互相看答案。

最後：

```
Main
 ↓
Compare
 ↓
Decision
```

這類 parallel reasoning 的價值通常高於 parallel implementation。

---

# 24. `/cai:discover`

Discover 是 CAI 最適合 Multi-Agent 化的部分之一。

可以：

```
                 Discover
                    │
       ┌────────────┼────────────┐
       │            │            │
    Codebase      Docs       Dependency
    Explorer     Research      Explorer
       │            │            │
       └────────────┼────────────┘
                    ↓
               Discovery Map
                    ↓
                   Main
```

---

# 25. `/cai:verify`

Verification 也是非常適合 Multi-Agent 的地方。

因為 Reviewer 的：

```
Context Independence
```

有時是優點。

可以避免：

```
Implementation Anchoring
```

架構：

```
                     DIFF
                      │
       ┌──────────────┼──────────────┐
       ↓              ↓              ↓
 Correctness       Security       Regression
 Reviewer          Reviewer        Reviewer
       │              │              │
       └──────────────┼──────────────┘
                      ↓
                  Findings
                      ↓
                    Main
```

---

# 26. Verification-Aware Planning

Task 在建立時就應定義：

```
How will we know this is correct?
```

而不是 implementation 完成後才想 verification。

例如：

```
task: add token refresh

definition_of_done:
  - expired token refreshes
  - invalid refresh token rejected

verification:
  commands:
    - pytest tests/auth/test_refresh.py

  expected:
    tests_pass: true
```

這與 VeriMAP 的 Verification-Aware Planning 概念一致。

---

# 27. Evidence-first Verification

Subagent 不應回：

```
Done.
```

而應回：

```
task: task-004

changes:
  files:
    - src/auth/google.py

verification:
  command:
    pytest tests/auth/test_google.py

  result:
    passed: 12
    failed: 0

commit:
  abc123
```

Main Agent 接收的是：

# Evidence

不是：

# Agent Confidence

---

# 28. Main 不應重新完整 Verify

目前常見問題：

```
Worker
 ↓
Implement
 ↓
Verify
 ↓
Main
 ↓
Read everything again
 ↓
Run everything again
```

等於：

```
duplicated work
```

應改為：

```
Worker
 ↓
Implementation
 ↓
Deterministic Verification
 ↓
Independent Reviewer
 ↓
Evidence
 ↓
Main Decision
```

Main 只在：

```
high risk
conflicting evidence
integration issue
low confidence
```

時進行 deeper verification。

---

# 29. Evidence Store

新增：

```
.cai/track/<feature>/evidence/
```

例如：

```
evidence/
├── task-001/
│   ├── result.yaml
│   ├── tests.txt
│   └── diff-summary.md
│
├── task-002/
│   └── ...
```

---

# 30. Evidence Manifest

```
task: task-001

implementation:
  actor: main

verification:
  pytest:
    status: pass

  lint:
    status: pass

review:
  correctness:
    status: pass

risk:
  low

accepted:
  true
```

---

# 31. Dynamic Reasoning Context

新增：

```
.cai/track/<feature>/context/
```

結構：

```
context/
├── current.md
├── digest.md
├── decisions.md
├── discoveries.md
├── failures.md
└── constraints.md
```

---

# 32. [current.md](http://current.md)

只保存近期 working state：

```
# Current State

Current task:
task-004

Current hypothesis:
OAuth refresh race originates in token cache update.

Files currently relevant:
- auth/token.py
- auth/cache.py

Next action:
inspect cache invalidation.
```

---

# 33. [digest.md](http://digest.md)

保存壓縮後歷史 reasoning：

```
# Reasoning Digest

## Architecture

AuthProvider owns token lifecycle.

## Important discoveries

Token cache is shared across requests.

## Rejected hypotheses

Database transaction isolation is not the cause.

## Previous failures

Adding retry did not solve race condition.
```

---

# 34. Decision Records

新增：

```
decisions/
```

例如：

```
decision-003.md
```

內容：

```
decision:
  use per-user token lock

reason:
  prevents concurrent refresh

alternatives_rejected:
  - global lock
  - retry loop
```

重要決策不能只存在 conversation context。

---

# 35. Context Compaction

當 context 達到 threshold：

```
Detailed History
       ↓
Context Compactor
       ↓
Reasoning Digest
```

保留：

```
decisions
discoveries
constraints
failures
open questions
```

捨棄：

```
raw logs
duplicate reasoning
obsolete hypotheses
repeated tool output
```

---

# 36. Context Layers

CAI v2 建議三層 context：

```
L1 — Project Context

CLAUDE.md
architecture
codemap
rules
```

```
L2 — Track Context

goal
design
decisions
reasoning digest
```

```
L3 — Working Context

current task
recent files
recent reasoning
current diff
```

---

# 37. Context Pack

Subagent 仍可以使用 Context Pack。

但只在：

```
bounded task
```

使用。

例如：

```
goal:
  inspect authentication security

scope:
  - src/auth/

relevant_context:
  - auth uses JWT
  - refresh token stored server-side

task:
  identify security vulnerabilities

output:
  findings only
```

---

# 38. Subagent Output Contract

Subagent output 必須：

```
Structured
Bounded
Evidence-backed
```

避免：

```
long conversational handoff
```

推薦：

```
status: complete

findings:
  - id: SEC-01
    severity: major
    file: auth/token.py
    line: 87

evidence:
  - test output
```

---

# 39. Artifact-based Communication

Agent 不應大量互相聊天：

```
Agent A
 ↔
Agent B
 ↔
Agent C
```

應透過：

```
Artifact
Evidence
Task State
Decision Record
```

溝通。

例如：

```
Explorer
   ↓
discovery.md
   ↓
Main
```

---

# 40. Avoid Agent Chat Mesh

禁止設計：

```
A ↔ B
↕   ↕
C ↔ D
```

原因：

```
communication complexity
context duplication
error propagation
token cost
```

Centralized coordination 比 peer mesh 更容易控制。

---

# 41. Deterministic Before Agentic

CAI 目前已有 deterministic scripts。

這個方向應進一步強化。

任何可以用：

```
Python
AST
Git
pytest
lint
type checker
schema
regex
compiler
```

判斷的事情：

# 不要交給 LLM。

---

# 42. Deterministic Scheduler

新增：

```
scheduler.py
```

負責：

```
task readiness
dependency resolution
parallel-safe detection
resource limit
conflict detection
```

LLM 不負責：

```
while task unfinished:
    guess what runs next
```

---

# 43. Delegation Policy Engine

新增：

```
delegation.py
```

輸入：

```
task type
parallelizability
context coupling
verifiability
risk
scope overlap
estimated context cost
```

輸出：

```
MAIN
DELEGATE
PARALLEL_REVIEW
ARENA
```

---

# 44. Example Policy

```
IF context_coupling == VERY_HIGH
    → MAIN

IF parallelizability == LOW
    → MAIN

IF type == research
    → DELEGATE

IF type == review
    → PARALLEL_REVIEW

IF type == architecture
   AND alternatives > 1
    → ARENA
```

---

# 45. No Mandatory Agent Count

CAI 不應設定：

```
minimum_agents = 4
```

最佳結果完全可能是：

```
agents_spawned = 0
```

例如：

```
fix race condition
```

如果：

```
context coupling = very high
parallelism = low
```

Main Agent 自己處理就是正確策略。

---

# 46. Concurrency Budget

即使可以 parallel：

```
max_parallel_agents
```

也應有限制。

第一版建議：

```
parallel:
  research: 4
  review: 4
  implementation: 2
```

這不是研究證明的最佳固定數字，而是保守的工程預設值；之後應由 CAI 自己的 eval data 調整。

---

# 47. Model Routing

保留目前：

```
think
build
chore
```

模型 tier。

但增加：

```
Task Complexity
Risk
Context Size
```

作為 routing input。

例如：

```
Mechanical rename
    ↓
chore

Implementation
    ↓
build

Architecture
    ↓
think
```

---

# 48. Escalation

Agent 不應無限 retry。

流程：

```
cheap model
     ↓
failure
     ↓
stronger model
     ↓
failure
     ↓
Main
     ↓
Human
```

---

# 49. Failure Classification

失敗應分類：

```
IMPLEMENTATION_ERROR
ENVIRONMENT_ERROR
DEPENDENCY_ERROR
CONTEXT_MISSING
AMBIGUOUS_REQUIREMENT
ARCHITECTURE_ERROR
TEST_FLAKE
TOOL_ERROR
```

不同 failure 使用不同策略。

---

# 50. Context Missing

特別新增：

```
CONTEXT_MISSING
```

如果 Subagent 發現：

```
required context > supplied context
```

不要自己猜。

回：

```
status: blocked
reason: context_missing

required:
  - lifecycle ownership of AuthSession
```

Main 再決定：

```
expand context
```

或：

```
take task back
```

---

# 51. Worktree Strategy

Git Worktree 不再是所有 Subagent 的預設。

只有：

```
implementation delegation
```

才需要：

```
git worktree
```

Research / Review：

```
read-only
```

不需要 worktree。

---

# 52. Implementation Delegation

只有滿足：

```
bounded scope
clear interface
low-medium coupling
high verifiability
low overlap
```

才允許：

```
Implementation Worker
```

例如：

```
Implement S3 adapter
```

可能適合。

但：

```
Refactor authentication architecture
```

不適合。

---

# 53. `/cai:build` v2

```
/cai:build
      │
      ▼
Load Track Context
      │
      ▼
Build Task Graph
      │
      ▼
Task Analysis
      │
      ▼
Delegation Policy
      │
 ┌────┴─────────┐
 │              │
MAIN         DELEGATE
 │              │
 │           Worker
 │              │
 └──────┬───────┘
        ▼
   Verification
        │
        ▼
      Evidence
        │
        ▼
       Main
```

---

# 54. `/cai:design` v2

```
Main
 │
 ├── Explorer
 ├── Researcher
 ├── Architect A
 └── Architect B
        │
        ▼
     Artifacts
        │
        ▼
       Main
        │
        ▼
     Synthesis
        │
        ▼
      Design
```

---

# 55. `/cai:verify` v2

```
                  DIFF
                   │
      ┌────────────┼────────────┐
      ▼            ▼            ▼
Correctness     Security     Regression
      │            │            │
      └────────────┼────────────┘
                   ▼
               Evidence
                   │
                   ▼
                  Main
```

---

# 56. `/cai:ship`

Ship 基本上不需要 Multi-Agent。

應保持：

```
Deterministic checks
        ↓
Release preparation
        ↓
Human Gate
        ↓
Merge / Tag / Publish
```

---

# 57. Human Gate

保留目前兩個重要 gate：

```
Design Approval
```

以及：

```
Irreversible Ship Approval
```

增加 Risk-based Gate：

```
LOW
    → automatic

MEDIUM
    → evidence required

HIGH
    → explicit approval

CRITICAL
    → human execution
```

---

# 58. Proposed Track v2

```
.cai/track/<feature>/

├── state.yaml
├── goal.yaml
├── design.md
│
├── context/
│   ├── current.md
│   ├── digest.md
│   ├── discoveries.md
│   ├── failures.md
│   └── constraints.md
│
├── tasks/
│   ├── graph.yaml
│   ├── task-001.yaml
│   └── task-002.yaml
│
├── decisions/
│   └── decision-001.md
│
├── evidence/
│   └── task-001/
│
└── ledger.jsonl
```

---

# 59. Ledger

保留 append-only ledger。

新增 events：

```
TASK_CREATED
TASK_STARTED
TASK_DELEGATED
TASK_COMPLETED

CONTEXT_COMPACTED

AGENT_STARTED
AGENT_FINISHED

VERIFY_STARTED
VERIFY_PASSED
VERIFY_FAILED

HUMAN_REQUIRED

DECISION_RECORDED
```

---

# 60. Event-driven Execution

避免：

```
Main polling agents
```

改成：

```
TASK_READY
   ↓
scheduler
   ↓
execution
   ↓
TASK_COMPLETED
```

---

# 61. Proposed New Components

```
plugins/cai/scripts/

task_graph.py
scheduler.py
delegation.py
context_manager.py
evidence.py
policy.py
events.py
```

---

# 62. `task_[graph.py](http://graph.py)`

負責：

```
task dependency
cycle detection
ready task
blocked task
completion
```

---

# 63. `context_[manager.py](http://manager.py)`

負責：

```
working context
reasoning digest
context compaction
context pack
decision extraction
```

這會是 CAI v2 最重要的新 component。

---

# 64. [`delegation.py`](http://delegation.py)

負責：

```
Should this task leave Main?
```

輸出：

```
MAIN
SUBAGENT
PARALLEL
ARENA
```

---

# 65. [`evidence.py`](http://evidence.py)

統一：

```
tests
lint
review
benchmark
security
artifact
```

格式。

---

# 66. [`policy.py`](http://policy.py)

輸入：

```
risk
evidence
verification
trust
```

輸出：

```
AUTO_CONTINUE
REVIEW
HUMAN_APPROVAL
BLOCK
```

---

# 67. Agent Roles

保留目前已有的 specialized agents。

CAI v2 不需要建立大量新的 Manager Agent。

推薦核心角色：

```
Main Session

Explorer
Architect
Designer
Implementer
Reviewer
Security Reviewer
Test Runner
Verifier
Shipper
```

新增 Agent 應非常保守。

---

# 68. 不建議 Chief Orchestrator Agent

前一版設計中的：

```
chief-orchestrator.md
```

不再是優先項目。

因為 Main Session 本身已經是：

```
Context Owner
Decision Owner
Integration Owner
```

再建立 Chief Agent 反而可能：

```
Main
 ↓
Chief
 ↓
Worker
```

增加一次 context handoff。

---

# 69. Orchestration 應該主要是 Runtime Capability

Orchestration 不應只是一個 prompt。

應由：

```
task_graph.py
scheduler.py
delegation.py
context_manager.py
policy.py
```

提供。

Agent 負責：

```
judgment
reasoning
```

Runtime 負責：

```
state
dependency
scheduling
limits
evidence
```

---

# 70. Agent Viewer v2

Viewer 可以增加：

```
Current Main Context

Task Graph

Delegated Tasks

Evidence

Agent Cost

Context Usage

Reasoning Digest

Human Attention
```

---

# 71. Human Attention Queue

Viewer 最重要的新區域：

```
Needs You
```

只顯示：

```
ambiguous requirement
high-risk decision
failed verification
conflicting architecture
irreversible action
```

不要讓 Human 監控 Agent。

---

# 72. Metrics

不要使用：

```
Number of Agents
```

當成功指標。

應測：

```
Task Success Rate

Human Intervention Rate

Verification Failure Rate

Retry Rate

Context Reconstruction Rate

Duplicate File Read Rate

Re-verification Rate

Merge Conflict Rate

Token Cost

Wall Clock Time
```

---

# 73. 最重要的 Efficiency Metrics

推薦：

```
Verified Output / Token
```

以及：

```
Human Minutes / Completed Task
```

---

# 74. Delegation Metrics

新增：

```
Delegated Task Success Rate

Delegation Rollback Rate

Context Missing Rate

Delegation Cost vs Main Estimate
```

用實際數據逐漸調整 delegation policy。

---

# 75. Context Metrics

新增：

```
Context Size

Compaction Frequency

Digest Reuse

Repeated File Reads

Repeated Reasoning

Context Missing Events
```

這可能比 Agent Count 更值得最佳化。

---

# 76. Evaluation

建立 benchmark：

```
evals/context/
evals/delegation/
evals/verification/
```

---

# 77. Delegation Eval

同一 Task 比較：

```
Main-only
```

vs

```
Main + Subagent
```

測：

```
quality
tokens
latency
retries
verification
human intervention
```

---

# 78. Context Eval

比較：

```
Full History
```

vs

```
Dynamic Context
```

vs

```
Digest + Recent Window
```

測：

```
task success
token usage
repeated reasoning
```

---

# 79. Research Eval

Research 可以測：

```
1 Explorer
2 Explorers
4 Explorers
```

觀察 marginal gain。

不要假設：

```
8 > 4
```

---

# 80. Verification Eval

測：

```
Main Review

vs

Independent Reviewer

vs

Parallel Reviewers
```

比較 defect detection / token。

---

# 81. Implementation Eval

尤其重要：

```
Main implementation

vs

1 worker

vs

2 workers
```

CAI 應用自己的 repository benchmark 找到：

```
delegation crossover point
```

---

# 82. Migration Plan

不建議一次重寫 CAI。

---

## Phase 1 — Context Layer

先建立：

```
context_manager.py

context/
  current.md
  digest.md
  decisions.md
```

目標：

```
reduce repeated reasoning
```

---

## Phase 2 — Evidence Layer

建立：

```
evidence.py
```

統一：

```
tests
review
lint
security
```

輸出。

---

## Phase 3 — Task Graph

建立：

```
task_graph.py
```

但：

> Task Graph 不代表 Agent Graph。

Task 預設由 Main 執行。

---

## Phase 4 — Delegation Policy

建立：

```
delegation.py
```

開始自動判斷：

```
MAIN
SUBAGENT
PARALLEL_REVIEW
ARENA
```

---

## Phase 5 — Research / Design Parallelism

先在：

```
discover
design
review
```

導入 Multi-Agent。

這些位置風險最低、收益最可能為正。

---

## Phase 6 — Selective Implementation Delegation

最後才允許：

```
implementation subagent
```

而且限定：

```
bounded
isolated
verifiable
low coupling
```

---

# 83. 不建議的 Migration Order

不要：

```
Phase 1
Chief Orchestrator

Phase 2
50 Workers

Phase 3
Worktrees

Phase 4
Verification
```

這會先產生 coordination complexity，再補 infrastructure。

---

# 84. 推薦順序

```
Context
   ↓
Evidence
   ↓
Task Graph
   ↓
Delegation Policy
   ↓
Parallel Research / Review
   ↓
Selective Parallel Coding
```

---

# 85. CAI v2 的核心公式

CAI v1 可以理解為：

```
Agentic SDLC
=
Stages
+ Agents
+ Skills
+ Guards
```

CAI v2 應該成為：

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

---

# 86. 最終架構

```
flowchart TB

    U[User] --> M[Main Session]

    M --> G[Goal / Intent]
    G --> CTX[Context Manager]

    CTX --> TG[Task Graph]

    TG --> DA[Delegation Analysis]

    DA -->|High Context Coupling| MAIN[Main Execution]

    DA -->|Research| EXP[Explorer]

    DA -->|Architecture Alternatives| ARENA[Architecture Arena]

    DA -->|Review| REV[Parallel Reviewers]

    DA -->|Bounded Implementation| IMP[Implementation Worker]

    EXP --> ART[Artifacts]
    ARENA --> ART
    REV --> ART
    IMP --> ART

    MAIN --> VERIFY[Deterministic Verification]
    ART --> VERIFY

    VERIFY --> EVID[Evidence Store]

    EVID --> POLICY[Risk / Evidence Policy]

    POLICY -->|Accept| M
    POLICY -->|Need Context| CTX
    POLICY -->|High Risk| HUMAN[Human Gate]

    M --> SHIP[Ship]

    SHIP --> HUMAN
```

---

# 87. 最重要的 Architecture Decision

CAI v2 最重要的 architecture decision 不應該是：

> How do we run 50 agents?

而應該是：

> **Where should context live, and when is it economically and cognitively beneficial to move work outside that context?**

因此：

```
Main Agent
=
Persistent Strategic Context
```

而：

```
Subagent
=
Ephemeral Specialized Compute
```

---

# 88. Final Recommendation

CAI 下一階段最值得先做的不是：

```
Chief Orchestrator
```

也不是：

```
Swarm
```

更不是：

```
50-Agent Runtime
```

第一優先：

# Dynamic Context Layer

```
current context
+
reasoning digest
+
decision records
+
failure memory
```

第二優先：

# Evidence Layer

第三優先：

# Task Graph

第四優先：

# Adaptive Delegation

最後才是：

# Selective Multi-Agent Implementation

這個順序最大的優點是：

即使最後實驗證明：

```
implementation subagents
```

幾乎沒有價值，

前面建立的：

```
Context Management
Evidence
Task Graph
Verification
Decision Records
```

仍然全部對 Single-Agent CAI 有價值。

因此這是一條低風險的演進路徑。

---

# 89. Design Principles

最終可以將 CAI v2 的設計原則濃縮為：

1. **Context before Agents**
2. **Main owns strategic context**
3. **Delegation is optional**
4. **Parallelize exploration before implementation**
5. **Task Graph ≠ Agent Graph**
6. **Evidence over Agent confidence**
7. **Verification is designed before implementation**
8. **Deterministic before probabilistic**
9. **Artifacts over agent-to-agent conversation**
10. **Compress history, preserve decisions**
11. **High-coupling work stays in Main**
12. **Independent review is valuable**
13. **No unlimited retries**
14. **Risk determines autonomy**
15. **Measure verified output, not agent count**

---

# 90. References

## Google Research — Scaling Agent Systems

Google Research, *Towards a science of scaling agent systems: When and why agent systems work*, 2026.

主要結論：

- controlled evaluation of 180 agent configurations
- Multi-Agent 對 parallelizable tasks 有利
- sequential tasks 可能因 Multi-Agent coordination 而退化
- Agent 數量增加存在 diminishing returns
- centralized coordination 在可靠性上優於無協調的 independent agents

Source:

[https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/)

---

## Anthropic — Multi-Agent Research System

Anthropic Engineering, *How we built our multi-agent research system*, 2025.

主要結論：

- Orchestrator-worker 適合高度平行化 Research
- Multi-Agent 可以利用多個 context window 擴充 inference compute
- Multi-Agent token consumption 顯著高於一般 interaction
- Coding task 通常比 Research 更少真正可平行工作
- Agent 之間大量 context dependency 時不適合 Multi-Agent
- Artifact-based handoff 可以降低資訊在 coordinator 間傳遞造成的損失

Source:

[https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

---

## SWE-AGILE — Dynamic Reasoning Context

Lian, Liu, Chen, Chen, Li.

*SWE-AGILE: A Software Agent Framework for Efficiently Managing Dynamic Reasoning Context.*

Findings of ACL 2026.

主要結論：

- Full reasoning history 造成 context explosion
- 丟棄 reasoning history 造成 redundant re-reasoning
- 使用 sliding reasoning window
- 歷史 reasoning 壓縮成 Reasoning Digest
- Dynamic Reasoning Context 可平衡 continuity 與 context efficiency

Source:

[https://aclanthology.org/2026.findings-acl.868/](https://aclanthology.org/2026.findings-acl.868/)

---

## VeriMAP — Verification-Aware Planning

Xu, Zhang, Mitra, Hruschka.

*Verification-Aware Planning for Multi-Agent Systems.*

EACL 2026.

主要結論：

- Multi-Agent failure 不只來自 reasoning error
- task interpretation、handoff、output mismatch 都會造成失敗
- Planning 階段應同時定義 verification criteria
- Subtask dependency 與 passing criteria 應一起建模

Source:

[https://aclanthology.org/2026.eacl-long.353/](https://aclanthology.org/2026.eacl-long.353/)

---

## CodeDelegator — Context Pollution

Fei, Chen, Pan, Zheng, Song.

*CodeDelegator: Mitigating Context Pollution via Role Separation in Code-as-Action Agents.*

IJCAI 2026.

主要結論：

- 單一長時間 Agent 同時維持 strategy 與 implementation 會產生 context pollution
- Persistent Delegator 應保留 strategic context
- Ephemeral Coder 可以隔離 implementation/debugging noise
- Persistent / Ephemeral State Separation 可避免 execution history 污染高階 reasoning

Source:

[https://ijcai.org/proceedings/2026/12](https://ijcai.org/proceedings/2026/12)

---

## Google Cloud — Agentic AI Design Patterns

Google Cloud Architecture Center.

*Choose a design pattern for your agentic AI system.*

主要結論：

- Sequential workflow 適合固定且 deterministic 的流程
- Parallel workflow 適合真正 independent 的 subtasks
- Parallelism 會增加 resource、token 與 synthesis complexity
- 不需要 LLM 判斷的 orchestration 應優先使用 deterministic workflow

Source:

[https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system)

---

# 91. Closing Architecture Statement

Claude All-in-One 不應演進成：

```
A system that runs as many agents as possible.
```

而應演進成：

```
A system that intelligently decides
where reasoning should live,
when work should be delegated,
how results should be verified,
and when humans should intervene.
```

因此 CAI v2 的定位建議正式改為：

# Context-Centric Adaptive Agentic SDLC Runtime

核心不是：

```
Multi-Agent
```

而是：

```
Right Context
    +
Right Agent
    +
Right Verification
    +
Right Autonomy
```

最終目標不是：

```
More Agents
```

而是：

```
Less Repeated Reasoning
Less Context Reconstruction
Less Human Supervision
Less Verification Duplication
More Verified Software Output
```