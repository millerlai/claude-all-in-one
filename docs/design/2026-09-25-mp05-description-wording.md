# mp05-description-wording — 19 條 always-on description 的措辭審查紀錄

依據：`docs/design/2026-09-25-mattpocock-skills-gap-analysis.md` §MP-05（description 措辭審查：leading word 前置、一分支一觸發）。來源：mattpocock/skills 的 `skills/productivity/writing-for-agents/SKILL.md` §Context pointers 與 §Leading words。執行日 2026-09-25，分支 `cai/description-wording`。

這份檔案只記錄做了什麼、量到什麼、每一條為什麼這樣改；它不是設計文件，沒有 `## Status`。差距文件本身（MP-05 的任務表）由主 session 更新，本檔不動它。

## 名詞表

- **description**：每個 skill 或 agent 檔案最前面 frontmatter（檔頭的 YAML 區塊）裡的 `description:` 那一行或那一段。模型在每個 session 都讀得到它，並靠它決定要不要叫這個元件。
- **always-on**：「一直在場」——不用任何人開口，模型每回合都看得到的東西。這裡指沒有標 `disable-model-invocation: true`（禁止模型自行呼叫）的 skill，加上全部 agent，它們的 description 每回合都在花 token。
- **ratchet（棘輪）**：`scripts/validate.py` 裡的 `ALWAYS_ON_CEILING`，一個只能往下、不能悄悄往上的總字元數上限；總量超過它就 FAIL。
- **leading word（前導詞）**：模型預訓練裡已經有的緊湊概念（例如 *regression*、*scout*、*test-first*），一個詞就能鉤住一整片行為；相對的是自造詞，得先花字數定義。
- **branch（分支）**：一條 description 裡「該在什麼情況下觸發」的一個獨立情況。同一個情況換個說法再寫一次，就是同一個分支寫兩次。
- **eval / case / grader**：`claude plugin eval` 是付費跑的行為測試；一個 **case** 是一段 prompt（提示）加幾個 **grader**（判定器，對輸出做字串或工具呼叫比對）。本 repo 有三個 case，放在 `plugins/cai/evals/`。
- **slash 指令**：使用者在 Claude Code 裡打 `/cai:track status` 這種以斜線開頭的指令；平台直接把對應 skill 的內容展開進 prompt，不經過 description 比對。
- **folded scalar（折行值）**：YAML 裡 `description: >` 後面接好幾行縮排文字的寫法；讀出來時各行以空白接成一行。`validate.py` 計數用的就是接成一行後的長度。
- **anchor（錨點）**：`scripts/codex-overrides.json` 裡每一條覆寫要比對的原文；`gen-codex.py` 要求它在目標檔裡恰好出現一次，否則整個產生流程失敗。
- **sibling（同胞）**：同屬 cai 的另一個 skill 或 agent。

## 1. 三條規則，三個不動

每一條 description 都逐一過這三條規則（沿用差距文件 MP-05 的說法）：

- **(a) 情境前置**：開頭第一個子句寫「該觸發它的情況」，不寫「它是什麼」。「A skill that…」「Runs the … stage:」這類開頭都拿掉。「Use PROACTIVELY」不是身分句，不在此列，見下方 L3。
- **(b) 一分支一觸發**：已經有的觸發條件，再用同義詞或換句話寫一次，就是同一個分支寫兩次——砍掉後者，只留真正不同的分支。
- **(c) 砍 body 已經有的**：身分陳述（「Read-only code smell analyst.」），以及 body 自己就有 `## When not to use this` 之類段落在重複的「Not for …」清單。

三個刻意不動，都是因為三個 eval case 量不到它們：

- **L1 中文觸發句留一句**：今天有中文的 description（`debug`、`plan-review`、`verify`）改完後仍各留一句中文；不因為砍同義而把一個語言整個砍掉。
- **L2 同胞區隔的 Not-for 留著**：「Not for X」的 X 若是一個 sibling，而且拿掉這句後兩者的 description 會互相重疊（誤觸發到對方），就留。這一輪逐條判斷下來，三條有 Not-for 的 description（`debug`、`implementer`、及 `architect` 的「do not use for routine tasks」）只有 `architect` 那句留下——它不是指向 sibling，而是主 session 挑 agent 時的成本閘，body 沒有這句。其餘見 §3 各條的理由。
- **L3 「Use PROACTIVELY」留著**（2026-09-25，review 後補回）：`explorer`、`test-runner` 改前各有一句「Use PROACTIVELY」，第一版把它當成開頭一併砍掉（總量量到 3802）。review 指出 Claude Code 的 sub-agents 文件（https://code.claude.com/docs/en/sub-agents §Understand automatic delegation，本輪實際抓取）原文是「To encourage proactive delegation, include phrases like "use proactively" in your subagent's description field」——它是平台自己點名的自動派工（automatic delegation）槓桿，不是規則 (c) 要砍的身分陳述；mattpocock 來源的三條規則（front-load the leading word／one trigger per branch／cut identity the body already carries）與差距文件 MP-05 都沒有要求拿掉它，而三個 eval case 也量不到它消失（§6）。所以兩條都以句尾「Use PROACTIVELY.」放回，情境仍在句首、規則 (a) 不受影響；各 +17，合計 +34，總量 3836。

另外偏好 leading word：*regression*（取代「something that used to work and stopped」）、*scout*（explorer）、*test-first*（取代「a failing test run before and a passing one after」）、*lens*。

每條 description 保持原本的 YAML 形式：單行的仍單行，雙引號包起來的（`goal`、`track`）仍雙引號，`>` 折行的仍折行；`validate.py` 對全部 19 檔的 frontmatter 檢查都 PASS（§4）。

## 2. 盤點：哪 19 條、怎麼數

`scripts/validate.py` 的 always-on 區塊（改前 `:268-307`）：把 `plugins/cai/agents/*.md`、`plugins/cai/skills/*/SKILL.md`、`plugins/cai/refactoring-catalog/*/SKILL.md` 全部列出，跳過檔內含 `disable-model-invocation: true` 的，其餘各取 `frontmatter_description()`（`:99-115`：單行取該行、引號剝掉；折行值把各縮排行 strip 後以空白接起）的長度加總，印出 `always-on description budget: N chars`，再檢查 N ≤ `ALWAYS_ON_CEILING`。

19 個主線 skill 裡有 10 個帶旗標（`build`、`design`、`git-sweep`、`intake`、`models`、`options`、`quiz`、`setup`、`ship`、`usage`），剩 9 個 skill；agent 10 個全算。改前實跑 `python scripts/validate.py` 印出：

```
     always-on description budget: 5674 chars (design target: 4673)
PASS always-on description budget does not exceed 5697 chars (5674)
```

## 3. 逐條改前改後

### 3.1 總表

| # | 元件 | 改前 | 改後 | 差 | 規則 | 一句話理由 |
|---|---|---|---|---|---|---|
| 1 | `skills/chore` | 189 | 188 | -1 | a, b | 動詞開頭改情境開頭；「chore … chore tier」去掉一個 chore |
| 2 | `skills/debug` | 579 | 250 | -329 | a, b, c, L1 | 身分句、四組同義觸發、三個 Not-for（body `## When not to use this` 逐一重複，差距文件 :219 點名）都砍 |
| 3 | `skills/discover` | 625 | 400 | -225 | a, b, c | 五個分支各被寫三次（技法名、情境、使用者說法），收成情境加一句說法；slash 提及刪 |
| 4 | `skills/git` | 378 | 229 | -149 | a, b | full form 與 shorthand 是同一組分支寫兩次；合併請求兩例留一例 |
| 5 | `skills/goal` | 244 | 185 | -59 | a, c | 兩條 lane 的機制是 body Step 3–4 |
| 6 | `skills/plan-review` | 599 | 363 | -236 | a, b, c, L1 | 文件類型列兩次、四個 lens 摘要是 body Step 1–2、兩句精準度提問同分支 |
| 7 | `skills/refactor` | 464 | 340 | -124 | a, b | 「tidy up」「restructure」是 refactor 同義詞；具名 refactoring 兩例留一例 |
| 8 | `skills/track` | 265 | 254 | -11 | a | 情境開頭；「resume where it stopped」貼近 eval prompt 用字；Usage 留 |
| 9 | `skills/verify` | 455 | 272 | -183 | a, b, c, L1 | 派工與測試機制是 stage-verify.md；三句 review 說法同分支 |
| 10 | `agents/architect` | 184 | 173 | -11 | a, c | 身分句刪；成本閘留 |
| 11 | `agents/designer` | 283 | 142 | -141 | a, c | 「cites evidence… hands up unanswered」是 body :22-25、:29-35 |
| 12 | `agents/explorer` | 141 | 126 | -15 | a, c, L3 | 身分句「Fast codebase exploration」去掉；read-only scout 一個詞；「Use PROACTIVELY」留（L3） |
| 13 | `agents/implementer` | 137 | 83 | -54 | a, c | 「Not for architectural decisions」body :21-22 已說；L2 未啟用（見下） |
| 14 | `agents/refactoring-detector` | 281 | 162 | -119 | a, c | 回傳格式是 body `## Return format` |
| 15 | `agents/reviewer` | 146 | 108 | -38 | a, c | 身分句刪；「does not fix anything」改正向「findings only」 |
| 16 | `agents/security-reviewer` | 187 | 151 | -36 | a, c | 同 reviewer；四個 hunt item 留（body 只指向 finding-severity.md） |
| 17 | `agents/shipper` | 199 | 159 | -40 | a, c | 「Stops for confirmation」是 body :16-24；Codex anchor 同步 |
| 18 | `agents/test-runner` | 96 | 94 | -2 | a, c, L3 | 身分句「Runs test suites and reports failures」去掉；「Does not fix code」縮成兩個字；「Use PROACTIVELY」留（L3） |
| 19 | `agents/verifier` | 222 | 157 | -65 | a, c | 「three reviewer lenses plus the security one」是 body :12-14；Codex anchor 同步 |
| | **合計** | **5674** | **3836** | **-1838** | | |

字元數全部由 §2 的同一個計數方式量出（`validate.py` 的 `frontmatter_description()`），不是估的。

### 3.2 逐條原文

description 本身保留原語言，不翻譯。理由裡引用的 body 行號（`:22-25` 這種）都是**改前**檔案的行號；折行 description 縮短後，該檔 body 的行號會往上移一到三行。

**1. `plugins/cai/skills/chore/SKILL.md`**

改前：

> Run a mechanical, no-judgement chore on the chore tier instead of the main session model — renames, formatting, simple lookups, one-off shell commands, boilerplate. Usage: /cai:chore <task>

改後：

> Mechanical, no-judgement work — renames, formatting, simple lookups, one-off shell commands, boilerplate — run on the chore tier instead of the main session model. Usage: /cai:chore <task>

理由：(a) 原句以動詞「Run a … chore on the chore tier」起頭，情境（mechanical、no-judgement）雖在第一子句裡但排在動作後面，改成情境開頭；(b) 「chore on the chore tier」的第一個 chore 是重複。Usage 子句留著——規則 (c) 針對身分陳述與 Not-for 清單，用法提示不在其內。

**2. `plugins/cai/skills/debug/SKILL.md`**

改前：

> Find the root cause of a bug before proposing any fix — a test that fails, a crash, a stack trace, unexpected behaviour, or something that used to work and stopped. Use when the user says "this is broken", "it's not working", "the test fails", "fix this bug", "為什麼會壞", "這段程式有 bug", or pastes an error message or stack trace. Not for a diff that might not be mergeable (`verify`), code that behaves correctly but is hard to read (`refactor`), or a question about what's unknown before any code exists (`discover`) — this is for something that demonstrably does not work right now.

改後：

> Something demonstrably broken right now — a failing test, a crash, wrong behaviour, a regression — where the root cause comes before any fix. Use when the user says "this is broken", "fix this bug", "為什麼會壞", or pastes an error message or stack trace.

理由：(a) 「Find the root cause of a bug before proposing any fix」是 body `## The rule` 的身分陳述；原句最後一句「this is for something that demonstrably does not work right now」才是情境，搬到開頭。(b) 四組同分支：「a test that fails」／「the test fails」；「a stack trace」／「pastes … stack trace」；「this is broken」／「it's not working」；「fix this bug」／「這段程式有 bug」——各留一個。「something that used to work and stopped」→ *regression*。(c) 三個 Not-for 與 body `## When not to use this`（改前 `:117-124`）逐一重複，且差距文件 `:219` 已把這段點名為「body 已經有的東西」。L1：兩句中文留「為什麼會壞」（全中文那句；「這段程式有 bug」的 bug 英文那邊已經有）。L2 未啟用：`verify`、`refactor`、`discover` 改後各自以正向情境開頭（review before it merges／internal structure without changing behaviour／unknown before code is written），與「demonstrably broken right now」不重疊。

**3. `plugins/cai/skills/discover/SKILL.md`**

改前：

> Surface what the user doesn't know before writing implementation code — a blindspot pass, a vocabulary ladder, an interview, an option space, or a mock, whichever unknown would change the most work. Use whenever the codebase area is unfamiliar, the requirements are ambiguous, the solution space has not been explored, or the result will be judged by look and feel. Also use when the user invokes /cai:discover, or says "what am I missing", "find my blindspots", "interview me about this", "brainstorm the options", "show me some directions", "mock this up first", "I've never touched this code", or "I don't know what X is".

改後：

> An unknown that would change the work, surfaced before implementation code is written — the codebase area is unfamiliar, the requirements are ambiguous, the option space is unexplored, a term is undefined, or the result will be judged by look and feel. Use when the user says "what am I missing", "interview me about this", "brainstorm the options", "mock this up first", or "I don't know what X is".

理由：(a) 「Surface what the user doesn't know」是動作，改成「An unknown that would change the work」。(b) 五個分支各被寫三次——技法名（blindspot pass／vocabulary ladder／interview／option space／mock）、情境、使用者說法。技法名刪（`stage-discover.md` 自己有，屬 (c)）；使用者說法每分支留一句：「find my blindspots」≈「what am I missing」、「show me some directions」≈「brainstorm the options」、「I've never touched this code」≈ 情境「codebase area is unfamiliar」，刪。情境清單補上「a term is undefined」承接 vocabulary ladder 那個分支。(c) 「Also use when the user invokes /cai:discover」——slash 指令由平台展開，不經 description 比對，刪。無中文，L1 不適用。

**4. `plugins/cai/skills/git/SKILL.md`**

改前：

> Use this whenever the user asks to run a git or GitHub CLI operation — full form (git commit, git add, git push, git pull, git merge, git rebase, git stash, branch create/switch, gh pr create) or shorthand (commit, add, push, pull, pr), including combined requests like "commit + push + pr" or "commit, push" — so it executes on the chore tier instead of the main session model.

改後：

> A git or GitHub CLI operation the user asks for — commit, add, push, pull, merge, rebase, stash, branch create/switch, pr, or a combined request like "commit + push + pr" — run on the chore tier instead of the main session model.

理由：(a) 「Use this whenever…」開頭改為情境。(b) full form 與 shorthand 是同一組分支寫兩次（模型比對「commit」不需要前面有「git」），合成一組裸動詞；合併請求兩個例子留一個。(c) 無。

**5. `plugins/cai/skills/goal/SKILL.md`**

改前：

> Review a design doc, then route it: a document with a work breakdown schedule is built unit by unit, everything else goes to a single implementer — both lanes converge on the same test-and-report step. Usage: /cai:goal <path to design/plan doc>

改後：

> A design or plan doc to take from review to verified implementation — unit by unit when it carries a work breakdown schedule, whole otherwise. Usage: /cai:goal <path to design/plan doc>

理由：(a) 「Review a design doc, then route it」是動作；body 第一行「Take this design/plan doc from requirement to verified implementation」才是它的用途，改成以此為情境。(c) 兩條 lane 的機制（single implementer、converge on the same test-and-report step）是 body Step 3–4，刪；「unit by unit when it carries a work breakdown schedule, whole otherwise」留作觸發面，讓模型知道兩種文件都收。Usage 留。

**6. `plugins/cai/skills/plan-review/SKILL.md`**

改前：

> Review an implementation plan, architecture design, or technical spec the way a senior architect would — trace every design element back to a requirement, surface over-engineering, check the software-engineering consequences the plan glossed over, and hunt wording too vague to implement from. Use when the user asks to review a plan, design doc, spec, RFC, or ADR, says "審一下這份計畫", "is this over-engineered", "does this match the requirements", "poke holes in this design", "這份規格夠精準嗎", "is this spec precise enough to build from" — and also on your own implementation plans before handing them over.

改後：

> A plan, design doc, spec, RFC, or ADR to review before anything is built from it — read from the requirements first, the way a senior architect would. Use when the user asks for that review, says "審一下這份計畫", "is this over-engineered", "does this match the requirements", "is this spec precise enough to build from" — and on your own plans before handing them over.

理由：(a) 開頭改為「A plan, design doc, spec, RFC, or ADR to review before anything is built from it」。(b) 文件類型列了兩次（implementation plan／architecture design／technical spec，與 plan／design doc／spec／RFC／ADR）合成一份；「poke holes in this design」與「asks for that review」／「審一下這份計畫」同分支，刪；「這份規格夠精準嗎」與「is this spec precise enough to build from」同分支。(c) 四個 lens 的摘要（trace back to a requirement、over-engineering、consequences glossed over、vague wording）是 body Step 1–2，刪；留下的三句使用者說法已各自指向一個 lens（traceability、over-engineering、precision）。「read from the requirements first」留一句，因為它是與一般 code review 的區別。L1：兩句中文留「審一下這份計畫」。自審分支（on your own plans）是獨立分支，留。

**7. `plugins/cai/skills/refactor/SKILL.md`**

改前：

> Use when improving the internal structure of existing code without changing its behaviour - cleaning up a long method, breaking up a god class, removing duplication, taming conditionals, fixing an inheritance hierarchy, or when the user says refactor, code smell, technical debt, tidy up, restructure, or names a specific refactoring such as Extract Method or Replace Conditional with Polymorphism. Also use before adding a feature to code that resists the change.

改後：

> Improving the internal structure of existing code without changing its behaviour - a long method, a god class, duplication, tangled conditionals, an inheritance hierarchy - or the user says refactor, code smell, technical debt, or names a refactoring such as Extract Method. Also use before adding a feature to code that resists the change.

理由：(a) 「Use when improving…」→「Improving…」。(b) 「tidy up」「restructure」是 refactor 的同義詞，刪；具名 refactoring 的兩個例子（Extract Method、Replace Conditional with Polymorphism）是同一分支，留一個。(c) 無——五個 smell 例子 body 沒有逐一重述，留作觸發面。「code smell」「technical debt」是不同的鉤子（使用者說 smell 或說 debt），都留。無中文。原句用的 ` - ` 分隔符照舊。

**8. `plugins/cai/skills/track/SKILL.md`**

改前：

> Carry one feature through the six SDLC stages (intake, discover, design, build, verify, ship), keeping state in .claude/track/ so a new session with no memory of this conversation can resume. Usage: /cai:track [<feature>|status|skip <stage> --reason "<why>"|done]

改後：

> One feature carried through every SDLC stage — intake, discover, design, build, verify, ship — with its state kept in .claude/track/ so a later session can resume where it stopped. Usage: /cai:track [<feature>|status|skip <stage> --reason "<why>"|done]

理由：(a) 「Carry one feature through the six SDLC stages」→「One feature carried through every SDLC stage」；「six」由清單自己說明。「a new session with no memory of this conversation can resume」→「a later session can resume where it stopped」，*stopped* 是 `track-status-runs-the-script` 的 prompt 用字（§6）。(b)(c) 無；Usage 留——body `:7-13` 雖有用法區塊，但規則 (c) 針對身分陳述與 Not-for 清單，且這是 eval 唯一碰到的 always-on description，不多動。YAML 雙引號與 `\"` 逸出照舊。

**9. `plugins/cai/skills/verify/SKILL.md`**

改前：

> Review a branch diff before merging by dispatching four read-only reviewers (correctness, conformance, coverage, security) in parallel and reconciling their findings, then fix Blockers and Majors with a failing test run before and a passing one after. Use when the user asks to review a diff, branch, or PR before merging, says "review my changes", "check this before I merge", "審一下這個 diff", "找出這次改動的問題" — and on your own changes before handing them over.

改後：

> A diff, branch, or PR to review before it merges — four read-only lenses (correctness, conformance, coverage, security), then Blockers and Majors fixed test-first. Use when the user says "review my changes", "審一下這個 diff" — and on your own changes before handing them over.

理由：(a) 「Review a branch diff before merging by dispatching…」→「A diff, branch, or PR to review before it merges」。(b) 「asks to review a diff, branch, or PR before merging」「review my changes」「check this before I merge」是同一分支寫三次，留情境加一句「review my changes」；「找出這次改動的問題」與「審一下這個 diff」同分支。(c) 派工與測試機制（dispatching … in parallel and reconciling their findings；a failing test run before and a passing one after）是 `stage-verify.md` 的內容，刪；四個 lens 名稱留（它們是與 `plan-review`、一般 code review 的區別），「a failing test run before and a passing one after」→ *test-first*。L1：留「審一下這個 diff」。自審分支留。

**10. `plugins/cai/agents/architect.md`**（折行）

改前：

> Deep design and architecture analysis. Use ONLY for cross-cutting design decisions, concurrency/correctness issues, or ambiguous requirements. Expensive — do not use for routine tasks.

改後：

> Cross-cutting design decisions, concurrency or correctness questions, or ambiguous requirements, analysed read-only by a senior architect. Expensive — not for routine tasks.

理由：(a) 「Deep design and architecture analysis. Use ONLY for…」→ 三個情境直接開頭。(c) 「Deep design and architecture analysis」是身分（body：「You are a senior architect. Read-only.」），刪。「Expensive — not for routine tasks」留：它不是指向 sibling 的 Not-for，而是主 session 挑 agent 時的成本閘，body 沒有這句。

**11. `plugins/cai/agents/designer.md`**（折行）

改前：

> Writes a design document — diagnosis, stance, decisions, detail, or delta — following stage-design.md's procedure. Dispatched by the `design` stage. Cites evidence for every claim about existing behaviour and hands any architecture-level choice up unanswered rather than deciding it.

改後：

> A design document the `design` stage dispatches for — diagnosis, stance, decisions, detail, or delta — written by stage-design.md's procedure.

理由：(a) 「Writes a design document」→「A design document the `design` stage dispatches for」。(c) 「Cites evidence for every claim … hands any architecture-level choice up unanswered」是 body `:22-25`、`:29-35`，刪。五個模式名留（它們是這個 agent 收哪些文件的觸發面）。`codex-overrides.json` 對 designer 的兩個 anchor 都在 body，不受影響。

**12. `plugins/cai/agents/explorer.md`**（折行）

改前：

> Fast codebase exploration. Use PROACTIVELY for locating files, symbols, usages, and config entries before any implementation work. Read-only.

改後：

> Locating files, symbols, usages, and config entries before any implementation work — a fast, read-only scout. Use PROACTIVELY.

理由：(a) 「Fast codebase exploration. Use PROACTIVELY for…」→ 情境開頭。(c) 身分句刪；body 已說「read-only codebase scout」，description 留 *scout* 一個詞（與 implementer 區別）。L3：「Use PROACTIVELY」第一版隨開頭一起砍掉（109 字），review 後以句尾「Use PROACTIVELY.」放回（+17 → 126）——它是平台文件點名的派工槓桿，不是身分句，見 §1。

**13. `plugins/cai/agents/implementer.md`**（折行）

改前：

> Implements well-specified features and fixes. Use when requirements are clear and scoped to a few files. Not for architectural decisions.

改後：

> A well-specified feature or fix, with requirements clear and scoped to a few files.

理由：(a) 「Implements well-specified features and fixes. Use when…」→「A well-specified feature or fix…」。(c) 「Not for architectural decisions」——body `:21-22` 已說遇到設計決策就 STOP and report back。L2 未啟用：`architect` 改後以「Cross-cutting design decisions」開頭，implementer 的正向條件「well-specified … scoped to a few files」本身已排除它，兩者不重疊。

**14. `plugins/cai/agents/refactoring-detector.md`**（單行）

改前：

> Read-only code smell analyst. Invoke to survey a file, module or package and return an evidenced, severity-scored list of code smells with candidate refactorings. Use for parallel analysis across several modules, or when a scan would flood the main conversation with file contents.

改後：

> A file, module or package to survey for code smells, read-only — several modules in parallel, or a scan that would flood the main conversation with file contents.

理由：(a) 「Read-only code smell analyst. Invoke to survey…」→「A file, module or package to survey for code smells」。(c) 身分句與「return an evidenced, severity-scored list of code smells with candidate refactorings」（body `## Return format`）刪；「read-only」留一個詞。兩個使用情境（平行掃多個 module、掃描會淹掉主對話）留。

**15. `plugins/cai/agents/reviewer.md`**（折行）

改前：

> Reviews a diff through one named lens and reports findings. Dispatched by the `verify` stage, several at a time. Read-only; does not fix anything.

改後：

> One named lens over one diff, as the `verify` stage dispatches several at a time — read-only, findings only.

理由：(a) 「Reviews a diff through one named lens and reports findings」→「One named lens over one diff」。(c) body `:11` 已說「You review one lens of one diff. Read-only.」；「does not fix anything」改成正向的「findings only」（來源 §Leading words 的 negation 段：能正向說就不用禁止句）。

**16. `plugins/cai/agents/security-reviewer.md`**（折行）

改前：

> Reviews a diff through the security lens - shell execution, argv, secrets in logs, guard bypass - and reports findings. Dispatched by the `verify` stage. Read-only; does not fix anything.

改後：

> The security lens over one diff - shell execution, argv, secrets in logs, guard bypass - as the `verify` stage dispatches it. Read-only, findings only.

理由：同 reviewer。四個 hunt item 留——body 只指向 `finding-severity.md`，沒有列出它們，不算 body 已有。原句的 ` - ` 分隔符照舊。

**17. `plugins/cai/agents/shipper.md`**（折行）

改前：

> Squashes a branch into one conventional commit, pushes it, and opens the PR — following stage-ship.md's procedure. Dispatched by the `ship` stage. Stops for confirmation before any irreversible step.

改後：

> A finished branch to ship — squashed into one conventional commit, pushed, and opened as a PR by stage-ship.md's procedure — as the `ship` stage dispatches it.

理由：(a) 「Squashes a branch…」→「A finished branch to ship — squashed…」。(c) 「Stops for confirmation before any irreversible step」是 body `:16-24`（draft then stop and hand it up；merging/tagging/publishing needs the person's confirmation），刪。`codex-overrides.json` 對 shipper description 的 anchor（含 `description: >` 共四行）同步改成新的四行；Codex 端的 replacement 文字（「Prepares a branch for release on Codex…」）沒有動，見 §5。

**18. `plugins/cai/agents/test-runner.md`**（折行）

改前：

> Runs test suites and reports failures. Use PROACTIVELY after any code change. Does not fix code.

改後：

> After any code change — the test suite run, failures reported, nothing fixed. Use PROACTIVELY.

理由：(a) 「Runs test suites and reports failures. Use PROACTIVELY after any code change」→「After any code change — …」。(c) 「Does not fix code」body `:14` 已說「Do NOT attempt fixes」，縮成「nothing fixed」兩個字留著，因為 `verifier` 也跑測試但會修，這兩個字是兩者的區別。L3：同 explorer——「Use PROACTIVELY」第一版砍掉（77 字），review 後以句尾放回（+17 → 94）。

**19. `plugins/cai/agents/verifier.md`**（折行）

改前：

> Runs the `verify` stage: dispatches four review agents in parallel - the three `reviewer` lenses plus the security one - reconciles what they report, runs this repo's test command, and fixes only Blocker/Major, test-first.

改後：

> The `verify` stage's diff — four review lenses dispatched in parallel, their findings reconciled, this repo's tests run, only Blocker/Major fixed test-first.

理由：(a) 「Runs the `verify` stage:」→「The `verify` stage's diff — …」。(c) 「the three `reviewer` lenses plus the security one」是 body `:12-14`，刪。`codex-overrides.json` 對 verifier description 的 anchor（三行）同步改成新的三行；Codex 端 replacement（「Runs the back half of the `verify` stage…」）沒有動，見 §5。

## 4. 總量與 ceiling

- 改前：**5674**（ratchet 5697，餘 23）。
- 改後：**3836**（第一版 3802，L3 放回兩句「Use PROACTIVELY.」後 +34），改後實跑 `python scripts/validate.py` 印出：

```
     always-on description budget: 3836 chars (design target: 4673)
PASS always-on description budget does not exceed 3836 chars (3836)
```

- `ALWAYS_ON_CEILING` 5697 → **3836**（`scripts/validate.py`），刻意零餘裕：下一條要變長的 description 得先把 ceiling 抬高並說明為什麼。這是這個數字第一次落在 4,673 的設計目標之下；`(design target: 4673)` 那段印出文字沒有動。
- `tests/test_track_skill_ticket_pointer.py` 的 `test_always_on_budget_is_unchanged_at_5674` 是對同一個數字的等式斷言（該檔的慣例：數字只跟著一段說明為什麼的註解一起動），改名為 `..._at_3836`、斷言改 3836，並依同檔慣例加一段 2026-09-25 的註解（含 L3 那 34 字的來由）。
- `python scripts/validate.py`：exit 0，810 行 PASS，0 行 FAIL。最後三行：

```
PASS no evals file contains a sk-ant- (0 found)
PASS no evals file contains a ghp_ (0 found)
PASS no evals file contains a home-directory path (0 found)
```

- `python -m pytest`：結果見 PR 說明（本檔寫成時尚在跑；主 session 的 PR body 引用最後一行）。

## 5. Codex 端

- `scripts/codex-overrides.json` 有兩條 anchor 落在被改的 description 行上：`agents/verifier.md`（三行）與 `agents/shipper.md`（含 `description: >` 四行）。兩條 anchor 都改成新的行文，`gen-codex.py` 要求的「恰好出現一次」仍成立（`--check` 0 findings）。兩條的 **replacement**（Codex 專用的 description 文字）沒有動——它們不在這 19 條之內，也不進 `validate.py` 的計數；要不要對 Codex 端的兩段 replacement 套同樣三條規則，留給主 session 決定（見 PR 的 open questions）。
- `python scripts/gen-codex.py`：237 file(s) generated, 0 finding(s)。
- `plugins/cai/.claude-plugin/plugin.json` version 1.32.1 → 1.32.2。
- `python scripts/gen-codex.py --release 0.2.16`：released 0.2.16（`scripts/codex-release.json` 的 version 與 fingerprint 隨之更新）。L3 放回後 `cai_explorer.toml`、`cai_test-runner.toml` 的 description 再變一次，fingerprint 重算，仍以 0.2.16 重新 release——`main` 上是 0.2.15，`gen-codex.py` 的 `release_refusal()` 只拒絕 ≤ base ref 已發佈版本的號碼，同一分支內重錄同一個號碼是允許的。
- `python scripts/gen-codex.py --check`：237 file(s) checked, 0 finding(s)。
- 產出的 `plugins/cai-codex/` 裡，19 個對應檔案（10 個 `agents/cai_*.toml` 的 `description = …`、9 個 `skills/*/SKILL.md` 的 frontmatter）跟著更新；`cai_verifier.toml`、`cai_shipper.toml` 的 description 仍是 override 的 replacement 文字。

## 6. Eval：三個 case、prompt 關鍵字、指令、上次基準

三個 case 都在 `plugins/cai/evals/`；`case.yaml` 這個檔名在三個目錄下都不存在（每個 case 只有 `prompt.md` 與 `graders/`），本輪讀的是這些。

| case | prompt 起頭的 slash 指令 | 練到的 skill | 在 19 條之內？ | grader |
|---|---|---|---|---|
| `options-six-fields` | `/cai:options` | `options` | 否（帶 `disable-model-invocation: true`） | 六個 `regex` 標籤（What it literally is、ELI5、What actually changes、What it costs、How reversible、When it fits）+ 一個 `tool_used: Read`（`skills/options/references` 至少讀一次） |
| `track-status-runs-the-script` | `/cai:track status` | `track` | **是** | 一個 `regex`：輸出含 `track_state.py` |
| `design-gate-is-a-menu` | `/cai:design` | `design` | 否（帶 `disable-model-invocation: true`） | 三個 `regex`：`Approve`、`Changes requested`、`Reject` |

三個 prompt 都以 slash 指令起頭（pb02 量測紀錄 §7.1 於 2026-09-14 加上的），而 slash 指令由平台在 prompt 層直接展開（同紀錄 §7.2：「slash 指令在 prompt 層被展開（C11），不經過任何工具呼叫」）。所以這三個 case 量到的是 skill body 展開後模型的措辭，**不是 description 的觸發**；三個 case 裡唯一碰到 always-on description 的是 `track`，而它也是經 slash 到達的。這是差距文件 MP-05 風險欄說「三個 eval case 是唯一的信號」的實際含意：它們能抓到 body 行為的退步，抓不到 description 不再觸發。

`track` 的 prompt 裡 description 該繼續對得上的字：「feature track」「stopped」「which stage」「resume」——改後的 description 含 `feature`、`stage`、`resume where it stopped`、`.claude/track/`（§3.2 第 8 條）。

**指令逐字**（來自 `docs/design/2026-09-12-pb02-plugin-evals-measurement.md`；`$SCRATCH` 是當次 session 的 scratchpad 根，`$REPO` 是 repo 根；副本用 `cp -r "$REPO/plugins/cai" …` 複製後先 `diff -r` 確認再跑）。最近一次跑 `track-status-runs-the-script` 與 `design-gate-is-a-menu` 的指令是 §7.3（2026-09-14，`--runs 3`）：

```
claude plugin eval "$SCRATCH/pb02-ci-eval-copy/2026-09-14/cai" \
  --case track-status-runs-the-script \
  --runs 3 --model haiku --ablation none --keep-temp --max-cost-usd 1 --threshold 0 \
  --trust-plugin --no-publish \
  --output-dir "$SCRATCH/pb02-ci-eval-results/2026-09-14/track-status-runs-the-script" \
  --json "$SCRATCH/pb02-ci-eval-results/2026-09-14/track-status-runs-the-script/run-track-status-runs-the-script.json"

claude plugin eval "$SCRATCH/pb02-ci-eval-copy/2026-09-14/cai" \
  --case design-gate-is-a-menu \
  --runs 3 --model haiku --ablation none --keep-temp --max-cost-usd 1 --threshold 0 \
  --trust-plugin --no-publish \
  --output-dir "$SCRATCH/pb02-ci-eval-results/2026-09-14/design-gate-is-a-menu" \
  --json "$SCRATCH/pb02-ci-eval-results/2026-09-14/design-gate-is-a-menu/run-design-gate-is-a-menu.json"
```

`options-six-fields` 最近一次是 §1（2026-09-12）：

```
claude plugin eval "$SCRATCH/pb02-eval-copy/2026-09-12/cai" \
  --case options-six-fields \
  --model haiku --ablation none --keep-temp --max-cost-usd 5 --threshold 0 \
  --trust-plugin --no-publish \
  --output-dir "$SCRATCH/pb02-eval-results/2026-09-12/options-six-fields" \
  --json "$SCRATCH/pb02-eval-results/2026-09-12/options-six-fields/run-options-six-fields.json"
```

同一份紀錄 §1 坐實：一次指令重複 `--case` 只會跑到最後一個，所以三個 case 要三次指令，各自一個 `--output-dir` 與 `--json`；`--output-dir` 必須在 repo 外（本 repo `CLAUDE.md`「Before pushing」）。

**上次記錄的基準**（同一份紀錄）：

| case | 量測日 | 結果 | 花費 |
|---|---|---|---|
| `options-six-fields` | 2026-09-12（§3–§4） | 六個標籤 grader 3/3 PASS；`reads-options-references`（tool_used）1/3 PASS | US$0.09788（三個 run 合計） |
| `design-gate-is-a-menu` | 2026-09-14（§7.4） | 三個 grader 各 3/3 PASS | US$0.09060950 |
| `track-status-runs-the-script` | 2026-09-14（§7.4） | 3/3 PASS | US$0.05053910 |

三個 case 一輪合計約 US$0.24（`CLAUDE.md`「Before pushing」引用的數字；§3 的 9 個 run 合計 US$0.24146）。差距文件 MP-05 的規則：任何一個 case 從 3/3 掉下來，就把那條 description 還原。

## 7. Eval before/after

尚待主 session 用付費的 `claude plugin eval` 於改前（`main` 5e1a29f）與改後（本分支）各跑一輪三個 case（`--runs 3`）後補上；本輪的執行者依指示沒有跑它。

## 8. 沒動的東西

- `README.md:135` 的 `/cai:debug` 表格列是舊 description 的改寫（不是逐字引用），不在 19 條之內，未動。
- `scripts/validate.py:231-233` 的歷史註解（git-sweep 加入時「reads 5674 of 5697」「142 characters against 23 of headroom」）是當時的量測紀錄，未改寫；新的說明加在 `ALWAYS_ON_CEILING` 正上方。
- `docs/rule-provenance.md` 沒有任何條目引用 description 行，不需同步。
- `MANUAL.md`、`docs/` 其他檔案沒有逐字引用這 19 條的舊文（以舊句片段 grep 過，0 命中）。
