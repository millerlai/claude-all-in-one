# gap03-review-benchmark — measurement

本輪唯一寫數字與但書的地方（`## Implementation spec`〈measurement 檔〉，
`docs/design/2026-09-14-gap03-review-benchmark-detail.md:611-625`）。以下四句
必寫句逐字照抄，供 V13 grep（AC11）：

1. 5 筆樣本算不出有統計意義的 F1，本輪的數字不是基線。
2. 標註者就是這些 lens 的作者，所以標註與 lens 的判準之間沒有獨立性。
3. address rate 是人工清點的，來源是各條 track 的 `state.md` verify 列，而
   `.claude/track/` 不在 git 裡。
4. AC6 那次實跑的單價是多少、那個數字從哪裡來：**取不到**——四鏡在本 session
   內派工（approach A），單次呼叫的美金花費沒有暴露給這個 session；能量到的
   只有每個 lens 完成通知自帶的 token／tool-use／耗時數字（見下方「AC6 實跑
   的報表」一節），不是美金。approach C（`claude -p` headless）的單價另有
   實測，見下方「C probe」一節，那個數字不是 AC6 實跑本身的單價，是同一支
   `security-reviewer` lens 換一條路徑跑一次的單價。

## AC6 實跑的報表（單元 7，2026-09-14）

案例：`argv-echo-in-run`（`base_sha` 18c9bd3，`base_ref`
`origin/backup/ticket-integration-5c0d4ec`）。照
`scripts/review-benchmark-procedure.md` 九步驟跑兩次，`findings.json` 兩份都
落在 scratchpad（不進 git，計分器讀完即可丟）。

`python scripts/review_benchmark_score.py --collection tests/review-benchmark
--findings <run1> --findings <run2>` 的輸出，AC7 的 2N 列（N=1）：

| case | run | tp | fp | fn | precision | recall | f1 | f1_delta | unscored | duplicate | failed_lenses |
|---|---|---|---|---|---|---|---|---|---|---|---|
| argv-echo-in-run | 1 | 1 | 1 | 0 | 0.5000 | 1.0000 | 0.6667 | - | 20 | 0 | |
| argv-echo-in-run | 2 | 1 | 0 | 0 | 1.0000 | 1.0000 | 1.0000 | +0.3333 | 17 | 0 | |

（另外四筆樣本印成 `no run for this case`，因為本輪只跑了一筆樣本，符合
`score_all()` 的規則：沒有跑過的 case 照印一列，不當成 0 分。）

`security` 鏡是這筆樣本唯一有標註的鏡（`expected` 只列 `security`，
`expected_absent` 是空陣列）；`correctness`／`conformance`／`coverage` 三鏡
在這筆樣本上的所有回報全部落進 `unscored`（本輪 20、17 兩個數字的絕大部分）。
run 1 的那一個 FP 是 `security` 鏡自己另一條 Minor（`ref` 引數注入疑慮，行
141）沒有落進標註的 ±3 容忍窗，因此算 FP，不是模型誤報一個不相干的東西。

**兩跑對同一個缺陷的 severity 不一致，逐字記下：** run 1 的 `security` 鏡把
`ticket_backend.py:97/100`（`run()` 兩個 print 站把含完整留言內容的 argv 印
出）判 **Blocker**；run 2 的同一支鏡對同一個缺陷判 **Major**。這正是設計要
量的「同一缺陷、兩次跑、severity 一致率」那一格——本輪只有一筆命中，一致率
是 0/1。

## C probe（單元 7，approach C 的單價實測）

`claude -p --plugin-dir plugins/cai --agent cai:security-reviewer
--output-format json --max-budget-usd 2.00 "<prompt 交付同一份 diff.patch 與
同一組 security 四個 hunt item>"`，從 repo 根跑一次：

- Exit code 0；agent 名 `cai:security-reviewer` 被接受，沒有任何錯誤。
- `total_cost_usd` = US$0.4395868（本輪唯一一筆有美金數字的花費，D13 的
  `--max-budget-usd 2.00` 封頂，離上限還很遠，沒有撞到 budget-limit）。
- `usage`：`input_tokens` 14、`cache_creation_input_tokens` 57718、
  `cache_read_input_tokens` 243159、`output_tokens` 24548（其中
  `thinking_tokens` 20985）。`modelUsage` 列出兩個模型鍵：
  `claude-haiku-4-5-20251001`（inputTokens 1077、outputTokens 15、
  costUSD 0.001152）與 `claude-sonnet-5`（inputTokens 14、
  outputTokens 24548、cacheReadInputTokens 243159、
  cacheCreationInputTokens 57718、thinkingTokens 20985、
  costUSD 0.4384348）——兩者相加等於 `total_cost_usd`。`num_turns` = 10。
- 找到的缺陷與 run 1 的 `security` 鏡一致：同一個 `file:line`
  （`ticket_backend.py:97`／`:100`）、同一個成因（PATCH 分支把留言內容塞進
  argv，`run()` 無條件印出）、同一個 severity（Blocker）。
- 工具集是否受 `tools:` 約束：**有部分證據，不是全部**。回應文字裡看得到它
  讀過 `.claude/cai-review.md`（這份審查政策檔）、引用了 `preflight.py:212-220`
  與只存在於 `main` 分支（`913c721`）的 `_argv_summary()`——三者都落在
  `cai:security-reviewer` 允許的工具集（Read／Grep／Glob／`git diff`／`log`／
  `show`）之內，沒有出現任何超出這個集合的動作痕跡；但 JSON 裡的
  `permission_denials` 是空陣列，這既可能是「從沒試過越權工具」也可能是
  「試過但沒被記錄」，兩者都說得通，本階段沒有更進一步的證據分辨。
- 認證來源的觀察，逐字記下（stdout 第一行，JSON 結果之前）：「claude.ai
  connectors are disabled because ANTHROPIC_API_KEY or another auth source is
  set and takes precedence over your claude.ai login · Unset it to load your
  organization's connectors」——這次呼叫走的是環境變數裡的 token，不是 owner
  互動登入的 claude.ai 帳號。

## C22 的 fenced-JSON 觀察

單元 7 兩次跑、四鏡各一次，共八次派工都在散文報告後面多附了一塊
` ```json ` 區塊（欄位 `file`／`line_start`／`line_end`／`severity`／
`cause`）。八次裡，JSON 區塊的內容全部與同一次回應的散文找到的東西一致——
沒有一次 JSON 區塊多報、少報，或報出與散文矛盾的東西。這塊 JSON 從未被拿去
計分（決定一）；上面這一段本身也不是分數的來源，只是觀察記錄。

## address rate（AC8，兩個率）

`tests/review-benchmark/address-rate.md` 十一列（`pb06-ledger-metrics`
排除，理由見下）算出的兩個率：

- 修掉率（`fixed / raised`）= 25 / 61 = 0.409836...
- 有回應率（`(fixed + triaged) / raised`）= 30 / 61 = 0.491803...

`pb06-ledger-metrics` 這一列的 `raised` 與 `left_minor` 兩格是逐字的
`UNVERIFIED` 字串，不是數字：PR #93 的描述讀得到 `fixed`＝3、`triaged`＝0，
但 Minor 的條數在原文裡讀成 4 條或 9 條都說得通，原文沒有一處數過總數
（F10）。這一列因此排除在上面兩個率的分母之外，十一列的恆等式
`fixed + left_minor + triaged == raised` 逐列核對過。

## 但書

1. D2 的跨距標註會把 recall 系統性地抬高，最寬的一個命中窗是樣本 4 的
   1429–1522 共 94 行；本輪唯一跑到的樣本 1 的窗是 97–103（±3），比那個窗
   窄得多。
2. D4 的 `unscored` 欄在本輪不小（20、17），因為多數樣本只有一兩鏡有 ground
   truth——本輪唯一跑的樣本 1 也只有 `security` 一鏡。
3. C probe 的金額是官方明說的 client-side 估算，可能與實際帳單不同
   （HLD 的 C15 引的官方句子）。
4. `--max-budget-usd 2.00` 是主 session 2026-09-14 取的**慣例預設值（下檔
   有界），不是 owner 裁決**（D13）。
5. 樣本 3、4、5 的 `diff.patch` 是修法的反向，等於把答案指給 lens 看（樣本
   5 的 diff 逐字含著被刪掉的那個測試名）；本輪唯一跑到的樣本 1 不在這三筆
   之內，但下一輪若跑到 3、4、5，這一點必須連同 recall 一起讀。
6. 樣本 5 的 `line_start` 與樣本 1、2 的 `base_ref` 在設計階段是
   UNVERIFIED，已由 build 在單元 1／5 checkout 後補實（見
   `implementation-notes.md`「Pre-build baseline」）；本輪不受影響。

## 已知限制

`.claude/track/` 不在 git 裡（`.gitignore:11`），所以上面 address-rate 表格
`source` 欄的每一條引用，在一份新 clone 上都指不到檔——想核對的人要在自己
的機器上留著那些 track 目錄才查得到（F11）。
