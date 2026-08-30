# track usage accounting — implementation notes

Build 階段的狀態表、路徑歸屬圖與偏離紀錄。設計文件是
`docs/design/2026-08-30-track-usage-accounting-detail.md`（`approved 2026-08-30`）。

## 為什麼狀態欄在這裡而不在設計文件裡

`stage-build.md` 的 Step 1 說把 `Verify with`／`Status`／`Commit` 三欄加進設計文件
自己的 `## Work breakdown`。這裡走它的備援路徑（改寫 implementation-notes），原因是
兩個程序互相牴觸：`preflight.py` 的 `artifact_unchanged` 以 ledger 記下的 sha256
比對設計文件，**只要動它一個位元組，下一次 build 的 preflight 就會判「設計在簽核後
被改過」而擋下整個 stage**。進度欄每個 unit 都要改一次，等於每個 unit 都把自己的
閘門打壞。

## 狀態表

順序執行（使用者 2026-08-30 決定），每個 unit 驗證後 commit 一次（同日明許）。

| # | Unit | Depends on | Verify with | Status | Commit |
|---|---|---|---|---|---|
| 1 | `usage_collector.py`：路徑解析、`CAI_USAGE_LEDGER`、窗內取行、requestId 去重、per-model 聚合、problems | 無 | `python -m pytest tests/test_usage_collector.py -q` | **done** | `1c72f81` |
| 2 | record 新欄位、`_fit` 的上限參數與第四步（另含 `tests/conftest.py` 的封閉性修正，見 Deviations） | 1 的回傳型別 | `python -m pytest tests/test_ledger_usage.py tests/test_ledger.py -q` | **done** | `9b239e8` |
| 3 | 集中帳本寫入、D7 的收斂對象、`synced`、導入日標記 | 2 | `python -m pytest tests/test_ledger_central.py tests/test_ledger.py -q` | **done** | `7c46514` |
| 4 | `show` 續行 | 2 | `python -m pytest tests/test_ledger_show.py tests/test_ledger.py tests/test_cli_encoding.py -q` | **done** | `7f77b96` |
| 5 | `prices.json` 出貨版、逐 model 覆寫、別名與 `<synthetic>` 解析 | ~~使用者提供單價數字~~ 已由官方定價頁解除 | `python -m pytest tests/test_prices.py -q` | **done** | `19912b9` |
| 6 | `usage_report.py` 三種查詢 | 3、5 | `python -m pytest tests/test_report.py -q` | **done** | `a57c8be` |
| 7 | `/cai:usage` skill、`models.json` 指派、`ledger.py` docstring | 6 | `python scripts/validate.py` 與 `python -m pytest -q` | **done** | `25a0186` |

Unit 5 原本標 `blocked`（等使用者提供六個識別字的實際單價）。該封鎖已解除：單價是
可查證的公開事實，主 session 於 2026-08-30 從官方定價頁第一手取得，不需要人憑記憶填。
資料見下方「價目表資料」一節。

## 路徑歸屬圖

`stage-build.md` 要求從 `## Implementation spec` 的 `Where it lives` 導出，設計文件
本身沒有這張圖。

| Unit | 擁有的路徑 |
|---|---|
| 1 | `plugins/cai/scripts/usage_collector.py`（新）、`tests/test_usage_collector.py`（新） |
| 2 | `plugins/cai/scripts/ledger.py`（record 欄位與 `_fit`）、`tests/test_ledger_usage.py`（新） |
| 3 | `plugins/cai/scripts/ledger.py`（集中寫入與 `synced`）、`tests/test_ledger_central.py`（新） |
| 4 | `plugins/cai/scripts/ledger.py`（`show`） |
| 5 | `plugins/cai/prices.json`（新）、`tests/test_prices.py`（新） |
| 6 | `plugins/cai/scripts/usage_report.py`（新）、`tests/test_report.py`（新） |
| 7 | `plugins/cai/skills/usage/SKILL.md`（新）、`plugins/cai/models.json`、`ledger.py` 的模組 docstring |

## 從歸屬圖發現的一處設計文件錯誤

設計文件 `## Work breakdown` 的 `Can run alongside` 欄寫著 unit 2 可與 4 並行、
unit 3 可與 4 並行。**這三個 unit 都改 `plugins/cai/scripts/ledger.py`**，歸屬集合
相交，依 `stage-build.md` Step 4 的條件 2 它們不能並行；該檔也明說「歸屬圖與
`Alongside` 衝突時以歸屬圖為準」。

unit 5 標的「可與 1–4 並行」則是對的：它只碰 `prices.json` 與自己的測試，與
`usage_collector.py`／`ledger.py` 不相交。

本次選擇順序執行，所以這個錯誤不影響執行；記在這裡是為了不讓它被下一個人當成
可信的並行依據。設計文件本身不改（改了會打壞 `artifact_unchanged`）。

## 交給 verify stage 裁決的事項

- **`project` 取 `os.getcwd()`，`track` 取自 `--track-dir`，兩個識別來自不同輸入**
  （`plugins/cai/scripts/ledger.py:211-212`）。設計 Decision 6 寫的是「hook payload 的 `cwd`
  直接給」——那是還有 hook 的版本留下的措辭；Q2 選了零 hook 之後，`cwd` 變成**程序的**工作目錄。
  正規流程（track skill 以相對路徑 `--track-dir .claude/track/<feature>` 呼叫）下 cwd 必然等於
  專案根，不會出錯。但手動從子目錄執行 `ledger.py append` 時，同一個專案會被**靜默記成兩個不同的
  `project`**，而分辨專案正是 UC4 與 UC9 的目的。失敗不會有任何訊息。
  可能的修法是從 `track_dir` 往上兩層推導 `project`（`<project>/.claude/track/<feature>`），讓兩個
  識別出自同一個輸入。**未在 build 階段自行更動**，因為那會偏離已簽核的設計；列為 verify 的
  correctness lens 要判的一項。

- **`show` 分不出「確實沒用量」與「導入前的舊記錄」**（unit 4）。兩者都不印續行，輸出完全相同。
  但語意不同：D11 明定舊記錄在報表裡算「未涵蓋」而非 0，確實沒用量才是真的 0。
  **資料層分得出來**（用量欄位存不存在），所以 unit 6 的 `usage_report.py` 仍能正確履行 D11；
  這純粹是 `show` 的顯示落差。未在 unit 4 修，因為設計把 `show` 定位為給人讀、`usage_report.py`
  才是正式查詢介面。verify 判是否值得補一行區別。

## 待後續 unit 覆核的事項

- **Unit 1 的 subagent 檔篩選用了 file mtime 當前置過濾，而設計文件沒有指定這個條件。**
  設計只說「讀窗內新增的 subagent transcript」，沒說那是檔案層級還是行層級的判斷。
  實作選的是：先用 mtime 決定要不要打開某個 subagent 檔，打開後對主檔與 subagent 檔
  一律套同一套行層級的 `timestamp` 窗過濾，所以毫秒邊界的正確性（D4 的「窗不重疊」）
  不依賴 mtime 的精度。
  **`## Verification` 沒有任何一列涵蓋這個邊界**，unit 1 的四條驗收也沒測到它。
  這是 unit 1 唯一沒有被驗收表釘住的部分，unit 2 與 unit 3 動到窗的兩端時要回頭看它。

## 價目表資料（unit 5 的 upstream blocker，已解除）

來源：https://platform.claude.com/docs/en/about-claude/pricing（主 session 2026-08-30 第一手取得）。
使用者原本被列為這份資料的提供者，但這是可查證的公開事實，不該由人憑記憶填。

| Model | Base input | 5m cache write | 1h cache write | Cache read | Output |
|---|---|---|---|---|---|
| `claude-opus-5` | 5.00 | 6.25 | 10.00 | 0.50 | 25.00 |
| `claude-sonnet-5` | 2.00 | 2.50 | 4.00 | 0.20 | 10.00 |
| `claude-haiku-4-5-20251001` | 1.00 | 1.25 | 2.00 | 0.10 | 5.00 |
| `<synthetic>` | 0 | 0 | 0 | 0 | 0 |

單位為 USD / 百萬 token。倍率（原文）：5 分鐘寫入 1.25x base input、1 小時寫入 2x、讀取 0.1x。

別名 `opus` / `sonnet` / `haiku` 需要解析到上面三個完整識別字；那是**查表不是前綴比對**（哪一個別名對到哪一個版本是資料，不是規則）。

`<synthetic>` 定價 0 是量出來的結論不是假設：那些記錄是 Claude Code 自己產生的通知訊息（`Please run /login`、`You've hit your session limit`），五類 token 全為 0，不是 API 呼叫。歸 0 而非 unpriced，是為了不讓「未定價金額」混進定義上就是零的項目。

## 追溯表（stage-build Step 6）

設計文件 14 條 UC/R 各自落在哪。**指不出 `file:line` 的就是沒實作**——目前沒有這樣的列。

| 設計文件的要求 | 實作落點 |
|---|---|
| UC1 per-model 分類 token | `plugins/cai/scripts/usage_collector.py:40`（五個鍵）、`:216`（逐行聚合）、`plugins/cai/scripts/ledger.py:161`（寫進 record） |
| UC2 重跑逐字相同 | `usage_collector.py:216`（requestId 去重）、`ledger.py:95`（窗下界取上一筆 `window_end`）、`ledger.py:87`（毫秒上界） |
| UC3 單 track 每 stage 與總計 | `plugins/cai/scripts/usage_report.py:326` `track_report()` |
| UC4 跨專案 N 天按 stage 分組 | `usage_report.py:434` `range_report()` |
| UC5 GAP-02 四問 | `usage_report.py:281` `_row()`（stage、model 數、unpriced、attempts 四欄同列）、`:216` `_accumulate()` |
| UC6 金額標等值 API 花費 | `usage_report.py:32` `CAVEAT`、`:294` `_price_header()`（表頭一次，不逐列重複） |
| UC7 unpriced 不得當 0 | `usage_report.py:128` `resolve_price()` 回 `None` 而非 0、`:173` `_price_bucket()`、`:259` `_unpriced_str()` |
| UC8 資料起始日與「無資料」 | `ledger.py:255` `_mark_data_start()`、`usage_report.py:383` `data_start_date()`、`:434` 的 no-data 區塊、`:138` `NO_DATA` |
| UC9 集中帳本帶 project 與 track，per-track 自足 | `ledger.py:161`（集中份加 project/track）、`usage_report.py:326`（`track_report` 完全不碰集中帳本） |
| R1 記不成帳一律留痕 | `usage_collector.py:273`（讀不到回空 dict 加 problems）、`ledger.py:161`（寫不進集中帳本設 `synced`/`sync_error`） |
| R2 零 token 成本 | **`git diff main..HEAD -- plugins/cai/hooks/` 無輸出**——整條分支零 hook 改動；記帳全在既有的 `ledger.py append` 呼叫內 |
| R3 不回填 | `ledger.py:113` `_data_start_floor()`（找不到上一筆時以導入日為地板） |
| R4 Windows／ASCII／無 BOM | `python scripts/validate.py` exit 0、0 FAIL |
| R5 集中帳本並發安全 | `ledger.py:267` `_write_line()`（沿用既有 byte-0 lock，未另寫第二套）、`tests/test_ledger_central.py` 的 8 程序測試 |

## Deviations

- Unit 1 與 2（修正）— 設計文件把 token 鍵定為**四個**，照抄 `message.usage` 頂層欄位，其中
  `cache_creation_input_tokens` 是合併值。**改為五個**：該鍵換成來源 `message.usage.cache_creation`
  底下的 `ephemeral_1h_input_tokens` 與 `ephemeral_5m_input_tokens`。
  Why: 官方定價的 cache write 有兩種費率——5 分鐘 TTL 是 base input 的 1.25x、1 小時是 2x，差 60%。
  記合併值就無法正確計價。以本 session 真實資料量測（cache_creation 共 3,104,421 tokens，1h 佔
  423,555、5m 佔 2,680,866，`claude-opus-5` base input $5/MTok）：分開計價 $20.99、全部當 5m 計
  $19.40（低估 8%）、全部當 1h 計 $31.04（**高估 48%**）。兩種單一費率都錯，方向還不可預測。
  這直接打到 AC4，也打到 GAP-02 的立意（「價值不在省錢，在能誠實講話」）。
  拆分無損：跨 40 個 session 檔、9,013 個 usage 物件實測，**每一個都有 `cache_creation`**，且
  `1h + 5m` 完全等於合計欄位，無一例外。合併值不再單獨記錄（冗餘，白吃 4096 的預算）。
  邊界：若 `cache_creation` 缺席而合計非零，記進 `problems` 指名有多少 token 無法歸類 TTL，
  不猜、不靜默丟棄。
  Cost: unit 1 與 2 已 commit，需回頭修（`usage_collector.py`、`ledger.py` 與兩個測試檔）；
  每個 model 多一個鍵，收合門檻從 12 個 model 下降（實測值由該次修正回報）。
  使用者於 2026-08-30 裁決採用拆分。

- Unit 2 — 設計文件 D3 說「測試環境沒有 `CLAUDE_CODE_SESSION_ID`，所以每筆都是空 dict 加原因，
  沒有測試需要造 transcript 就能通過」。**這個前提是錯的**：Claude Code 的 Bash 工具環境有設這個
  變數，所以既有測試會真的去掃開發者本機的 transcript。
  Why: 後果不只是慢——本機與 CI 走的是**不同的程式碼分支**，本機綠不代表 CI 綠；而且耗時隨
  transcript 成長（實測全套 10.42s vs 6.51s，慢 60%），unit 3 的 R5 測試要 spawn 8 個程序各寫
  50 筆，會變成 400 次真實檔案掃描。
  修法：`tests/conftest.py` 加一個 autouse fixture 移除該環境變數，讓整套測試封閉。要測 collect
  分支的測試自己 monkeypatch（unit 2 的新測試本來就是這樣做的）。
  Cost: 全套從 10.42s 降到 5.65s，本機與 CI 一致（5.65 vs 5.49）。`tests/conftest.py` 因此進入
  unit 2 的變更範圍——它原本不在任何 unit 的歸屬圖裡。

- Verify — 設計文件 D4 與 `## Glossary` 的 `window` 定義寫「下界是同一 session **同一 track** 上一筆
  record 的 `window_end`」。**實作已改為「同一 session 跨所有 track」**。
  Why: 依原定義，同一個 session 開第二條 track 時，那條 track 的帳本沒有這個 session 的記錄，
  於是回退到導入日地板，把第一條 track 已經算過的區間整段重算。實測 trackA 第二次的窗是
  `10:25:41.067→068`、trackB 的窗是 `00:00:00.000→10:25:41.078`。報表端沒有二次去重，
  所以膨脹永久寫進帳本、事後無法還原。「同一對話裡先做 feature A 再做 feature B」是正常用法。
  修法：`_window_since(session_id)` 改掃集中帳本取該 session 最晚的 `window_end`，與導入日地板
  取較晚者。實測掃 4.1MB（14,782 行）集中帳本耗 55ms，500ms 警戒線內約 9 倍餘裕。
  Cost: 設計文件的 D4 與 Glossary 措辭與程式碼不再一致。**未改設計文件**——它已簽核，改它會讓
  `preflight` 的 `artifact_unchanged` sha256 比對失敗而擋下整個 stage。

- Verify — UC6 的判準在 build 中途被主 session 從「報表任何出現金額的地方都帶標示」窄化為
  「表頭一次」，並把測試鎖成 `len(caveat_lines) == 1`，**未走 Deviation 格式、未交使用者裁決**。
  由 conformance lens 抓出。使用者 2026-08-30 補裁決為折衷：欄位名改為 `spend_equiv=`，
  每列都帶記號但不重複整句，表頭保留完整解釋。
  Why: 逐列重複整句話會把數字擠到看不見（原始判斷成立），但修改已簽核的驗收判準應由使用者決定。

- Verify — `tests/conftest.py` 的 `_isolated_central_ledger` fixture（unit 3 加的）先前只記在
  commit message，沒有進本檔的 Deviations。由 conformance lens 指出，補記於此：它把
  `CAI_USAGE_LEDGER` 導向 tmp，擋住測試寫進使用者真實的 `~/.claude/cai/usage.jsonl`。

## 主 session 自己犯的一個操作錯誤（記錄以免重演）

驗證「新測試是否擋得住」時做突變測試：改壞程式 → 跑測試 → `git checkout -- <file>` 還原。
但當時**修正尚未 commit**，所以 `git checkout` 不是撤銷突變，是把檔案重設到 HEAD，
連同修正一起抹掉（`ledger.py` 的 Blocker 與 Major-2、`usage_collector.py` 的 Major-1）。
測試檔沒被 checkout 所以倖存，結果是「新測試存在但被修的程式不見了」，4 條紅。
正確順序是**先 commit 修正，再做突變測試**。已於 `4856cbd` commit 後重跑三個突變，全部由
專屬測試擋下。

- Build — `stage-build.md` Step 1 說進度欄加進設計文件的 `## Work breakdown`，改為寫在本檔。
  Why: `preflight.py` 的 `artifact_unchanged` 以 sha256 比對簽核版設計文件，改動它會讓
  下一次 build 的 preflight 判定設計被竄改而擋下整個 stage。
  Cost: 讀者要看兩個檔才看得到完整排程；本檔開頭已指回設計文件。
