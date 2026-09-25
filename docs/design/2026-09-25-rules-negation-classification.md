# rules 否定句分類（MP-07 第一個 PR）

對應 `docs/design/2026-09-25-mattpocock-skills-gap-analysis.md` 的 MP-07：「29 條各歸一類……分類本身先出一個 PR，改寫是第二個。」這一份只分類、不改任何出貨檔。

## 名詞

- 拉取請求（PR）：一次送審的變更；MP-07 拆成兩個，這份是第一個。
- 對話工作階段（session）：Claude Code 從開啟到關閉的一次對話。
- 技能（skill）／代理（agent）：plugin 出貨的兩種元件，前者是一段被指令或模型觸發的程序，後者是被派去做一件事的子模型。
- 掛鉤（hook）：Claude Code 在工具呼叫前後自動執行的程式。cai 出貨的命令護欄（`bash_guard`）在每個 shell 指令前跑、會擋「在 `main` 上 commit」這類指令；本 repo 另有一個 Edit／Write 之後跑 `validate.py` 的掛鉤（PostToolUse hook）。
- 搜尋樣式（pattern）：交給 Grep 工具的正規表示式；Grep／Glob 是本 session 用來搜內容／搜檔名的兩個工具。
- 層級（tier）：`model-selection.md` 把工作分成的四層（program／chore／build／think），每層對到一個模型。
- 漂移／未發版（DRIFT／UNRELEASED）：`validate.py` 對 Codex 產物的兩種 FAIL——產物與來源不一致、或一致但版本號沒有往上調。Codex 是 OpenAI 的同類工具，`plugins/cai-codex/` 是給它的版本。
- 出貨規則檔（rules）：`plugins/cai/rules/*.md` 八個檔，`/cai:setup` 把它們複製進 `~/.claude/rules/`，之後每個 session 都載入（`plugins/cai/skills/setup/SKILL.md:27-28`）。
- 硬護欄（hard guardrail）：一條必須留著的禁止句，旁邊配一句正向目標。
- 可引導（steerable）：可以改寫成正向目標句而不失去原意的句子。
- 非禁止句（not-a-prohibition）：字面命中 `Never`／`No ` 等，但不是在禁止什麼——描述、標題、註解。
- 命中（hit）：搜尋 pattern 在某一行匹配到一次；一個句子跨兩行、兩行都匹配，就是兩個命中、一個句子。
- 帳本（ledger）：`docs/rule-provenance.md`，記錄每條硬規則來自哪一次失敗；每個條目有 `Rule:`（規則原句）、`Cited by:`（原句住在哪個檔的哪一節）、可選的 `Restated in:`（同一條規則在別處的重述）與 `Shared value:`（各處必須一致的數字）。
- 出處探針（`provenance.py`）：`plugins/cai/scripts/provenance.py`，`validate.py` 每次都跑它；它把 `Rule:` 原句正規化後，檢查是否仍是 `Cited by:` 那一節的子字串（`provenance.py:253-259`）。
- 評測（eval）：`claude plugin eval` 跑的測試；一個評測案例（case）是一個目錄，內含提示（`prompt.md`）與幾個判分器（grader，`graders/*.md`），判分器對模型最後一則訊息或工具呼叫做比對。
- 引導詞（leading word）：對方文件的用語——模型預訓練裡已有的緊湊概念，用一個詞代替一段話。
- 無效句（no-op）：對方文件的用語——模型不寫也會照做的句子。
- 行數上限（`RULES_LINE_CEILING`）：`scripts/validate.py:370-373`，每個 rules 檔最多 59 行。
- 產生器（`gen-codex.py`）：`scripts/gen-codex.py`，從 `plugins/cai/` 產生 Codex 用的 `plugins/cai-codex/`，rules 也在其中（`plugins/cai-codex/rules/*.md` 八個檔存在）。

## 範圍與數字

- 基準：`main` `5e1a29f`（cai 1.32.1，2026-09-25）。
- 搜尋：Grep 工具、pattern `\b(Never|never|Don't|don't|Do not|do not|Skip|No )\b`、範圍 `plugins/cai/rules/*.md`。**29 個命中**，與差距文件 `:249` 的 29 一致；分佈也一致（workflow.md 8、epistemics.md 5、model-selection.md 5、option-explainer.md 5、coding.md 3、documentation.md 2、communication.md 1、memory.md 0）。
- 29 個命中對應 **28 個句子**：`workflow.md:41-42` 一句跨兩行，兩行各命中一次。
- pattern 是大小寫敏感的，漏掉三種形狀，列在最後一節「順帶」，不納入本次分類。
- 來源：`mattpocock/skills` 的 `skills/productivity/writing-for-agents/SKILL.md` §Leading words 的 Negation 段（`:74`）：禁止句把被禁止的行為拉進上下文（context）、讓它更可用；改寫成目標行為；禁止句只留給無法正向表述的硬護欄，且要配一句正向目標。§Pruning（`:78-81`）：單一出處、無效句測試是相對於模型的、用跑的裁決。
- cai 自己已有的診斷：`GUIDE.md:85-91`「看到 never／always／must 就問是誰在擋；答案是『模型記得』就放錯元件」——問的是執行機制，不是措辭。`GUIDE.md:137-145`：「Never commit or push unless I explicitly ask」刻意留在散文，因為 hook 看得到指令、看不到對話；它的鄰句「never work directly on main」則由 `bash_guard` 擋。

## 分類原則

三類的定義在「名詞」；判到哪一類，用兩個測試，依序：

1. **正向版本會不會少掉一半意思。** 差距文件 `:256` 的例子：「Never guess or fabricate」改成「Say so when unsure」，「fabricate」（明明不確定卻寫得像確定）就不見了。少掉的，是硬護欄。
2. **句子的主詞是不是一個對外、難回頭的動作。** commit／push、裝套件或改環境、在 `main` 上動手、宣稱「做完了」——這四種動作各有一條句子，禁止句的工作是在**動作發生的那一刻**被認出來，正向句做不到這件事。這一類也留硬護欄，即使正向改寫在字面上等價。`GUIDE.md:135-145` 與帳本把這些當硬規則看，本文件沿用。

其餘的，主詞是輸出的形狀或措辭（列表還是段落、註解寫什麼、跳脫怎麼寫、選哪一個 tier），全部可引導。

**結果：硬護欄 5、可引導 20、非禁止句 4。**

| 檔案 | 命中 | 硬護欄 | 可引導 | 非禁止句 |
|---|---|---|---|---|
| workflow.md | 8 | 3 | 4 | 1 |
| epistemics.md | 5 | 2 | 2 | 1 |
| model-selection.md | 5 | 0 | 4 | 1 |
| option-explainer.md | 5 | 0 | 4 | 1 |
| coding.md | 3 | 0 | 3 | 0 |
| documentation.md | 2 | 0 | 2 | 0 |
| communication.md | 1 | 0 | 1 | 0 |
| memory.md | 0 | — | — | — |
| **合計** | **29** | **5** | **20** | **4** |

五條硬護欄裡有三條旁邊**已經有**正向句，不必加；兩條要加一句（`workflow.md:20`、`:21-22`）。

## 逐句表

「原句」是完整句子（跨行的已接回）。「提議文字」：可引導的是整句改寫；硬護欄的是要放在旁邊的正向句，或指出已有的；非禁止句寫「不改」。「帳本」欄寫這一句與 `docs/rule-provenance.md` 的關係：是不是某條目的 `Rule:` 原句、住不住在某個 `Cited by:` 指到的節。

| # | 位置 | 原句 | 類別 | 提議文字 | 帳本 |
|---|---|---|---|---|---|
| 1 | `coding.md:13-14` | Skip error handling for cases that can't occur — but if the skeptic pass finds a real path to that state, it's not impossible; handle it. | 可引導 | Handle only the errors that can actually occur — and if the skeptic pass finds a real path to a state, it can occur; handle it. | 無（coding.md 沒有條目） |
| 2 | `coding.md:19` | Don't improve/refactor/reformat code that isn't broken. | 可引導 | Improve, refactor or reformat only code that is broken; the rest stays as it is. | 無 |
| 3 | `coding.md:21` | Don't delete pre-existing dead code unless asked — mention it instead. | 可引導 | Leave pre-existing dead code in place and mention it; delete it only when asked. | 無 |
| 4 | `communication.md:8` | Be concise. Lead with the answer, then reasoning. No filler preamble. | 可引導 | Be concise. The first sentence is the answer; the reasoning follows it. | 住在 § Communication（帳本 `:105` 的 Cited by），不是 Rule 句（Rule 是 `:3-7`）；不動帳本 |
| 5 | `epistemics.md:4` | Not sure? Say so. Never guess or fabricate. Label unverified claims as assumptions. | **硬護欄** | 正向句已在兩側：「Say so.」「Label unverified claims as assumptions.」——不加 | 無（§ Epistemics 未被引用） |
| 6 | `epistemics.md:7` | State remaining uncertainty plainly; don't present a shaky answer as settled. | 可引導 | State remaining uncertainty plainly; a shaky answer goes out marked as shaky. | 無 |
| 7 | `epistemics.md:11-13` | Stop and ask only when the decision is hard to reverse, materially widens scope, or interpretations differ enough to mean different work. Then name the options; don't pick silently. A simpler approach existing is a one-line note, not a full stop. | 可引導 | （只改中間那句）Then name the options and say which one you would take. | 住在 § When to stop and ask（帳本 `:42`），不是 Rule 句（Rule 是 `:14-17`）；不動帳本 |
| 8 | `epistemics.md:20-21` | No contradiction with the line above: that one bans the tool for a question the user asked *you*. This section governs a decision only you are blocked on. | 非禁止句 | 不改（「No contradiction」是陳述，任務書的例子） | 住在 § How to ask（帳本 `:35`），不是 Rule 句 |
| 9 | `epistemics.md:34-36` | Before claiming a task complete, run the actual build/tests and read the real output. Never report success based on tool output you suspect is stale or "contaminated" — if you cannot verify, say so explicitly instead of assuming success. | **硬護欄** | 正向句已在兩側：「run the actual build/tests and read the real output」「if you cannot verify, say so explicitly」——不加。主詞是「宣稱做完」，原則 2 | 住在 § Verification & Completion（帳本 `:49`），不是 Rule 句（Rule 是 `:37-40`） |
| 10 | `documentation.md:10-11` | Validate every Mermaid block before delivering: check syntax, node/edge references, and that it renders — never ship a diagram you haven't confirmed parses. | 可引導 | Validate every Mermaid block before delivering: check syntax, node/edge references, and that it renders — a diagram ships only after you have confirmed it parses. | 無（documentation.md 沒有條目） |
| 11 | `documentation.md:26-31` | Don't hand-escape special characters (`<`, `>`, `&`, etc.) as HTML entities (`&lt;`, `&gt;`) or URL-encoded sequences inside Mermaid source. Instead wrap the label in double quotes (`A["text"]`), which Mermaid parses literally, or reword to avoid the character. Only use Mermaid's own numeric entity syntax (`#60;`, `#62;`) as a last resort if the character is unavoidable and quoting still fails to parse. | 可引導 | Special characters (`<`, `>`, `&`, etc.) inside Mermaid source go in a double-quoted label (`A["text"]`), which Mermaid parses literally, or get reworded away. Only use Mermaid's own numeric entity syntax (`#60;`, `#62;`) as a last resort if the character is unavoidable and quoting still fails to parse. ——改寫後 `&lt;` 這類錯誤寫法不再出現在檔裡；這正是對方主張的效果，也是唯一有風險的一條：改後模型若仍手動跳脫，就是把它移回硬護欄的證據 | 無 |
| 12 | `model-selection.md:9-10` | **program** — a deterministic check settles it: does the file/heading/path exist, does the test command exit 0, is the branch protected. No judgement, no model. | 非禁止句 | 不改（「No judgement, no model」是這一層的定義） | 住在 § Layers, cheapest first（帳本 `:91`），不是 Rule 句（Rule 是 `:6-8`） |
| 13 | `model-selection.md:26-28` | Before delegating via the Task tool or a subagent, check whether a program layer check already answers it. If not, judge task complexity and pick the cheapest tier that can do it reliably. Never default to the strongest. | 可引導 | （只改末句，併入前句）If not, judge task complexity and pick the cheapest tier that can do it reliably; a stronger tier is reached on evidence. | 無（§ Model selection for tasks 未被引用） |
| 14 | `model-selection.md:29-32` | Tiers are named for the kind of work, not for a model. Which model each one resolves to lives in `plugins/cai/models.json` and is applied to every component by `plugins/cai/scripts/gen-models.py`, so re-tiering is one line there — never a hand-edit of a component's frontmatter. | 可引導 | （只改末段）so re-tiering is one line there; every component's frontmatter is generated from it. | 無 |
| 15 | `model-selection.md:37-38` | Unsure between two tiers → start cheaper; escalate only on evidence (failed attempt, discovered ambiguity), never because it "might" be hard. | 可引導 | Unsure between two tiers → start cheaper; escalate only on evidence already in hand (a failed attempt, a discovered ambiguity). | 無 |
| 16 | `model-selection.md:39-41` | Prefer the cai plugin agents when they match. Each one already carries its own tier, so name the agent and let its frontmatter decide the model — do not restate the model in prose. | 可引導 | （只改末段）so name the agent and let its frontmatter decide the model — the frontmatter is the one place the model is named. | 無 |
| 17 | `workflow.md:2-3` | In a git repo, before touching code: switch to master/main, pull latest, then create a branch — make changes there, never directly on master/main. | **硬護欄** | 正向句已在前面：「create a branch — make changes there」——不加。這是 29 條裡唯一由 `bash_guard` 執行的（`GUIDE.md:142-145`），散文只是預告 hook 會擋什麼 | 住在 § Workflow（帳本 `:98`），不是 Rule 句 |
| 18 | `workflow.md:10-12` | When the project already has tests, loop on verifiable goals (don't add a harness uninvited; suggest it if missing): validation → test invalid inputs; bug → reproduce in a test; refactor → tests pass before and after. Run tests before saying it's done. | 可引導 | （只改括號）(a missing harness is suggested first and added once asked) | 住在 § Workflow，不是 Rule 句；不動帳本 |
| 19 | `workflow.md:13-15` | A large multi-file change runs in checkpointed units, never as one long edit: an interruption must not leave work half-done or the tree incompilable. Keep responses concise as you go (no large summaries) so the budget goes to the work. | 可引導 | （只改第一句）A large multi-file change runs in checkpointed units: after any interruption the tree still compiles and every finished unit stands on its own. ——順便收掉同句的「must not」（pattern 沒抓到） | 住在 § Workflow，不是 Rule 句；不動帳本 |
| 20 | `workflow.md:16-19` | Plans are written with incomplete information. When implementation hits something the plan didn't anticipate, take the conservative option, log the deviation and its reason (an `implementation-notes.md` for long runs), and keep going — then report the deviations with the result. Silently re-scoping hands back a change I never approved. | 非禁止句 | 不改（「a change I never approved」是理由裡的描述，不是禁止） | 住在 § Workflow，不是 Rule 句 |
| 21 | `workflow.md:20` | Never commit or push unless I explicitly ask. | **硬護欄** | 加在同一個 bullet 後面：Until then the work stays in the working tree. ——`GUIDE.md:137-140` 說明它刻意留在散文；原則 2 | 住在 § Workflow，不是 Rule 句（帳本沒有這條的條目）；`GUIDE.md:137` 的轉述句仍為真 |
| 22 | `workflow.md:21-22` | Never install packages or otherwise change the environment (`pip install`, `npm i -g`) without asking first — least of all on a dirty working tree. | **硬護欄** | 加在同一個 bullet 後面：Ask first, naming the package and why it is needed. ——原則 2；也是 29 條裡**唯一的帳本 Rule 句**。字面上「Ask before installing … — above all on a dirty working tree」是等價的正向版本，主 session 若改判可引導，帳本 `:97` 必須同一個 edit 更新 | **是 Rule 句**：`workflow-ask-before-environment-changes`，帳本 `:97`（Rule）、`:98`（Cited by § Workflow）。加句放在原句後，原句仍是該節的子字串，`provenance.py` 不受影響 |
| 23 | `workflow.md:41-42`（2 個命中） | Bar: a multi-step procedure likely to recur. Don't propose for one-off tasks or trivial single commands, and don't re-propose one the user declined. | 可引導 | Bar: a multi-step procedure likely to recur; a declined proposal stays declined. ——「one-off／trivial」是門檻的反面，門檻本身已經說了 | 無（§ Recurring procedures → skills 未被引用） |
| 24 | `option-explainer.md:2-3` | Only when a reply is about to offer two or more ways forward. If the user has already said "you pick", decide and answer — do not list. | 可引導 | （只改第二句）If the user has already said "you pick", decide and answer with that one pick. ——仍是 2 行 | 無（§ Presenting options 未被引用；帳本引的是 § Before the list） |
| 25 | `option-explainer.md:21-23` | Each option is a title line, then these six as a numbered list — one field per item, its label first. Never a paragraph with the six run together: every field is still there and none of them can be found. | 可引導 | Each option is a title line, then these six as a numbered list — one field per item, its label first, so that a reader finds every field by its label and can compare it across options. ——仍是 3 行；形狀本身由 `options_lint.py` 檢查（`GUIDE.md:104-108`） | 無 |
| 26 | `option-explainer.md:34-35` | End with "if you would rather not weigh it, pick X, because ...", plus the condition that would make X the wrong pick. Never end on "it depends". | 可引導 | End with "if you would rather not weigh it, pick X, because ...", plus the condition that would make X the wrong pick; the closing sentence names X. ——仍是 2 行 | 無 |
| 27 | `option-explainer.md:39` | # Self-check before sending — any no, do not send | 可引導 | # Self-check before sending — every box ticked, then send ——仍是 1 行；「any no」的 no 是名詞，但「do not send」是門檻，改成同義的正向門檻 | 無 |
| 28 | `option-explainer.md:56-59` | 59 lines by validate.py's count; wc -l agrees only with the trailing newline. 40 -> 45: six fields plus three ELI5 checks do not fit. 45 -> 56 for #73: the fields were here and their layout was not. 56 -> 59: a format difference described in prose cannot be compared against another. | 非禁止句 | 不改（維護者的 HTML 註解，「do not fit」是敘述；註解隨檔案一起被複製進 `~/.claude/rules/`，這件事本文件不處理） | 無 |

表裡 28 列＝28 個句子；第 23 列算 2 個命中，合計 29。

### 帳本對照的結論

- `Rule:` 原句：29 個命中裡只有一個——第 22 列（`workflow.md:21-22`，帳本 `:97-98`）。它歸硬護欄，第二個 PR 只在它後面加一句，原句不動，`provenance.py` 的 `rule_quote_in_cited_section` 不受影響。
- `Restated in:`／`Shared value:`：29 個命中沒有任何一個出現在這兩種行裡。帳本 `:25` 的「Two lanes, never three」是一句重述，但它住在 `plugins/cai/skills/track/references/stage-build.md`，不在 rules，不在本任務範圍。
- 住在 `Cited by:` 指到的節、但不是 Rule 句的可引導句有四條：第 4（§ Communication）、7（§ When to stop and ask）、18、19（§ Workflow）列。改它們時該節的 Rule 原句仍在，探針照常通過；`validate.py:410-420` 每次都跑它，所以第二個 PR 不必另外做什麼，只要看它印 PASS。

## 量測：eval 看得到 rules 嗎

**看不到。** 四項證據，都是一手：

1. plugin 本身不載入 rules：`plugins/cai/.claude-plugin/plugin.json` 只有 `skills` 一個路徑鍵（`:9`），Grep `rules` 於該檔零命中。rules 進入一個 session 的唯一路徑是 `/cai:setup` 把它們複製進 `~/.claude/rules/`（`plugins/cai/skills/setup/SKILL.md:27-28`；`scripts/validate.py:339-340` 的註解說的是同一件事；README.md:463）。
2. eval 的每個 run 有自己的 `config`／`home`：pb02 的探針 (e)，`--keep-temp` 留下的 `claude-eval-*/` 內含 `config`、`home`、`out`、`tmp` 四個子目錄（`D:/project/claude-all-in-one/docs/design/2026-09-12-pb02-plugin-evals-probes.md:22`——這份與 high-level 都在同機另一個 clone，本 checkout 的 `docs/design/` 只有 measurement 那份）。high-level 文件把它記成 C12「`rules/*.md` 在 run 裡是死的」（`2026-09-12-pb02-plugin-evals-high-level.md:34`），並在範圍外明講「不測 `plugins/cai/rules/` 那一層……仍只能靠人工清單」（`:440`）。
3. 三個 case、11 個 grader 量的都是 skill 側的句子：`options-six-fields` 的六個標籤 grader 對 `skills/options/references/template.md`（`graders/label-eli5.md:8`），`reads-options-references` 對 `skills/options/SKILL.md:21-29`；`track-status-runs-the-script` 對 `skills/track/SKILL.md:21-25`；`design-gate-is-a-menu` 三個對 `skills/track/references/approval-gates.md:68-72`。Grep `rules` 於 `plugins/cai/evals/` 零命中。沒有任何一個 grader 的比對字串來自 29 句中的任何一句。
4. 任務書提到的 `case.yaml` 不存在：Glob `plugins/cai/evals/**/case.yaml` 零檔；一個 case 就是 `prompt.md` 加 `graders/*.md`（Glob `plugins/cai/evals/**/*` 共 14 個檔）。

這對差距文件 `:254` 的判準——「改前改後各跑一次三個 case；如果看不出差別，就寫看不出差別，不繼續改」——的意思是：**結果在跑之前就決定了**。三個 case 讀不到 `plugins/cai/rules/`，判分器也不比對這 29 句裡的任何字，改前改後必然同分；花掉的 US$0.24（`2026-09-12-pb02-plugin-evals-measurement.md:103`）買到的是一個與改寫無關的「無差別」。照字面執行，第二個 PR 會因為一個非觀測而停下。

本 repo 沒有別的方法能量這件事，逐一查過：`scripts/activation.py` 數的是 skill／agent 被用過幾天（`:2-16`），不是規則被遵守的程度；`tests/review-benchmark/` 量 verify 四鏡抓到什麼；`validate.py` 只查形狀。對方自己的說法是無效句「用跑的來裁決」（`writing-for-agents/SKILL.md:81`），而這裡沒有任何東西會跑 rules。要不要在沒有量測的前提下做第二個 PR，是主 session 的決定，本文件不替它選；三種讀法：(a) 判準不適用，憑本分類就做；(b) 照字面，做到本 PR 為止；(c) 等有一個能載入 `~/.claude/rules/` 的量測再說——那是另一條 track，repo 裡沒有。

## 第二個 PR

若主 session 決定做，範圍就是下面這些，一句不多：

**改寫（20 個命中、19 個句子）**：第 1、2、3、4、6、7、10、11、13、14、15、16、18、19、23、24、25、26、27 列，提議文字照逐句表。

**加正向句（2 條硬護欄）**：第 21 列（`workflow.md:20`）、第 22 列（`workflow.md:21-22`），各在原 bullet 後加一句，原句一字不動。第 5、9、17 列的正向句已在，不動。

**不動（4 條非禁止句）**：第 8、12、20、28 列。

**帳本**：零個條目需要改。第 22 列的 Rule 句保留在原位；四條住在被引用節裡的改寫（第 4、7、18、19 列）不碰各自那一節的 Rule 句。`validate.py` 跑 `provenance.py` 會證實這件事——若它印出 `rule_quote_in_cited_section` FAIL，就是改寫碰到了不該碰的句子，不是要去加條目（`provenance.py:26-30`、`:353-356`）。

**第二個 PR 會撞到的檢查**，逐一列出，都在 `scripts/validate.py`：

| 檢查 | 位置 | 對第二個 PR 的意思 |
|---|---|---|
| 行數上限 59 | `validate.py:370-373` | `option-explainer.md` 現在**正好 59 行**（其他：model-selection 44、workflow 42、epistemics 40、documentation 36、coding 21、memory 11、communication 10）。第 24–27 列的四個改寫各自維持原行數（表裡已標）；`workflow.md` 加兩句仍在上限內。多一行就要一個人的決定（`validate.py:361-369`） |
| 字面契約 | `validate.py:328-337` | `option-explainer.md` 必須仍含 `options_lint.py` 與 `(recommended)` 兩個字串；四個改寫不碰 `:36-37`、`:40` |
| 模板不得重述 rules | `validate.py:435-469` | 改寫後的句子不能與 `templates/CLAUDE.md.tpl` 的 bullet 或 `templates/CLAUDE-project.md.tpl` 的句子相同；提議文字都是新句，撞到的機率低，但要看它印 PASS |
| 出處探針 | `validate.py:410-420` | 見上 |
| Codex 產物 | `CLAUDE.md` §Who a file is for | rules 會被 `gen-codex.py` 複製進 `plugins/cai-codex/rules/`，所以要 `python scripts/gen-codex.py` 再 `--release <更大的版本>`，否則 `validate.py` 報 DRIFT／UNRELEASED；Edit 後 PostToolUse hook 先印的那一次 FAIL 是預期的 |

**改完之後**：使用者端的 `~/.claude/rules/` 是舊副本，要重跑 `/cai:setup` 才換（差距文件 `:256` 的第二個風險）；本 repo 自己因為 `CLAUDE.md` 直接 `@` 匯入 rules，改完立刻生效。`GUIDE.md:137`、`:142` 兩句對 workflow.md 的轉述在第二個 PR 後仍為真，不必改。

## 順帶：pattern 沒抓到的否定句

大小寫敏感的 pattern 漏掉三種形狀，都不在 29 條裡；主 session 要不要把它們併進第二個 PR，本文件不決定：

- `memory.md:4`「Do NOT record implementation details that evolve with the code …」——大寫 `NOT`，整個 memory.md 因此零命中。以上面的原則看是可引導（主詞是記什麼），正向句其實已在前一個 bullet「Record only stable facts」。
- `workflow.md:14`「must not leave work half-done」——`must not` 不在 pattern 裡；第 19 列的改寫已順帶收掉。
- `workflow.md:15`「(no large summaries)」——小寫 `no`；第 19 列的改寫沒有動它。

## Sources

- 任務來源：`docs/design/2026-09-25-mattpocock-skills-gap-analysis.md:243-256`（MP-07）；`:249` 的 29 與本次 Grep 一致。
- 對方文件：`mattpocock/skills` `skills/productivity/writing-for-agents/SKILL.md`（scratchpad 內 shallow clone，`:61-74` Leading words 與 Negation、`:76-81` Pruning，一手）。
- cai 側：`plugins/cai/rules/*.md` 八個檔逐行讀；`docs/rule-provenance.md` 全文（12 個條目）；`plugins/cai/scripts/provenance.py:33-99`、`:247-296`；`scripts/validate.py:320-420`、`:427-469`；`GUIDE.md:85-121`、`:135-145`；`plugins/cai/skills/setup/SKILL.md:11-34`；`plugins/cai/.claude-plugin/plugin.json`；`plugins/cai/evals/` 三個 `prompt.md` 與四個 grader 檔逐字讀，其餘七個 grader 由 Glob 確認存在；`scripts/activation.py:1-37`；README.md:461-463、`:612-633`。
- eval 能不能看到 rules：本 checkout `docs/design/2026-09-12-pb02-plugin-evals-measurement.md:20-28`、`:103`；同機另一個 clone `D:/project/claude-all-in-one/docs/design/2026-09-12-pb02-plugin-evals-probes.md:22`、`2026-09-12-pb02-plugin-evals-high-level.md:34`、`:440`。
