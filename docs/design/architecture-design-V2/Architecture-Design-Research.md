# CAI v2 補充設計

## Main Session 與 Subagent Context Handoff Architecture

**版本：** Draft v1  
**日期：** 2026-10-30  
**適用專案：** `millerlai/claude-all-in-one`

---

# 1. 核心結論

在 Claude Code 中，一般 Subagent 不應被理解成：

```
Main Session
    │
    │ Copy Full Context
    ▼
Subagent
```

更接近：

```
                 Main Session
              Full Working Context
                     │
                     │ Task Handoff
                     ▼
              ┌───────────────┐
              │ Task Prompt   │
              │ Constraints   │
              │ Scope         │
              │ Known Facts   │
              └───────┬───────┘
                      │
                      ▼
                Fresh Subagent
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
      CLAUDE.md    Repository    Tools
                      │
                      ▼
               Rebuild Context
                      │
                      ▼
                 Execute Task
                      │
                      ▼
             Result / Evidence
                      │
                      ▼
                 Main Session
```

因此 Main Session 與 Subagent 之間最重要的問題不是：

> 如何把 Main Session 的完整 Context 複製給 Subagent？

而是：

> **如何只傳遞完成 Task 所需要的 Context，同時避免遺失重要資訊？**

這應成為 CAI v2 的核心架構問題之一。

---

# 2. Main Session 的角色

CAI v2 將 Main Session 定義為：

```
Main Session
=
Context Owner
+
Decision Owner
+
Integration Owner
```

Main Session 維護的是：

```
User Intent
Architecture
Constraints
Previous Decisions
Current Hypothesis
Previous Failures
Rejected Alternatives
Implementation State
Integration State
Risk
```

這些資訊共同形成：

# Strategic Working Context

Subagent 不應預設擁有完整 Strategic Working Context。

---

# 3. Subagent 的角色

Subagent 定位為：

# Ephemeral Specialized Compute

而不是：

# Persistent Project Owner

其生命週期：

```
Task Created
     ↓
Context Supplied
     ↓
Subagent Started
     ↓
Acquire Additional Context
     ↓
Execute
     ↓
Produce Evidence
     ↓
Return Result
     ↓
Terminate
```

因此 Subagent 最適合：

- bounded task
- independent research
- code search
- documentation research
- security review
- code review
- test execution
- benchmark
- isolated implementation

而不適合：

- complex debugging
- architecture migration
- cross-module refactor
- highly stateful implementation
- heavily history-dependent reasoning

---

# 4. Context Handoff 本質

假設 Main 已經累積：

```
C_main
```

其中可能包含數萬 tokens：

```
C_main =
User Conversation
+ Tool Results
+ Files Read
+ Architecture Understanding
+ Decisions
+ Failed Attempts
+ Current Hypothesis
```

Main 不會也不應把：

```
C_main
```

完整交給每個 Subagent。

而是產生：

```
C_sub = H(C_main, Task)
```

其中：

```
H
=
Context Handoff Function
```

目標是：

```
C_sub << C_main
```

但仍滿足：

```
Information(C_sub)
>=
InformationRequired(Task)
```

---

# 5. Context Handoff 是 Lossy Compression

這個轉換：

```
Full Main Context
        ↓
Context Selection
        ↓
Subagent Context
```

本質上是一種：

# Lossy Compression

因為 Main 必須判斷：

> 哪些資訊對 Subagent 是重要的？

例如 Main 已知：

```
User Constraint:
Public API cannot change.

Architecture:
TokenManager owns token lifecycle.

Previous Attempt:
Retry-based solution failed.

Compatibility:
Redis schema must remain backward compatible.
```

如果只傳：

```
Investigate OAuth refresh race condition.
```

Subagent 很可能重新提出：

```
Add retry logic.
```

這不是 Subagent reasoning 能力不足。

而是：

# Missing Context

---

# 6. Context Reconstruction Cost

當 Subagent 沒有足夠 Context 時，它必須：

```
Read CLAUDE.md
      ↓
Search Repository
      ↓
Read Files
      ↓
Trace References
      ↓
Infer Architecture
      ↓
Reconstruct Mental Model
```

產生：

# Context Reconstruction Cost

因此：

```
Delegation Cost
=
Execution Cost
+
Context Reconstruction Cost
+
Coordination Cost
+
Verification Cost
```

不能只比較：

```
Main Coding Time

vs

Subagent Coding Time
```

---

# 7. Context Transfer Cost

另一方面，如果 Main 傳太多資訊：

```
Main Context
      ↓
Huge Context Pack
      ↓
Subagent
```

也會產生：

# Context Transfer Cost

包含：

```
Token Cost
Context Noise
Attention Dilution
Redundant Information
```

因此目標不是：

```
More Context
```

而是：

```
Minimum Sufficient Context
```

---

# 8. Minimum Sufficient Context

CAI 應尋找：

```
C_min
```

使：

```
C_min ⊆ C_main
```

而：

```
C_min
```

足以讓 Subagent 正確完成 Task。

理想狀態：

```
Context Size
     ↑

Too Much
   │
   │   Context Noise
   │
Optimal ────────── Minimum Sufficient Context
   │
   │   Missing Context
   │
Too Little
   └────────────────────────────→
```

---

# 9. Project Context 與 Session Context

必須區分兩種資訊。

## Project Context

可以透過 repository 重新取得：

```
CLAUDE.md
Architecture Docs
Code
Tests
Codemap
Rules
Track Artifacts
```

這些資訊：

```
Main
 │
 ├─────────┐
 ▼         ▼
Agent A   Agent B
```

都可以存取。

---

## Session Context

只存在 Main Session reasoning history：

```
User clarification
Recent discovery
Rejected hypothesis
Why decision X was made
Temporary assumption
Current debugging hypothesis
Previous failed attempt
```

這些資訊通常無法單靠重新讀 repository 完整重建。

因此：

> **重要的 Session Context 應逐步 Artifact 化。**

---

# 10. Context Externalization

CAI v2 應把重要 Context 從：

```
Conversation-only State
```

轉換為：

```
Persistent Artifact
```

例如：

```
.cai/track/<feature>/

context/
decisions/
discoveries/
evidence/
tasks/
```

讓：

```
Main Session
```

與：

```
Subagent
```

都能取得。

---

# 11. Proposed Context Architecture

```
.cai/track/<feature>/

├── state.yaml
├── goal.yaml
├── design.md
│
├── context/
│   ├── current.md
│   ├── digest.md
│   ├── constraints.md
│   ├── discoveries.md
│   └── failures.md
│
├── decisions/
│   ├── decision-001.md
│   └── decision-002.md
│
├── tasks/
│   ├── graph.yaml
│   └── task-001.yaml
│
├── evidence/
│   └── task-001/
│
└── ledger.jsonl
```

---

# 12. Context Layer

## [`current.md`](http://current.md)

保存目前正在處理的狀態：

```
# Current State

Current task:
AUTH-004

Current hypothesis:
Concurrent refresh requests overwrite shared cache state.

Relevant files:
- auth/token.py
- auth/cache.py

Next action:
Trace cache invalidation lifecycle.
```

---

# 13. Reasoning Digest

[`digest.md`](http://digest.md) 保存壓縮後的歷史：

```
# Reasoning Digest

## Architecture

TokenManager owns token lifecycle.

## Important Discoveries

Refresh token cache is shared across concurrent requests.

## Rejected Hypotheses

Database isolation is not responsible.

## Failed Approaches

Retry logic did not eliminate the race.
```

它的目的不是保存完整 Chain-of-Thought。

而是保存：

```
Decisions
Facts
Discoveries
Constraints
Failures
Open Questions
```

---

# 14. Constraints

[`constraints.md`](http://constraints.md)：

```
# Constraints

- Public API cannot change.
- Redis schema must remain backward compatible.
- Existing authentication clients must continue working.
```

這些資訊非常適合 Subagent 使用。

---

# 15. Decision Records

重要決策不能只存在 conversation。

例如：

```
decisions/
└── decision-002-token-owner.md
```

內容：

```
# Decision: Token Lifecycle Ownership

TokenManager remains responsible for refresh-token lifecycle.

## Reason

Moving lifecycle management into AuthService would introduce
cross-layer coupling.

## Rejected Alternatives

- AuthService directly accesses Redis.
- Global refresh lock.
```

---

# 16. Discovery Records

Explorer 找到的重要資訊：

```
discoveries.md
```

例如：

```
## AUTH-DISC-003

`TokenManager.refresh()` can execute concurrently for the same user.

Evidence:

- auth/token.py:87
- auth/cache.py:42

Shared state:

`refresh_token_cache`
```

如此其他 Agent 不必重新搜尋。

---

# 17. Failure Memory

失敗也是 Context。

例如：

```
# Failed Attempts

## Retry-based refresh

Result:
Race condition still reproduced under concurrent requests.

Reason:
Retry occurs after shared state has already been overwritten.

Evidence:
evidence/auth-retry-test.txt
```

避免：

```
Agent A tries solution X
        ↓
fails
        ↓
Agent B doesn't know
        ↓
tries solution X again
```

---

# 18. Context Handoff Protocol

CAI v2 應正式建立：

# Context Handoff Protocol

流程：

```
Main Context
      ↓
Task Analysis
      ↓
Context Selection
      ↓
Task Contract
      ↓
Subagent
      ↓
Evidence Artifact
      ↓
Result Contract
      ↓
Main
```

---

# 19. Task Contract

Main 不應只傳：

```
Investigate OAuth issue.
```

而應建立：

```
task:
  id: AUTH-004
  type: investigation

goal:
  identify root cause of concurrent token refresh race

scope:
  files:
    - auth/token.py
    - auth/cache.py

known_facts:
  - TokenManager owns token lifecycle
  - refresh cache is shared

constraints:
  - public API cannot change
  - Redis schema must remain compatible

rejected_approaches:
  - retry-based fix

references:
  - .cai/track/oauth/context/digest.md
  - .cai/track/oauth/decisions/decision-002.md

permissions:
  write: false

output:
  type: findings

verification:
  require_file_references: true
```

---

# 20. Task Contract 的目的

Task Contract 回答：

```
WHAT
WHY
WHERE
CONSTRAINTS
KNOWN FACTS
WHAT NOT TO DO
WHAT TO RETURN
```

而不是把整段 Main conversation 傳給 Subagent。

---

# 21. Context Reference 優於 Context Duplication

如果資訊已存在：

```
.cai/track/oauth/context/digest.md
```

不要：

```
copy 3000 tokens into prompt
```

而是：

```
Read:

.cai/track/oauth/context/digest.md
```

形成：

```
Task Prompt
    ↓
References
    ↓
Persistent Artifacts
```

這樣可以：

- 減少 prompt size
- 避免 duplicate context
- 建立 single source of truth
- 讓多個 Agent 使用同一份 Context

---

# 22. Lazy Context Loading

Subagent 不需要一開始讀全部資料。

推薦：

```
Task Contract
      ↓
Minimum Context
      ↓
Start Work
      ↓
Need More Context?
   ┌───────┴───────┐
   NO              YES
   │                │
Continue       Load Reference
```

稱為：

# Lazy Context Loading

---

# 23. Context Expansion

如果 Subagent 發現資訊不足：

不要猜。

回：

```
status: blocked

reason:
  context_missing

required_context:
  - ownership of AuthSession lifecycle

why:
  cannot determine whether lock belongs in TokenManager or AuthSession
```

Main 可以：

```
Expand Context
```

或：

```
Take Task Back
```

---

# 24. Context Expansion Protocol

```
Subagent
    │
    │ CONTEXT_MISSING
    ▼
Main
    │
    ├── provide artifact
    │
    ├── provide additional constraint
    │
    └── terminate delegation
```

這比 Subagent自行推測安全。

---

# 25. Result Handoff

Context Loss 不只發生：

```
Main → Subagent
```

也發生：

```
Subagent → Main
```

例如 Subagent 花：

```
20K tokens
```

完成 investigation。

最後只回：

```
Race condition is in TokenManager.
```

大量資訊又消失。

因此需要：

# Result Contract

---

# 26. Result Contract

推薦：

```
task:
  id: AUTH-004

status:
  complete

summary:
  concurrent refresh requests overwrite shared cache state

findings:

  - id: AUTH-F01

    location:
      file: auth/token.py
      line: 87

    finding:
      refresh operation is not serialized per user

    evidence:
      - auth/cache.py:42

confidence:
  high

open_questions:
  - whether distributed locking is required

recommended_next_step:
  evaluate per-user lock ownership
```

---

# 27. Evidence 不應只存在 Prompt

重要結果應寫成：

```
evidence/
```

例如：

```
evidence/AUTH-004/

├── result.yaml
├── findings.md
├── test-output.txt
└── references.txt
```

Main 可以讀摘要。

需要深入時才讀 Evidence。

---

# 28. Artifact-based Communication

推薦：

```
Agent
 ↓
Artifact
 ↓
Main
```

而不是：

```
Agent
 ↓
Long Chat Message
 ↓
Main
```

Artifact 有：

```
Persistent
Inspectable
Reusable
Verifiable
Addressable
```

等優點。

---

# 29. Agent-to-Agent Communication

避免：

```
Agent A ↔ Agent B
   ↕         ↕
Agent C ↔ Agent D
```

因為會產生：

```
Context Duplication
Communication Cost
Inconsistent State
Error Propagation
```

推薦：

```
          Main
           │
     ┌─────┼─────┐
     ↓     ↓     ↓
     A     B     C
     │     │     │
     ▼     ▼     ▼
   Artifact Store
           │
           ▼
          Main
```

---

# 30. Shared Context 不代表 Shared Conversation

CAI 應追求：

```
Shared Persistent Context
```

而不是：

```
Shared Conversation History
```

差別：

```
Conversation History
=
Verbose
Temporal
Noisy
Reasoning-heavy
```

而：

```
Persistent Context
=
Structured
Compressed
Relevant
Reusable
```

---

# 31. Claude Code Context Modes

CAI 可以進一步抽象三種 execution context。

---

## Mode 1 — Main

```
execution_context: main
```

使用：

```
Main Working Context
```

適合：

- debugging
- integration
- architecture migration
- cross-module implementation
- history-dependent reasoning

---

## Mode 2 — Fresh Subagent

```
execution_context: fresh
```

使用：

```
Task Contract
+
Project Context
+
Referenced Artifacts
+
Repository
```

適合：

- research
- exploration
- review
- security
- testing
- bounded implementation

---

## Mode 3 — Forked Context

概念：

```
execution_context: fork
```

適合：

```
需要大量目前 Main Context
但希望獨立探索
```

可以理解為：

```
Main Context
      │
      ├─────────── Fork
      │              │
      │              ▼
      │          Exploration
      │
      ▼
Continue Main
```

這個模式的具體可用能力應依 Claude Code 當前版本與官方 API/CLI 行為決定，不應假設所有 Subagent 都支援完整 context fork。

---

# 32. Context Mode Decision

CAI 可以增加：

```
execution:
  context_mode: auto
```

Policy：

```
IF context_coupling == VERY_HIGH
    → MAIN

IF task == research
    → FRESH

IF task == review
    → FRESH

IF task == security_review
    → FRESH

IF task == debugging
    → MAIN

IF task == architecture_exploration
   AND context_dependency == HIGH
    → FORK if supported
```

---

# 33. Context Coupling

新增：

```
context_coupling
```

衡量 Task 對 Main Working Context 的依賴。

---

## LOW

Task 幾乎可以獨立理解：

```
Search usages of API X.
```

推薦：

```
FRESH
```

---

## MEDIUM

需要部分 architecture：

```
Implement adapter using existing interface.
```

推薦：

```
FRESH + Context References
```

---

## HIGH

依賴多個前置決策：

```
Implement cross-module authentication feature.
```

推薦：

```
MAIN
```

---

## VERY HIGH

依賴長時間 reasoning history：

```
Continue debugging intermittent distributed race.
```

推薦：

```
MAIN
```

---

# 34. Context Handoff Score

可以定義：

```
ContextHandoffRisk
=
ContextCoupling
×
ImplicitKnowledge
×
HistoryDependency
```

如果：

```
ContextHandoffRisk
```

過高：

```
Do Not Delegate
```

---

# 35. Delegation Value 更新

原本：

```
DV =
ParallelismBenefit
+ SpecializationBenefit
+ ContextIsolationBenefit
- ContextTransferCost
- CoordinationCost
- VerificationDuplication
```

現在增加：

```
ContextReconstructionCost
```

因此：

```
DV =
ParallelismBenefit
+ SpecializationBenefit
+ ContextIsolationBenefit
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
DV > threshold
```

才值得 delegation。

---

# 36. Context Manager

CAI v2：

```
context_manager.py
```

應負責：

```
Main Context Lifecycle

Reasoning Digest

Context Compaction

Decision Extraction

Discovery Persistence

Failure Persistence
```

---

# 37. Context Handoff Manager

另外增加：

```
context_handoff.py
```

負責：

```
Main → Subagent

Task Contract
Context Selection
Artifact References
Context Expansion
Result Contract
Evidence Return
```

因此兩者責任不同。

---

# 38. Context Manager vs Context Handoff

```
context_manager.py
```

回答：

> Main Session 應該記住什麼？

---

```
context_handoff.py
```

回答：

> Subagent 完成這個 Task 需要知道什麼？

這兩個問題不應混在一起。

---

# 39. Proposed Runtime

```
                         Main
                          │
                          ▼
                  Context Manager
                          │
                          ▼
                     Task Graph
                          │
                          ▼
                 Delegation Policy
                          │
                ┌─────────┴─────────┐
                │                   │
              MAIN               SUBAGENT
                │                   │
                │                   ▼
                │          Context Handoff
                │                   │
                │                   ▼
                │             Task Contract
                │                   │
                │                   ▼
                │               Subagent
                │                   │
                │                   ▼
                │             Result Contract
                │                   │
                │                   ▼
                │               Evidence
                │                   │
                └─────────┬─────────┘
                          ▼
                        Main
```

---

# 40. Context Handoff Lifecycle

完整 lifecycle：

```
1. Task identified

2. Determine context coupling

3. Decide MAIN / FRESH / FORK

4. Build minimum context

5. Reference persistent artifacts

6. Start subagent

7. Subagent loads additional context lazily

8. If insufficient:
       CONTEXT_MISSING

9. Main expands context or takes task back

10. Subagent produces structured result

11. Evidence stored

12. Main consumes summary

13. Main reads detailed evidence only if required
```

---

# 41. Context Budget

每個 delegated task 可以設定：

```
context_budget:
  initial: small
  expansion: allowed
```

目標不是：

```
Give Agent everything.
```

而是：

```
Give Agent enough to start correctly.
```

---

# 42. Context Provenance

每個重要 Context 最好記錄來源。

例如：

```
fact:
  TokenManager owns token lifecycle

source:
  type: decision
  reference: decision-002
```

或：

```
fact:
  refresh cache shared across requests

source:
  type: code
  file: auth/cache.py
  line: 42
```

這樣 Subagent 可以自行 verify。

---

# 43. Context Confidence

Context 也可以有：

```
FACT
DECISION
HYPOTHESIS
ASSUMPTION
```

例如：

```
statement:
  race occurs during cache update

type:
  hypothesis
```

避免 Subagent 把 Main 的：

```
guess
```

當成：

```
fact
```

---

# 44. Context Freshness

Context Artifact 需要避免 stale information。

例如：

```
context:
  generated_from_commit: abc123
```

如果 repository 已變成：

```
def456
```

則：

```
Context may be stale
```

CAI 可以要求 refresh。

---

# 45. Codemap Integration

CAI 已有：

```
/cai:codemap
```

它非常適合成為 Subagent context bootstrap。

流程：

```
Subagent
    ↓
Codemap
    ↓
Relevant Files
    ↓
Detailed Read
```

而不是：

```
Subagent
    ↓
grep entire repository
    ↓
read many files
```

因此 Codemap 應成為：

# Context Navigation Layer

而不是單純 index。

---

# 46. Recommended Context Sources

Subagent 的 context priority：

```
1. Task Contract

2. Track Constraints

3. Relevant Decisions

4. Reasoning Digest

5. Codemap

6. Relevant Files

7. Repository Search

8. Main Context Expansion
```

---

# 47. Verification Context

Reviewer 不一定需要 Implementation Context。

甚至應刻意限制。

例如：

```
Reviewer receives:

Requirement
Design
Diff
Tests
Constraints
```

而不是：

```
Implementer's full reasoning
```

原因是避免：

# Reasoning Anchoring

Reviewer 應該形成獨立判斷。

---

# 48. Different Agent, Different Context

不能建立：

```
One Context Pack for every Agent
```

應該：

```
Explorer Context
≠
Implementer Context
≠
Reviewer Context
≠
Security Context
```

例如：

### Explorer

需要：

```
Goal
Scope
Known facts
Repository
```

### Implementer

需要：

```
Goal
Design
Constraints
Decisions
Interface
Tests
```

### Reviewer

需要：

```
Requirement
Design
Diff
Definition of Done
```

### Security Reviewer

需要：

```
Threat boundary
Relevant code
Security constraints
Diff
```

---

# 49. Context Isolation 也是優點

Subagent Context 少不一定都是缺點。

例如 Security Reviewer：

```
Fresh Context
```

可以避免：

```
Implementation Bias
```

所以 Context Isolation 本身也是：

```
Specialization Benefit
```

這也是 Fresh Subagent 在 Review 階段特別有價值的原因。

---

# 50. Main Session 不應重讀所有 Subagent Work

Main 應：

```
Read Result Contract
```

如果：

```
risk = low
evidence = strong
verification = pass
```

則：

```
Accept
```

只有：

```
risk = high

or

evidence conflict

or

verification fail

or

context uncertainty
```

才：

```
Read Detailed Evidence
```

---

# 51. Progressive Evidence Loading

類似 Context Lazy Loading：

```
Result Summary
      ↓
Enough?
 ┌────┴────┐
 YES       NO
 │          │
Accept   Evidence
            ↓
         Raw Output
```

避免 Main 每次重新讀全部資訊。

---

# 52. Two-Way Compression Problem

整個 Multi-Agent 系統有兩次 compression：

```
              Compression #1
Main Context ───────────────→ Subagent

Subagent Work ──────────────→ Main
              Compression #2
```

CAI 必須同時處理：

```
Main → Subagent Context Loss
```

與：

```
Subagent → Main Result Loss
```

因此：

# Context Handoff Protocol 必須是雙向的。

---

# 53. CAI v2 Context Architecture

最終架構：

```
                    MAIN SESSION
                         │
                  Strategic Context
                         │
                         ▼
                 Context Manager
                         │
              ┌──────────┴──────────┐
              │                     │
        Persistent Context      Working Context
              │                     │
              └──────────┬──────────┘
                         ▼
                    Task Graph
                         │
                         ▼
                 Delegation Policy
                         │
                         ▼
                Context Handoff
                         │
                  Task Contract
                         │
                         ▼
                     Subagent
                         │
                  Lazy Context
                         │
                         ▼
                    Execution
                         │
                         ▼
                  Result Contract
                         │
                         ▼
                     Evidence
                         │
                         ▼
                    MAIN SESSION
```

---

# 54. Proposed Components

```
plugins/cai/scripts/

context_manager.py
context_handoff.py
task_graph.py
delegation.py
evidence.py
scheduler.py
policy.py
```

其中：

```
context_manager.py
```

管理：

```
Main Context Lifecycle
```

而：

```
context_handoff.py
```

管理：

```
Main ↔ Subagent Context Boundary
```

---

# 55. Implementation Priority

建議 CAI v2 開發順序調整為：

```
Phase 1
Context Manager

      ↓

Phase 2
Context Handoff Protocol

      ↓

Phase 3
Evidence Layer

      ↓

Phase 4
Task Graph

      ↓

Phase 5
Delegation Policy

      ↓

Phase 6
Adaptive Multi-Agent
```

Context Handoff 應提前到 Task Graph 之前。

原因：

即使沒有複雜 Task Graph：

```
Main
 ↓
Subagent
```

本身就已經存在 Context Loss 問題。

---

# 56. 最重要的設計原則

CAI v2 應增加以下原則：

### 1. Context is a first-class resource

Context 與：

```
CPU
Memory
Token
Time
```

一樣需要管理。

---

### 2. Main owns strategic context

Main 是：

```
Context Owner
Decision Owner
Integration Owner
```

---

### 3. Subagent receives minimum sufficient context

不是：

```
Full Context
```

也不是：

```
No Context
```

而是：

```
Minimum Sufficient Context
```

---

### 4. Persist important knowledge

重要資訊不能只存在：

```
Conversation
```

應轉換成：

```
Decision
Discovery
Constraint
Evidence
Artifact
```

---

### 5. Reference instead of duplicate

優先：

```
Read decision-003.md
```

而不是：

```
Copy decision-003 content into every prompt
```

---

### 6. Lazy-load context

先給最小 Context。

需要時再擴充。

---

### 7. Missing context must be explicit

Subagent 不應猜。

應回：

```
CONTEXT_MISSING
```

---

### 8. Result handoff must be structured

避免：

```
Done.
```

使用：

```
Result Contract
+
Evidence
```

---

### 9. Different agents receive different context

```
Explorer Context
≠
Implementer Context
≠
Reviewer Context
```

---

### 10. Context isolation can be beneficial

Review / Security Agent 不一定需要 implementation reasoning。

---

### 11. Task Graph is not Agent Graph

Task 存在：

```
≠
```

一定需要 Subagent。

---

### 12. Delegation is an economic decision

必須考慮：

```
Context Transfer Cost
Context Reconstruction Cost
Coordination Cost
Verification Duplication
```

---

# 57. Final Architecture Principle

CAI v2 不應把 Subagent 理解成：

```
Another Main Agent
```

而應理解成：

```
Temporary Specialized Compute
Operating on Explicit Context
```

Main Session 則是：

```
Persistent Strategic Intelligence
```

兩者之間：

```
Main
 │
 │ Context Contract
 ▼
Subagent
 │
 │ Evidence Contract
 ▼
Main
```

因此 CAI v2 真正需要建立的不是單純：

```
Agent Orchestration
```

而是：

# Context-Aware Agent Orchestration

其核心公式可以寫成：

```
Effective Delegation
=
Right Task
×
Right Context
×
Right Agent
×
Right Evidence
```

任何一項接近零：

```
Effective Delegation ≈ 0
```

最終設計目標：

> **Main Session 保留完整的策略理解；Subagent 只取得完成特定工作所需的最小充分 Context；重要知識透過 Artifact 持久化；結果透過 Evidence 回傳，而不是依賴 Agent 對話記憶。**

---

# 58. References

## Claude Code — Subagents

Claude Code 官方文件：

[https://code.claude.com/docs/en/sub-agents](https://code.claude.com/docs/en/sub-agents)

重點：

- Subagent 使用獨立 context
- 可配置自己的 system prompt、tools 與 permissions
- Main Agent 可 delegate 特定工作給 specialized subagent

---

## Claude Code — Memory / [CLAUDE.md](http://CLAUDE.md)

Claude Code 官方文件：

[https://code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)

重點：

- [`CLAUDE.md`](http://CLAUDE.md) 提供 project-level persistent instructions
- 可讓不同 session / agent 重新取得專案規則
- 適合保存穩定、跨 session 的 project context

---

## Claude Code — Interactive Mode / Fork

Claude Code 官方文件：

[https://code.claude.com/docs/en/interactive-mode](https://code.claude.com/docs/en/interactive-mode)

重點：

- Claude Code 提供 conversation branching / fork 類能力
- Fork 類 context 與一般 fresh subagent delegation 應視為不同 execution context
- 實際支援行為應依使用中的 Claude Code 版本確認

---

## Anthropic — Multi-Agent Research System

Anthropic Engineering：

[https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

重點：

- Multi-Agent 適合高度可平行化工作
- Orchestrator 負責 delegation
- Subagent 使用獨立 context
- Agent communication 與 synthesis 會增加 token / coordination cost
- Research task 比 coding task 更容易有效平行化

---

# 59. 與 CAI v2 主架構的關係

本文件是：

`Claude All-in-One v2 — Context-Centric Adaptive Agentic SDLC Architecture`

的 Context Handoff 補充設計。

主架構回答：

> **什麼 Task 應該交給哪一個 Agent？**

本文件回答：

> **決定交給 Subagent 後，到底應該把什麼資訊交給它，以及如何把結果可靠地帶回 Main Session？**

兩者合起來形成：

```
Context Management
        +
Context Handoff
        +
Task Graph
        +
Adaptive Delegation
        +
Evidence Verification
        +
Risk-based Autonomy
```

這六個部分應共同構成 CAI v2 的 Agent Runtime 核心。