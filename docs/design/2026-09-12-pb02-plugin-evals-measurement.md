# pb02-plugin-evals — 量測紀錄

軌道：`pb02-plugin-evals`．階段：build（unit 3／unit 4）。這份檔案獨立於已被
ledger 的 sha256 釘住的設計文件（`docs/design/2026-09-12-pb02-plugin-evals-detail.md`），
理由與 `docs/design/2026-09-12-pb02-plugin-evals-probes.md:4` 相同：核准後的
文件不再被附加，本輪的量測數字另外落檔（Q9，本輪已照這個作法指定檔名，未主張
成為下一輪的慣例）。

## 1. 量測條件

- 量測執行日：**2026-09-12**（unit 3 開始執行的當地日期；三次指令中最後一次
  完成時系統時鐘已跨入 2026-09-13——`aggregate-result.json` 的
  `startedAt` 落在 UTC 2026-09-13T03:59–04:01 之間，起訖詳見各 case 的
  `aggregate-result.json`。副本與結果目錄仍統一用 `2026-09-12` 這一層，不因跨
  夜而拆成兩個日期）。
- 副本落點：`$SCRATCH/pb02-eval-copy/2026-09-12/cai`（`$SCRATCH` 是本次
  session scratchpad 的根，不是個人路徑）。
- 結果目錄：`$SCRATCH/pb02-eval-results/2026-09-12/<case>/`（見下方「D7 的退
  路」，三個 case 各自一個子目錄）。
- 複製與核對指令（Git Bash，逐字）：

  ```
  mkdir -p "$SCRATCH/pb02-eval-copy/2026-09-12" "$SCRATCH/pb02-eval-results/2026-09-12"
  cp -r "$REPO/plugins/cai" "$SCRATCH/pb02-eval-copy/2026-09-12/cai"
  diff -r "$REPO/plugins/cai/evals" "$SCRATCH/pb02-eval-copy/2026-09-12/cai/evals"
  ```

  `diff -r` 無輸出，exit 0——複製與工作樹逐位元組相同，確認過才往下走。

- **D7 的退路（本輪觸發）**：設計文件的 `--case` 指名三次、單一指令的形狀在
  這次實跑**沒有成立**——`aggregate-result.json` 的 `suite.caseFilter` 只印出
  最後一個 `--case` 的值（`track-status-runs-the-script`），該次只跑了 3 個
  run 而不是 9 個，另外兩個 case 完全沒有執行。這就是 D7 標記為 UNVERIFIED
  的那個行為，本次量測把它坐實為**不可重複**。已依 `## Failure modes` 的退路
  改成三次指令，`--output-dir`／`--json` 都逐 case 拆開。已完成的
  `track-status-runs-the-script` 那一次（真花了錢的 3 個 run）保留不重跑，只
  把輸出檔搬進它自己的子目錄，避免重複花費。三次指令逐字：

  ```
  claude plugin eval "$SCRATCH/pb02-eval-copy/2026-09-12/cai" \
    --case options-six-fields \
    --model haiku --ablation none --keep-temp --max-cost-usd 5 --threshold 0 \
    --trust-plugin --no-publish \
    --output-dir "$SCRATCH/pb02-eval-results/2026-09-12/options-six-fields" \
    --json "$SCRATCH/pb02-eval-results/2026-09-12/options-six-fields/run-options-six-fields.json"

  claude plugin eval "$SCRATCH/pb02-eval-copy/2026-09-12/cai" \
    --case design-gate-is-a-menu \
    --model haiku --ablation none --keep-temp --max-cost-usd 5 --threshold 0 \
    --trust-plugin --no-publish \
    --output-dir "$SCRATCH/pb02-eval-results/2026-09-12/design-gate-is-a-menu" \
    --json "$SCRATCH/pb02-eval-results/2026-09-12/design-gate-is-a-menu/run-design-gate-is-a-menu.json"

  claude plugin eval "$SCRATCH/pb02-eval-copy/2026-09-12/cai" \
    --case track-status-runs-the-script \
    --model haiku --ablation none --keep-temp --max-cost-usd 5 --threshold 0 \
    --trust-plugin --no-publish \
    --output-dir "$SCRATCH/pb02-eval-results/2026-09-12/track-status-runs-the-script" \
    --json "$SCRATCH/pb02-eval-results/2026-09-12/track-status-runs-the-script/run-track-status-runs-the-script.json"
  ```

  `--max-cost-usd 5` 未被觸發於任一次指令（三次合計 $0.2415，遠低於 $5），所以
  `## Failure modes` 的「上限乘二、重跑一次」沒有用到。

## 2. 三段 `UNVERIFIED:` 說明（AC4）

- **preflight 先跑（T-something，`plugins/cai/skills/track/SKILL.md:48`–`:51`）**
  ：`UNVERIFIED` — 這台 Windows 機器只要授了 Bash/PowerShell，`claude plugin
  eval` 在 2 秒內整批拒絕、0 turn（C5），而 `preflight.py` 需要 shell 才能跑；
  同時 `tool_order` 這種 grader 型別本輪也從未試過（C4）。所以「preflight 早
  於任何派工」這件事寫不成一個機械可判的 case，本輪不量。
- **verify 派三個 reviewer（`plugins/cai/skills/track/references/stage-verify.md:46`–`:47`）**
  ：`UNVERIFIED` — 同樣卡在 C5（Bash 授權整批被拒），而且 `reviewer` agent 的
  定義本身就帶 `Bash(git diff:*)` 等三個工具樣式（`plugins/cai/agents/reviewer.md:6`），
  在一個未授 Bash 的 run 裡它會被降級成別的行為還是讓整個 run 被拒，本輪
  沒有人試過（C24）。所以「verify 確實派出三個 reviewer」也寫不成 case。
- **human gate 是選單（`docs/design/2026-09-12-pb02-plugin-evals-probes.md:20`）**
  ：`AskUserQuestion` 不在 eval 子行程的工具清單內（C8，已於探針階段實測坐
  實，非本輪新驗）。替代做法是 `design-gate-is-a-menu` 這個 case，對三個選單
  標籤做 contains 比對——**量到的是措辭，不是「真的開了選單」這個行為**，
  `## Verification` 已經把這句寫進 Errors 一欄，這裡重申一次以免被誤讀成行為
  證據。

## 3. 逐 run 成本表

9 個子行程（3 case × 3 run × 1 arm，`--ablation none`），全部 model `haiku`，
量測日 2026-09-12。金額來自各 case `aggregate-result.json` 的
`arms.with[].costUsd`／`turns`／`durationSeconds`；token 四欄來自對應
`claude-eval-*/out/trace.jsonl` 的 `result` 事件，逐 run 都取到了值，沒有一格
要寫 `UNVERIFIED`。

| case | run | costUsd | turns | durationSeconds | input | output | cache_read | cache_creation | tool_used grader |
|---|---|---|---|---|---|---|---|---|---|
| options-six-fields | 1 | 0.02954 | 3 | 32 | 17 | 2455 | 24970 | 11801 | FAIL (Read called 0x) |
| options-six-fields | 2 | 0.03427 | 3 | 38 | 17 | 3396 | 24976 | 11819 | **PASS** (Read called 2x) |
| options-six-fields | 3 | 0.03407 | 3 | 43 | 17 | 3375 | 24970 | 11743 | FAIL (Read called 0x) |
| design-gate-is-a-menu | 1 | 0.03222 | 8 | 27 | 66 | 1554 | 122088 | 9742 | — (no tool_used grader) |
| design-gate-is-a-menu | 2 | 0.02764 | 6 | 24 | 50 | 1370 | 88515 | 9511 | — |
| design-gate-is-a-menu | 3 | 0.02047 | 4 | 17 | 26 | 1056 | 39453 | 8973 | — |
| track-status-runs-the-script | 1 | 0.03281 | 5 | 37 | 34 | 2765 | 57907 | 10528 | — |
| track-status-runs-the-script | 2 | 0.01599 | 1 | 14 | 10 | 999 | 7522 | 8188 | — |
| track-status-runs-the-script | 3 | 0.01445 | 1 | 11 | 10 | 692 | 7522 | 8185 | — |
| **合計** | 9 | **0.24146** | 34 | 243 | 247 | 17662 | 397923 | 90490 | — |

觀察（判讀依 `## Failure modes` 的「先讀 trace 再判是 pattern 失敗還是模型失
敗」原則，逐個記，不重跑到綠為止）：

- **options-six-fields 的六欄標籤 grader 三個 run 全 PASS**——標籤本身穩定
  出現，模型忠實照 `template.md` 的 skeleton 寫。
- **`reads-options-references`（tool_used）在 3 個 run 中 1 次 PASS**（run
  2）：那一次模型真的先 `Read` 了 reference 檔（Read called 2x）才寫六欄；
  另外兩次模型直接從記憶寫出六欄，沒有呼叫 `Read`（Read called 0x）——這是
  D1 拆檔的目的展現出來的樣子：六欄標籤與工具呼叫級證據在報表上分得很開，
  不是同一件事的兩種說法。
- **design-gate-is-a-menu 三個 run 全 FAIL**：last_message 沒有出現
  `Approve`／`Changes requested`／`Reject` 三個詞（pattern not found）。這是
  措辭沒對上，不是模型退步的證據——`## Verification` 已把這個 case 定性為量
  措辭，AC7 那一節重申。
- **track-status-runs-the-script 三個 run 全 FAIL**：last_message 沒有出現
  `track_state.py`；run 2、3 只有 1 turn 就結束（`turns: 1`），偏低，依
  `## Failure modes` 的判讀順序，這個形狀更接近「模型選了別的說法或直接回答
  而沒有點名腳本」而非拒答（拒答的形狀是三個 grader 群同時全 FAIL 且
  `turns` 明顯偏低——這裡只有一個 grader，無法用「群」來分辨，如實記錄，不
  另外推測）。

## 4. E5 命中率（Q8）

- **`reads-options-references`（`tool_used: Read`）：1/3 PASS**。依 Q8 的裁
  決，`n ≥ 1` 即記「T4（`/cai:options` 的 reference 檔真的被讀）取得工具呼叫
  級證據」——**本輪達成**，命中率 `1/3` 照實記，不代表穩定，只代表這一輪至
  少觀察到一次。
- **六個 `regex` 標籤 grader：3/3 PASS**（每個 run 六欄都出現）。

## 5. AC7 — 為何不跑 `--ablation with-without`

本輪固定用 `--ablation none`，理由是「本輪不花錢去量對照組」而不是「旗標不
可用」——`--ablation with-without` 這個旗標本身探針已驗證存在
（`docs/design/2026-09-12-pb02-plugin-evals-probes.md:65` 列為「仍未驗證」的
是它的 baseline arm 實際行為與成本，不是旗標存不存在）。這是使用者已認可的
讀法（HLD:222），本輪按此執行，未嘗試對照組。

## 6. AC15 — 建議與算式

三個數字分開列，互不相加：

- **實測**：3 case × 3 run × 1 arm = 9 個子行程，model `haiku`，量測日
  2026-09-12，總金額 **US$0.24146**（第 3 節「合計」列）。
- **外推的 gate 成本**：`--ablation` 預設 `with-without`（兩條 arm，C28）。
  US$0.24146 × 2 = **US$0.48292**。**係數 2 取自工具的預設值，不是本輪實
  測**——本輪固定 `--ablation none`，沒有真的跑過對照組，所以這是外推不是
  觀測。
- **模型價格比**：**UNVERIFIED**。本輪全部跑在 `haiku` 上；換算到帳戶預設模
  型（未帶 `--model` 時使用）的任何金額都沒有依據可換算（C20，
  `docs/design/2026-09-12-pb02-plugin-evals-probes.md:46`），本文件不猜這個
  比例。

**頻率因數（每個都指得出來源，2026-09-13 於本機取得）：**

- **PR 觸發**：這個 repo 實際的合併頻率，取最近 30 天：

  ```
  git log --merges --since=2026-08-13 --oneline | wc -l
  ```

  結果：**12**（2026-08-13 至 2026-09-13，30 天內 12 次 merge commit）。這是
  量測值，不是提議值。
- **排程**：**本文件提議 cadence，非量測值**——提議「每日一次」（30 次／
  月），純粹是一個好核對的整數起點，不是根據任何既有排程資料算出來的。

**兩條路徑各自的月成本估算（每個因數的來源見上）：**

| 觸發方式 | 頻率因數 | 每次跑法 | 月成本估算 |
|---|---|---|---|
| PR 觸發 | 12 次／30 天（量測，`git log --merges`） | 若每次合併只跑 `--ablation none`（9 個子行程） | 12 × US$0.24146 ≈ **US$2.90／月** |
| PR 觸發（含 gate 對照組） | 同上 | 若每次合併改跑 `--ablation with-without`（外推係數 2） | 12 × US$0.48292 ≈ **US$5.80／月** |
| 排程 | 30 次／30 天（提議值，非量測） | `--ablation none` | 30 × US$0.24146 ≈ **US$7.24／月** |
| 排程（含 gate 對照組） | 同上（提議值） | `--ablation with-without`（外推） | 30 × US$0.48292 ≈ **US$14.49／月** |

**建議**：以 PR 觸發、`--ablation none` 起步（≈US$2.90／月，四種算法中金額最
低且頻率因數是量測值而非提議值）。理由：這一輪只有 3 個 case、11 個 grader，
訊號密度還不足以撐對照組的額外花費——先確認「PR 觸發時 eval 真的攔得住退
步」這件事本身值不值得做，再談要不要加對照組或改排程。若之後 case 數增加
到需要更頻繁的訊號，或需要量化「這個 plugin 版本相對於沒有它」的 delta，再
回頭評估 `--ablation with-without` 與排程 cadence——那兩個選項的月成本已經
列在表裡，屆時是同一份算式換一個頻率因數，不需要重新量測單次成本。

## 交叉核對

- `aggregate-result.json`（三個 case 各自一份）與 `run-<case>.json`
  （`--json` 的輸出）都落在 `$SCRATCH/pb02-eval-results/2026-09-12/<case>/`，
  不在 `plugins/cai/` 底下——`git status --porcelain plugins/cai/` 為空、
  `plugins/cai/evals/results/` 不存在（AC17，2026-09-13 核對）。
- `python scripts/validate.py` 與 `python -m pytest` 的結果見 unit 5 的驗證
  記錄（`implementation-notes.md`），本檔不重複貼。
