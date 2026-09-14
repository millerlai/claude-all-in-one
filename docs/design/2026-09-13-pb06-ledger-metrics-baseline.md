# PB-06 baseline: ledger 四個指標（issue #85）

跑法：對每個 `.claude/track/done/*` 與尚未歸檔的 `issue78-rule-guards` 各跑一次
`usage_report.py metrics --track-dir <dir>`，再跑一次
`usage_report.py metrics --days 30`。以下逐字貼輸出，未加工。

## `.claude/track/done/gap02-usage-ledger`

```
Stage metrics for .claude/track/done/gap02-usage-ledger
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=1  cycle=15:20:34  rework=3  human_signed=0/3
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=0  cycle=19:37:09  rework=3  human_signed=2/3
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=4/5  cycle=—  rework=9  human_signed=3/9
track cycle: 22:35:44

```

## `.claude/track/done/guardrail-hardening`

```
Stage metrics for .claude/track/done/guardrail-hardening
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=77:31:42  rework=3  human_signed=1/3
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=5/5  cycle=—  rework=7  human_signed=2/7
track cycle: 88:27:51

```

## `.claude/track/done/option-explainer-with-eli5`

```
Stage metrics for .claude/track/done/option-explainer-with-eli5
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:51:19  rework=3  human_signed=2/3
ship        first_pass=0  cycle=0:16:02  rework=2  human_signed=1/2
----------------------------------------
TOTAL       first_pass=4/5  cycle=—  rework=8  human_signed=4/8
track cycle: 3:28:11

```

## `.claude/track/done/pb02-plugin-evals`

```
Stage metrics for .claude/track/done/pb02-plugin-evals
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=0  cycle=0:30:57  rework=2  human_signed=0/2
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=1:21:36  rework=2  human_signed=1/2
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=4/5  cycle=—  rework=7  human_signed=2/7
track cycle: 14:31:36

```

## `.claude/track/done/pb04-security-lens`

Sanity check against the task's expected numbers: intake `first_pass=1`,
design `rework=2`, discover `—` — all three match below.

```
Stage metrics for .claude/track/done/pb04-security-lens
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=3:20:34  rework=2  human_signed=1/2
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=5/5  cycle=—  rework=6  human_signed=2/6
track cycle: 8:52:07

```

## `.claude/track/done/pr60-followups`

```
Stage metrics for .claude/track/done/pr60-followups
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=0  cycle=1:40:54  rework=2  human_signed=0/2
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=4/5  cycle=—  rework=6  human_signed=2/6
track cycle: 12:22:18

```

## `.claude/track/done/ticket-integration`

```
Stage metrics for .claude/track/done/ticket-integration
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=0  cycle=0:47:04  rework=2  human_signed=0/2
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=2:48:23  rework=3  human_signed=3/3
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=4/5  cycle=—  rework=8  human_signed=4/8
track cycle: 14:59:20

```

## `.claude/track/done/track-context-budget`

```
Stage metrics for .claude/track/done/track-context-budget
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=5/5  cycle=—  rework=5  human_signed=2/5
track cycle: 15:01:01

```

## `.claude/track/done/track-status-vocabulary`

```
Stage metrics for .claude/track/done/track-status-vocabulary
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=5/5  cycle=—  rework=5  human_signed=2/5
track cycle: 3:24:50

```

## `.claude/track/issue78-rule-guards`（尚未歸檔）

```
Stage metrics for .claude/track/issue78-rule-guards
Columns: first_pass is 1 if the stage's first attempt passed, else 0; cycle is h:mm:ss from the stage's first record to its last passed one; rework is the stage's attempt count (consecutive same-sha passed rows count once); human_signed is the share of attempts carrying a human gate record; — means the stage had no attempt at all.

intake      first_pass=0  cycle=0:42:14  rework=2  human_signed=0/2
discover    first_pass=—  cycle=—  rework=—  human_signed=—
design      first_pass=1  cycle=1:01:05  rework=3  human_signed=1/3
build       first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
verify      first_pass=1  cycle=0:00:00  rework=1  human_signed=0/1
ship        first_pass=1  cycle=0:00:00  rework=1  human_signed=1/1
----------------------------------------
TOTAL       first_pass=4/5  cycle=—  rework=8  human_signed=2/8
track cycle: 7:28:52

```

## Central：`metrics --days 30`

```
Cross-project stage metrics -- last 30 day(s)
Data start date: 2026-08-30 (nothing before this date is on file -- the ledger was not installed yet, which is different from nothing having happened).
No data for the first 14 of the requested 30 day(s) -- they are before the data start date, shown as no data rather than as 0.
Columns: first_pass and human_signed add each track's own numerator and denominator; rework and cycle are averaged across tracks that had an attempt; — means no track had an attempt in this stage.

intake      first_pass=10/19  cycle=0:14:32  rework=1.42  human_signed=1/27
discover    first_pass=3/3  cycle=0:00:00  rework=1.00  human_signed=0/3
design      first_pass=21/21  cycle=4:43:20  rework=1.62  human_signed=23/34
build       first_pass=15/19  cycle=0:35:12  rework=1.32  human_signed=0/25
verify      first_pass=19/19  cycle=0:00:00  rework=1.00  human_signed=0/19
ship        first_pass=15/19  cycle=0:21:59  rework=1.21  human_signed=19/23
----------------------------------------
TOTAL       first_pass=83/100  cycle=—  rework=1.26  human_signed=43/131
track cycle (avg): 13:12:33

gate not walked: design
```

## 實作時的判斷（spec 沒有逐字寫出的部分）

- **每個 stage 一列的 `first_pass` 顯示**：track-dir 模式印 `0`／`1`／`—`（單一數字，
  對應「該 stage 的第一個 attempt」），central `--days` 模式印 `x/y`
  （多少 track 首次就過 ÷ 多少 track 有 attempt）——因為後者本來就是跨 track 彙總。
  TOTAL 列在兩種模式下都印成 `x/y`（stage 數或 stage×track 數的分子分母），因為
  TOTAL 本身就是「比例」。
- **TOTAL 列的 `cycle` 欄**：一律印 `—`。把不同 stage 的 cycle 相加或平均沒有定義
  好的意義（各 stage 的時間區間本身會重疊），track 整體的耗時已經由獨立的
  「track cycle」那一行回答，所以 TOTAL 的 cycle 欄不重複算一次。
- **central 模式的 `rework`／`cycle` 平均，分母是誰**：只對「該 stage 有至少一次
  attempt」的 (project, track) 取平均，没有 attempt 的 track 不拉低平均值——
  跟 `first_pass`／`human_signed` 的分母（只算有 attempt 的 track）保持一致。
- **central 模式的 track cycle**：spec 只在 track-dir 模式明講 track cycle 的定義，
  沒有明講 central 彙總要怎麼算。這裡採用跟 `cycle`／`rework` 一致的規則：對每個
  (project, track) 算出自己的 track cycle，再對「有算出 track cycle」的那些
  track 取平均，印成 `track cycle (avg): h:mm:ss`。
- **`gate not walked` 的判定範圍**：以「該 stage 的 attempt 分組」為準（而非整份
  ledger 的原始列）——一個 attempt 分組只要有任何一列 `gate: human` 就算這次
  attempt 被人類簽過；design／ship 若有任何一次 attempt 通過（`passed`）但所有
  attempt 分組都沒有 `gate: human`，才印這行 footnote。central 模式下，只要任一
  (project, track) 在該 stage 觸發這個條件，就印一次（不重複列出是哪個 track）。
