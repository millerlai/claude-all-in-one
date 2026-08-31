# ticket-integration — implementation notes

- 開始：2026-08-31
- 分支：`feat/ticket-integration`
- 設計文件：`docs/design/2026-08-31-ticket-integration-detail.md`（HLD：`docs/design/2026-08-30-ticket-integration-high-level.md`，`Status: approved 2026-08-31`）

## 為什麼進度表在這裡而不在設計文件裡

`stage-build.md` Step 1 說進度欄應該加進設計文件自己的 `## Work breakdown`，讓設計與進度同檔。這裡沒有這麼做，因為 `preflight.py` 的 `artifact_unchanged` 正以 sha256 盯著那份 detail design（`state.md` 的 design 列指向它）——加欄會讓下一次 build preflight FAIL，而那個 probe 的用意正是「證明 build 讀的是人簽核過的那份」。同一個 repo 的 `gap02-usage-ledger` track 遇過同一件事，解法也是寫進 implementation-notes。

## 這一輪的三個決定（使用者 2026-08-31）

1. **每個 unit 一個 commit**。六個 commit，ship 階段會 squash 成一個。
2. **順序執行，不開 worktree 平行 lane**。
3. **unit 1 的 e2e 另建一個拋棄式 issue**（#47 已關閉，保留其驗證紀錄）。

## 進度表

`Verify with` 是現在就定死的 scoped 命令，不是事後才決定的。

| # | Unit | Depends on | Alongside（設計所載） | Verify with | Status | Commit |
|---|---|---|---|---|---|---|
| 1 | `ticket_backend.py`：`Backend`、`classify`、`run`（timeout 10s）、`GitHubBackend` | nothing | 2（實際上不可，見下） | `python -m pytest tests/test_ticket_backend.py` | **done** | `18c9bd3` |
| 2 | `ticket.py` 本機半邊：`read_config`、`read_pointer`/`write_pointer`、`render_comment`、`marker_for`、`StubBackend` | nothing | 1（實際上不可，見下） | `python -m pytest tests/test_ticket_config.py tests/test_ticket_render.py` | **done** | `1eeba93` |
| 3 | `ticket.py project` 接線、失敗訊息、pointer 狀態寫入 | 1, 2 | 4（實際上不可，見下） | `python -m pytest tests/test_ticket_project.py` | **done** | `6543a19` ＋ e2e 修正 `5c0d4ec` |
| 4 | `ticket.py read`、`ticket-mirror.md`、`SKILL.md` 的一行 | 2 | 3（實際上不可，見下） | `python -m pytest` ＋ `python scripts/validate.py` | **done** | `cfca96f` |
| 5 | `ticket.py transition`、`--confirmed-by-user`、ship 引用、`stage-ship.md` 一行 | 1, 4 | nothing | `python -m pytest` ＋ `python scripts/validate.py` | **done** | `0fbb989` |
| 6 | 收尾：`.claude/cai.json` 範例與說明、測試補齊 | 1–5 | nothing | `python -m pytest` ＋ `python scripts/validate.py` | **done** | `45c0a87` |

## Ownership map（哪個 unit 動哪些路徑）

由 detail design 的 `## Implementation spec` 各節 `Where it lives` 推出來的；設計文件本身沒有這張表。

| Unit | 擁有的路徑 |
|---|---|
| 1 | `plugins/cai/scripts/ticket_backend.py`（`CATEGORIES`、`TIMEOUT_SECONDS`、`Backend`、`classify`、`run`、`GitHubBackend`、`BACKENDS`、`get`）、`tests/test_ticket_backend.py` |
| 2 | `plugins/cai/scripts/ticket.py`（`read_config`、`read_pointer`、`write_pointer`、`marker_for`、`render_comment`）、`plugins/cai/scripts/ticket_backend.py` 的 `StubBackend` 一節、`tests/test_ticket_config.py`、`tests/test_ticket_render.py`、`tests/fake_gh.py` |
| 3 | `plugins/cai/scripts/ticket.py` 的 `project` 子指令與失敗訊息、`tests/test_ticket_project.py` |
| 4 | `plugins/cai/scripts/ticket.py` 的 `read` 子指令、`plugins/cai/skills/track/references/ticket-mirror.md`（新檔）、`plugins/cai/skills/track/SKILL.md`（恰一行） |
| 5 | `plugins/cai/scripts/ticket.py` 的 `transition` 子指令與 `--confirmed-by-user`、`plugins/cai/skills/track/references/stage-ship.md`（一行） |
| 6 | `.claude/cai.json` 的範例與說明、測試補齊 |

**零行改動的既有檔案**（任何 unit 都不得動，DD2 與 AC23 靠它們成立）：
`plugins/cai/scripts/preflight.py`、`plugins/cai/scripts/ledger.py`、`plugins/cai/skills/track/stages.json`、`plugins/cai/agents/*.md`。

## 建表時發現：`Alongside` 欄與檔案擁有權衝突

設計的 `## Work breakdown` 標 unit 1 與 2 可並行、3 與 4 可並行。做 ownership map 時發現兩對都不成立：

- **1 與 2**：unit 2 的 `StubBackend` 住在 `ticket_backend.py`，那是 unit 1 的檔案。
- **3 與 4**：兩者都在 `ticket.py` 加子指令。

`stage-build.md` Step 1 說「一個路徑落在兩個 unit 底下不是對映問題，而是這兩個 unit 不能並行」。使用者已選順序執行，所以這次不造成任何影響；記錄下來是因為若未來有人照設計的 `Alongside` 欄開平行 lane，會在同一個檔案上撞車。**設計文件未改**（它已簽核且被 sha256 盯著），此表的「實際上不可」註記是唯一的更正。

## 追溯表（`stage-build.md` Step 6.1）

每一列指得出實際落點才算實作了。`R1`–`R3` 與 `UC1`–`UC8` 的編號沿用 HLD 的
`## Use cases / Issues`。

| Id | 需求 | 實際落點 |
|---|---|---|
| R1 | 需求要有書面來源 | `plugins/cai/scripts/ticket.py:285`（`read`）＋ `plugins/cai/skills/track/references/ticket-mirror.md:15`（Before dispatch: read once） |
| R2 | 團隊看得到進度 | `plugins/cai/scripts/ticket.py:182`（`project`）＋ `:126`（`render_comment`）＋ `ticket-mirror.md:35`（After every state.md write） |
| R3 | 交付物指得回需求 | `ticket-mirror.md:45`（ship: resolve before quoting）＋ `plugins/cai/skills/track/references/stage-ship.md:8` |
| UC1 | 未啟用時逐字相同 | `ticket.py:44`（`read_config`，檔不存在即靜默返回）；斷言在 `tests/test_ticket_config.py`、`tests/test_ticket_read.py` |
| UC2 | ticket 內文成為書面需求 | `ticket.py:285`＋`ticket-mirror.md:15`（含 intake 被 skip 時由 verify 補讀） |
| UC3 | 同一則留言就地覆寫 | `ticket_backend.py:196` 的 `GitHubBackend.upsert_comment`（marker＋作者兩條件 find-back）＋ `ticket.py:112`（`marker_for`） |
| UC4 | ship 確認後才轉換一次 | `ticket.py:323`（`transition`，缺旗標即拒絕）＋ `stage-ship.md:8`＋`ticket-mirror.md:45` |
| UC5 | 不可達不擋人、不吃重試額度 | `ticket_backend.py:105`（`run`，例外全轉分類詞）＋ `ticket.py:392`（`main` 一律 exit 0）；斷言在 `tests/test_ticket_project.py` |
| UC6 | 不持憑證、輸出不落地 | `ticket_backend.py:46`（`classify`，封閉集合）＋ `:88`（`_argv_summary`）；斷言在 `tests/test_ticket_close_out.py` |
| UC7 | 手動補寫入口 | `ticket.py:175`（`_resend_hint`）＋ `:182` 失敗路徑印出可貼上的指令 |
| UC8 | 設定 per-project、換 backend 零改動 | `.claude/cai.json`＋`ticket.py:44`＋`ticket_backend.py:306`（`StubBackend`）、`:331`（`get`）；零改動斷言在 `tests/test_zero_change_promises.py` |

`SKILL.md:87` 是把以上接進 track 流程的那一行；它明寫由主 session 而非 subagent 執行。

## e2e 抓到、單元測試抓不到的兩個 bug（2026-08-31，commit `5c0d4ec`）

這兩個都是在 **186 個單元測試全綠**的狀態下存在的，值得單獨記一節，因為它們說明了這個
功能的哪一類風險靠 stub 測不出來。

1. **編碼。** `run()` 抄了 `preflight.py:212-220` 的 `subprocess.run(text=True)` 形狀，
   那會用主控台 locale 解碼。對 `git` 沒問題（輸出基本上是 ASCII），對 `gh` 必然出事——它
   回吐的是留言 body、issue title 與本專案自己的中文 `state.md` note。**第一次投影成功、
   第二次死在讀回自己剛寫的中文留言上**（cp950 `UnicodeDecodeError`）。而且它是在 subprocess
   自己的 reader thread 裡拋的，`run()` 的 `except` 根本看不到，只留下 `stdout is None`，
   於是三個 frame 之後才由 `json.loads(None)` 現形，行程 exit 1、失敗也沒記進 pointer——
   同時違反「不 raise」與「失敗記在 `ticket.json`」兩條。修法：明確 `encoding="utf-8"`，
   並讓每個 JSON 解析都走守衛、回分類詞而非拋例外。
2. **可觀測性。** 設計要的是 `backend <argv 摘要> -> <分類詞>`，而「摘要」是承重的：
   `-f body=...` 帶的是整張六列表，逐字印 argv 等於每次投影都把整則鏡像留言洗在畫面上。

**第二個修正第一次還修錯了，這點更值得記**：`run()` 有兩處 print，只改到其中一處；而為它
寫的測試驗的是摘要 helper 而不是 `run()`，於是測試全綠、真實輸出卻沒變。補的測試改為直接
驅動 `run()` 並斷言它印出來的那一行，突變驗證確認任一處 print 改回舊寫法都會讓它紅。
**教訓：測 helper 不等於測整合。**

## 主 session 測錯了一個數字，整份設計都建立在它上面（2026-08-31，commit `cfca96f`）

**`SKILL.md` 的 body 一直是 120 行，不是 119。** 主 session 用 `wc -l` 減 frontmatter 行數
得到 119；`validate.py:1344-1345` 用 `find("\n---", 3)` 定位 frontmatter 結尾再
`splitlines()`，得到 120。**同一個數字、兩套公式，無聲地不一致。**

這個 119 被寫進了 HLD 的 C19、Decision 1 的三個選項與裁決依據、detail 的 `## Budgets`
與 AC24。**使用者是看著「還剩 1 行」才選了「用掉最後 1 行指向 reference」**，而那條路在
算術上不可能（120 + 1 = 121 > 120）。

unit 4 的 implementer 沒有採信 brief 裡的數字：它 `git stash` 後實跑 `validate.py`，加上
那行看它 `FAIL (121)`，再還原確認。錯誤因此在 build 階段浮出，而不是在 ship 時整條路走不通。

**處置（使用者 2026-08-31 裁決）**：`scripts/validate.py` 的上限從 120 調到 122，改為具名
常數 `TRACK_SKILL_MAX`。理由寫在該處註解：一個檔案剛好卡在上限的「上限」已經不再測量任何
東西——下一行不論值不值得加都會失敗。刻意加 2 而非 1，讓它重新是預算而不是絆線。

**已加防再犯的測試**：`tests/test_track_skill_ticket_pointer.py` 的
`test_validate_reports_the_same_body_line_count_as_computed_here` 交叉比對兩套算法，任何
一邊漂移都會紅。其餘斷言一律讀 `validate.py` 自己的 stdout 或 `git diff`／`git show`
輸出，**不把任何數字複製一份到測試裡**——那次複製正是這個錯誤的來源。

**未改的文件**：HLD 與 detail 都已簽核且被 `artifact_unchanged` 以 sha256 盯著，因此
C19、Decision 1、`## Budgets`、AC24 裡的 119 與「剩 1 行」維持原文，以本節為準。

## Deviations

實作發現設計錯了就記在這裡，格式依 `stage-build.md` Step 5。

- **Unit 1 — 設計對「403 但身分未變」沒有給答案，第一版實作因此回錯分類。**
  設計在 `### classify` 的判定順序裡沒有任何 403 規則，卻在同一節的散文寫「該分類詞保留給
  PATCH／close 失敗，判定依據是 `403` 或 `forbidden` 出現在寫入呼叫的 stderr」。implementer
  保守地只在「403 且目前身分與快取 `login` 不同」時回 `forbidden`，身分相同時落回
  `classify()` 的結果，也就是 `unclassified`。
  Why: 兩段文字有張力，而 DD10 通篇談的是換帳號，讀起來像是 `forbidden` 專屬於那個情境。
  實際上 DD10 的二次確認只決定印哪一則訊息，不決定分類——被移除協作者、或 token scope 改
  變，同樣是 403，使用者卻會看到「無法分類」而找錯方向。
  改法: 403 一律回 `forbidden`；身分比對只選訊息（換帳號 vs 同一帳號權限不足）。
  Cost: none。介面與回傳型別未變，unit 2–6 不受影響。

- **Unit 1 — `tests/fake_gh.py` 未建立，改用 inline fake。**
  設計的 `## Naming` 列了它，但 ownership map 把它分給 unit 2。implementer 因此把每個假
  `gh` 腳本寫在 `tests/test_ticket_backend.py` 內、每個測試各自寫進 `tmp_path`。
  Why: 遵守 ownership 邊界，不是設計錯誤。
  Cost: unit 2 建 `tests/fake_gh.py` 時，可考慮把 unit 1 的 inline fake 收斂過去；不做也
  不會壞任何東西。

- **Unit 2 — 主 session 的 brief 造成一個結構性衝突，由主 session 自己修。**
  brief 把 `tests/test_ticket_backend.py` 列進「不可動」清單，但 unit 1 在該檔留了
  `test_stub_backend_is_registered_and_left_for_unit_2`，斷言 `StubBackend.whoami()` 會
  raise `NotImplementedError`——那正是 unit 2 要取代的行為。implementer 標記而未偷改，是
  對的處置；主 session 改寫該測試，改為斷言 AC23 真正依賴的事：第二個 backend 能回答同樣
  四個方法且完全不呼叫外部行程。
  Why: 寫 brief 時沒有察覺 unit 1 的佔位測試會與 unit 2 的實作直接對撞。
  Cost: none。

- **Unit 2 — implementer 未逐測試跑 red-green，主 session 以突變測試補驗。**
  它自陳實作與測試一起寫，只對截斷那一個測試做過突變檢查。主 session 在 commit `1eeba93`
  之後（先 commit 才動手，才有安全的還原點）跑了四個突變，全部被既有測試抓到：marker 去掉
  中括號（3 failed）、截斷停用（1 failed）、`artifact` 欄洩漏進表（1 failed，AC11 的核心）、
  `problem` 回傳含檔案內容（2 failed）。還原後 `git status` 乾淨、167 測試全綠。
  Why: implementer 判斷「同一次讀規格後一起寫」較有效率，但那正是無法證明測試非空的做法。
  Cost: none，但這個補驗是必要的——沒有它，那四條斷言的有效性只是宣稱。

- **Unit 2 — 鏡像留言第二行採用設計原文的中文字串。**
  設計以「」引號寫「此留言由 cai 就地覆寫，請勿手動編輯」，implementer 讀成字面內容而非
  設計註解，照用。這與本 repo 的 `state.md` note 同樣是中文，前後一致。
  Why: 設計文件沒有明說該行是內容還是敘述。
  Cost: 若團隊的 ticket 以英文為主，這一行需要改；改動範圍是 `ticket.py` 的一個字串常數與
  一條測試斷言。**留給使用者裁決，未自行決定。**
