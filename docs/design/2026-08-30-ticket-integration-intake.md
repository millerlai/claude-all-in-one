# ticket-integration — intake 產物

- 日期：2026-08-30
- track：`.claude/track/ticket-integration/`
- 分支：`feat/ticket-integration`
- 狀態：**待使用者簽核**。簽核前不得進入下一階段。

原始請求（使用者原話）：

> 在 AI SDLC 過程中，一般純軟體開發的團隊都可能會有類似 Ticket 系統例如 jira，如果是個人的軟體開發可能只能利用 github 上提供的 Issues 來做，我想討論的是這種需要是否能夠整合到我們專案的 six stages 中，可以再透過 configure 的方式設定，而不是必要條件，如果有 enable 就要納入這個 six stages 的一部分，如果沒有就走原本流程這樣。可能對於個人 或是 團隊都能適用?

---

## 1. 問題陳述

在 six stages 之外新增一個 per-project、進版控、預設關閉的開關；開啟後，track 以「委派給一支自管登入的外部 CLI」的方式，把一則 ticket 當成需求來源讀進 `intake` 與 `verify`，並在每次 `state.md` 被覆寫後，就地更新 ticket 上的**同一則**留言為六個 stage 的當下狀態表（含 skipped 與理由）；ticket 的狀態轉換由 plugin 主動發起，但每次執行前必須取得使用者確認。關閉時，six stages 的行為與今天逐字相同。

### 「整合」其實是三個成本不同的需求

| # | 需求 | 今天缺什麼 | 由哪個決策承接 |
|---|---|---|---|
| R1 | 需求要有書面來源 | `stage-verify.md:44,47-50` 的 conformance lens 明文要拿 the plan, spec, issue 比對；沒有書面需求時**直接放棄這個 lens** | 決策 1（讀） |
| R2 | 團隊看得到進度 | `state.md` 與 `ledger.jsonl` 都在 `.gitignore:11`，是本機私有檔，團隊裡沒有第二個人看得到 | 決策 1+3（回寫） |
| R3 | 交付物指得回需求 | ship 的 commit / PR 不帶 ticket 編號 | 決策 1+4 |

一個反直覺的事實：在團隊情境下，**ticket 是唯一共享的紀錄，`state.md` 才是私有的**。這反轉了同步的動機——不是讓 ticket 反映 `state.md`，而是讓 `state.md` 有個對外的投影。

---

## 2. 已拍板的決策（2026-08-30 訪談）

| # | 決策 | 使用者的選擇 |
|---|---|---|
| D1 | **方向：讀 + 回寫** | 明知代價（1-2 週、可逆性低、ledger append-only）仍選擇。R1+R2+R3 全要 |
| D2 | **backend：能力層抽象，第一版只實作 GitHub Issues** | 附加約束（原話）：「驗證方式都盡可能採用 SSO 的方式為主，其餘方式為輔，盡可能不要自己存 Token 之類的方式」 |
| D3 | **回寫形式：單一留言就地更新** | 固定編輯同一則留言，內容為六個 stage 當下狀態表，含 skipped 及理由 |
| D4 | **狀態轉換：plugin 主動轉，但每次執行前詢問使用者** | 原話：「我要採用 plugin 主動轉狀態, 但是要詢問 User 才做」 |
| D5 | **設定作用域：per-project 並進版控** | 採預設。憑證在 D2 之下本來就不由 plugin 管 |
| D6 | **維持六個 stage** | 採預設。加第七列會讓 `done/` 底下既有 track 的 `status` exit 2（`track_state.py:121-126`） |
| D7 | **不自動對帳** | 採預設。不一致只顯示，不自動改任何一邊 |

### D2 的關鍵推論：抽象在「能力層」而非「呼叫層」

介面不該抽象成 HTTP client，而該抽象成「**委派給一支自己管登入的外部 CLI**」。成立的理由：

1. zero-deps 保住，且有既有作法背書——`preflight.py:212-220` 呼 git、`preflight.py:123-125` 呼 `design_probe.py`，外部行程不是 Python 套件。
2. 洩漏路徑從根消失：plugin 不持有憑證，`ledger.py:221-234` 就沒有 token 可寫進去。
3. `gh` 已是既有假設而非新增相依：`skills/git/SKILL.md:17`、`agents/shipper.md:7`、`stage-design.md:187` 三處。

介面只該定義三個能力——**讀一則 ticket、覆寫一則留言、轉一次狀態**——不要定義用哪支 CLI、哪些子指令、哪種輸出格式。理由見第 5 節未驗證項 1：若 Jira 沒有滿足 D2 的 CLI，被迫退回 HTTP 時，焊死呼叫形狀的介面會整層重寫。

---

## 3. 可行性結論

### 3.1 D4 與「只有兩個人類 gate」的關係——第一版不衝突

`skills/track/SKILL.md:87-99` 寫著 `Exactly two stages stop for a person, never more`。

**第一版（GitHub Issues）不需要動這段文字一個字。** GitHub Issues 只有 open / closed 兩態，因此 D4 的狀態轉換一條 track 只發生一次，就是 ship 時的 close——正好落在既有第二個 gate 涵蓋的 stage 與性質（對外部系統的不可逆操作）之內。只需在 `stage-ship.md` 的不可逆操作清單把「close ticket」加成第四項。

**衝突只在 Jira 才真的出現**（多態，轉換散落多個 stage）。屆時三條路，破壞性由小到大：

- (i) 限制轉換只在 ship 發生 → 零破壞，但 D4 的價值被閹割（intake 做完 Jira 上仍是 To Do）。
- (ii) 新增第三個 gate → 推翻一條絕對句。破壞是認知上的：一條有條件成立的絕對規則比沒有規則更糟。
- (iii) 把第二個 gate 從「列舉 ship 的三個操作」改寫成「任何對外部系統的不可逆操作，目前是 merging / tagging / publishing / ticket 狀態轉換」→ 對未開啟者外延完全相同，規則數目仍是二；對開啟者功能不被閹割。

**建議 (iii)，但推遲到真的要做 Jira 時再付。** 現在改一條絕對規則卻無人受益是純成本；且 `SKILL.md` body 實測 **119 行、上限 120（`validate.py:1341-1346`），只剩 1 行餘量**，而 (iii) 的措辭比原文長。第一版所有新規則寫進 `references/stage-*.md`（無行數上限）。

(iii) 的代價要誠實記下：它讓 gate 判定從「查表」變成「判斷類別」。緩解方式是保留列舉當**非窮舉清單**並把 ticket 狀態轉換明確加進去——類別負責語意，清單負責判定，判斷不落給模型。

### 3.2 確認點只能落在主 session 的 orchestrator 層

- **`preflight.py` 不可能**：它被 `SKILL.md:48-51` 以 subprocess 呼叫，只印 PASS/FAIL 並 exit 0/2（`preflight.py:10,476-480`），自述為 "Zero-token stage gate"（`preflight.py:2`）。回傳通道只有 exit code 與 stdout，承載不了一次問答。
- **subagent 不該**：`agents/shipper.md:7` 的 tools 無互動工具，但 `agents/shipper.md:20-21` 與 `stage-ship.md:7-9` 都要求確認。唯一解法是那個確認本來就由主 session 執行——`stage-ship.md:31-34` 明文：a subagent's report is a draft。
  - 佐證既有不一致：`agents/designer.md:8` 的 `tools: Read, Write, Grep, Glob` 不含 `AskUserQuestion`，但同檔 description 明文要求 "stops for AskUserQuestion"（實測 grep 確認全 repo 只有此處提及）。即使 subagent 能問，由「草稿層」自行取得的授權，主 session 無法依 `stage-ship.md:31-34` 重新驗證——這正是不可逆外部寫入最不該放的位置。
- `validate.py:1253-1258` 的 `STAGE_TOOL_NEEDS` 只檢查 design→Write、verify→測試指令、ship→git，對互動工具沒有意見，不會替你擋錯層。

**結論：確認位於 `SKILL.md` 的 Running a stage 流程中、主 session 手上——ledger 寫入之後、狀態轉換執行之前。**

### 3.3 回寫的觸發點與冪等鍵

**觸發點：接在既有寫入序列第三位——`ledger.append()` → 覆寫 `state.md` → 更新 ticket 留言。**

- 不能更早：留言內容來源是 `state.md`，必須等它先被覆寫。
- 不能早於 ledger：`ledger.py:230-231` 明說 a refusal here leaves both files untouched; no orphan is possible on this path，而 `_fit` 確實可能拒絕寫入（`ledger.py:236-238`）。在 ledger 成功前對外寫入，就是製造「ticket 有、ledger 沒有」的孤兒。
- **`failed` / `blocked` / `unavailable` 不觸發回寫**：`SKILL.md:68` 明說 Only the passing path touches `state.md`，表的內容沒變。這把外部寫入自動壓到每個 stage 至多一次。
- **例外：`skip` 要觸發**。`SKILL.md:107-113` 的 skip 會覆寫該列（status=skipped、note=理由），正是 D3 要求出現在留言裡的內容。

**冪等鍵：留言 body 內的隱藏標記，不是本機存的 comment id。**

- 不能存本機：`.gitignore:11` 註解明說 `.claude/track/` 是 local working state；存本機則換機器、或 `/cai:track done` 搬進 `done/`（`SKILL.md:120-125`）後就找不回那則留言。
- 標記必須含 feature 名稱：`preflight.py:276-277` 允許同時最多 5 條 active track，兩條指向同一 issue 在程式上可能，標記不含 feature 名會互相覆寫。
- 找回方式：列出留言，取「body 含此標記」**且**「作者是目前登入身分」的那一則；找到就編輯，找不到就新增。第二個條件不能省，否則任何人手動貼一則含標記的留言都會被覆寫。

### 3.4 讀不到 vs 寫不進去：處置不同，但都不擋

**讀不到**：在 `preflight.py` 層照抄既有的「報告但永不擋」形狀——現成先例兩個：`ledger_intact`（`preflight.py:176-186`，註解寫 a corrupt ledger is loud and harmless: every stage says so, none refuses）與 `track_ignored`（`preflight.py:286-307`，Not a gate）。

**絕不能 FAIL**：preflight exit 2 → `SKILL.md:71-73` 記 `blocked` → `ledger.py:50` 的 `COUNTS_AS_RETRY` 含 `blocked` → 五次網路抖動就把該 stage 鎖死（`preflight.py:147-173`）。一個可選的方便功能變成把人鎖在自己 track 外面的原因，是這個設計最容易犯、最難察覺的錯。

**寫不進去：更不能擋**。寫入發生在 `state.md` 已被覆寫之後，此時該 stage 在本機意義上已經成功。若讓寫入失敗記成 `failed`，就造出「`state.md` 說 passed、`ledger.jsonl` 說 failed」的自我矛盾，而 ledger 不可回頭修改（`ledger.py:6`）。

**寫入失敗記在哪**：沿用既有同構前例——集中總帳寫失敗時 per-track 那筆記 `synced: false` 加 `sync_error`，流程照常完成（`ledger.py:265-267`）。ticket 回寫失敗應用**另一組獨立欄位名**（不重用 `synced`），並套用 stderr 過濾與 `_cut` 式截斷（`ledger.py:163-167,274-291`）。

**自癒由 D3 免費取得**：每次回寫都是整張六列表的覆寫而非增量 append，任何一次成功就把先前所有漏掉的更新一併補上。

**尚未關閉的缺口**：若整條 track 每次都寫失敗，就沒有任何一次成功可補齊，需要手動重試入口。**不該掛在 `/cai:track status`**——`track_state.py:6` 明說 It never writes state.md，讓純讀指令產生外部副作用會破壞這個性質。具體形式留給 design。

### 3.5 D2 的三個裂縫（必須做進設計約束）

1. **「委派給 CLI」≠「一定走 SSO」**。`gh auth login` 同時支援瀏覽器 OAuth 與貼上 PAT，抽象層無法強制前者。架構上能保證的是「**plugin 不持有憑證**」，不是「使用者用了 SSO」。兩者必須分開，否則 AC 會寫成不可測的東西。
2. **不持有憑證 ≠ 沒有洩漏面**。外部 CLI 的 stderr 可能含 URL、帳號、org 名稱；原封放進 `--note` 仍會進 append-only 的 `ledger.jsonl` 與跨專案集中總帳（`usage_collector.py:52-56`），而 `_fit` 只截斷不回頭修改（`ledger.py:339-390`）。既有已有同類路徑：`sync_error` 會把 OSError 訊息寫進紀錄（`ledger.py:266-267`）。需要一條「外部 CLI 的 stderr 不得原封進 ledger」的規則。
3. **不要把「怎麼呼叫」抽象進介面**——見第 2 節末。

---

## 4. 驗收標準

### 關閉時（回歸保證）

| # | 標準 | 怎麼測 |
|---|---|---|
| AC1 | 未開啟時 preflight 輸出逐字不變 | 改動前把六個 stage 的 `preflight.py <stage> --track-dir ... --project-dir ...` stdout 存成 golden file；改動後在**無設定檔**環境重跑，六份逐字節相同（含 probe 行數、順序、括號內文字）。`git diff --no-index` 對六份全部無輸出 |
| AC2 | 既有 track 不被破壞 | `.claude/track/done/` 底下兩條既有 track 的 `track_state.py status` 仍 exit 0；`stages.json` 的 `git diff` 為空 |
| AC3 | always-on 預算完全不動 | `scripts/validate.py` 印出的 always-on description budget 仍是 **5451**（實測值，ceiling 5468，`validate.py:215,222-225`）。只剩 17 字元頭寸，任何新增可自動觸發的 description 都會撞破 |
| AC4 | 全綠 | `python scripts/validate.py` exit 0 且 0 FAIL；`python -m pytest` 全綠；`SKILL.md` 仍通過 120 行上限（實測目前 119） |

### 不可達時（不擋人保證）

| # | 標準 | 怎麼測 |
|---|---|---|
| AC5a | 讀不到不吃重試上限 | 把 PATH 上的外部 CLI 換成永遠 exit 1 的 stub，同一 stage 連續走 6 次：`ledger.attempts()` 仍為 **0**，ledger 內無 `blocked`/`failed`，六個 stage 的 preflight 全 exit 0 且各印一行說明原因 |
| AC5b | 寫不進去不吃重試上限，且不製造矛盾 | 讀成功、寫入 stub 永遠失敗，跑完一個 passed 的 stage：`state.md` 該列為 done、ledger 該筆 outcome 為 `passed`（**不得**為 failed/blocked/unavailable）、`attempts()` 仍為 0，且該筆帶有回寫失敗的獨立欄位與原因 |
| AC6 | 自癒可觀測 | 在 AC5b 環境下連跑 intake→discover→design 三個 stage 皆寫入失敗，恢復 stub 為成功後跑 build：ticket 上留言為**一則**，內容含全部四列當下狀態（前三列不得遺漏），且無第二則帶標記留言 |
| AC7 | CLI 缺席等同不可達 | 從 PATH 完全移除該 CLI（command not found）：AC5a 與 AC5b 的斷言全部仍成立 |

### 憑證與洩漏

| # | 標準 | 怎麼測 |
|---|---|---|
| AC8 | plugin 不持有憑證 | 跑完一條完整 track 後，對 `ledger.jsonl`、集中總帳（`usage_collector.central_ledger_path()`）、per-project 設定檔、`state.md` grep：不含 `token`/`password`/`Authorization`/`Bearer`/`api_key`（不分大小寫）。設定檔進版控，同一組 grep 也對 `git show HEAD:<設定檔>` 執行 |
| AC9 | 外部 CLI 的 stderr 不原封落地 | 讓 stub 在 stderr 印出含 `Bearer sk-test-<亂數>` 的假錯誤：該亂數不得出現在 ledger 或集中總帳任何一行。（測的是 3.5-2 的過濾規則，不是 SSO——後者不可斷言，刻意不列） |

### 回寫的正確性

| # | 標準 | 怎麼測 |
|---|---|---|
| AC10 | 恆一則，就地覆寫 | 跑完六個 stage 後，該 issue 上帶標記且作者為登入身分的留言**恰為 1 則** |
| AC11 | 內容等於 state.md | 留言六列與 `state.md` 對應欄位逐列相同。至少一條測試路徑須含 `/cai:track skip <stage> --reason "<why>"`，並斷言該理由出現在留言中 |
| AC12 | 非 passed 不觸發外部寫入 | 讓一個 stage 走 `failed` 與 `blocked` 各一次（`state.md` 依 `SKILL.md:68` 不變）：stub 記錄到的寫入呼叫次數為 **0** |
| AC13 | 標記不依賴本機狀態 | 跑完三個 stage 後刪除整個 `.claude/track/<feature>/` 並重建（模擬換機器），再跑第四個 stage：仍編輯到**原本那一則**，issue 上不出現第二則 |
| AC14 | 不覆寫別人的留言 | 由另一帳號在同一 issue 貼一則含相同標記的留言，再跑一個 stage：該則**未被修改**（比對 id 與 body） |
| AC15 | 兩條 track 指同一 issue 不互相覆寫 | 建立兩條 active track 指向同一 issue，各跑一個 stage：issue 上有 2 則帶標記留言，標記各含自己的 feature 名稱，內容互不污染 |

### 狀態轉換與人類 gate

| # | 標準 | 怎麼測 |
|---|---|---|
| AC16 | 轉換前必問，未答不動 | 在 ship 的確認點回答「否」：stub 記錄到的**狀態轉換**呼叫次數為 0，而留言更新仍照常發生（留言是資訊、轉換才需要授權）；回答「是」後轉換恰發生 1 次 |
| AC17 | 第一版沒有第三個 gate | 跑完一條完整 track，人類停等點恰為 **2 個**：design 之後的簽核、ship 的不可逆操作確認。close ticket 併入後者，`SKILL.md:87-99` 的 `git diff` 為空 |
| AC18 | 確認由主 session 發起 | dispatch 給 shipper 的 prompt 與 shipper 的回報中均**不含**任何已取得使用者授權的宣稱；`agents/shipper.md:7` 的 tools 行未被加入互動工具（`git diff` 該行為空） |

### 讀入路徑的收益

| # | 標準 | 怎麼測 |
|---|---|---|
| AC19 | conformance lens 真的收到需求 | 開啟且可達時，verify 傳給三個 reviewer 的 requirement 內含 ticket 內文（對 dispatch prompt 斷言）。關閉且無書面需求時，仍照 `stage-verify.md:49-50` 明說「沒有書面需求」並只跑另外兩個 lens，**不得**自行編造 |
| AC20 | ship 的引用指得回去 | 開啟時 squash 後的 commit message 與 PR 內文各含一次 ticket 編號，且該編號可經外部 CLI 解析為存在的 ticket（`stage-ship.md:11-29` 的 grounding rule 適用） |

### 設定與相依

| # | 標準 | 怎麼測 |
|---|---|---|
| AC21 | per-project 且進版控 | 設定檔在 `git ls-files` 中出現；A 專案開啟、B 專案關閉時，兩邊 `preflight.py` 行為互不影響（同一台機器、同一 shell 環境） |
| AC22 | zero deps | 新增 script 的 import 僅限標準函式庫；`tests/` 有對應測試，且在**無該 CLI** 的機器上仍可執行（全程 stub） |
| AC23 | 抽象在能力層而非呼叫層 | 介面只暴露三個能力。可斷言形式：新增第二個 backend 的假實作（純本機 stub，不呼叫任何外部程式）時，`preflight.py` 與 track 流程的程式碼**零行改動** |
| AC24 | 新文字不進 SKILL.md | 新增規則文字位於 `references/stage-*.md` 或新設定檔說明，`skills/track/SKILL.md` 行數未增加（實測 119/120，只剩 1 行） |

---

## 5. 未驗證項（design 階段必須關掉）

1. **Atlassian 是否存在一支滿足 D2 的官方 CLI 且支援 SSO 登入。** 未查證。若不存在，第 2 節的抽象邊界就是唯一能防止整層重寫的保險。
2. **回寫在 preflight 之外增加的外部往返對延遲的影響。** 未量測。依 3.3，回寫不在 preflight 裡（它在主 session），所以 preflight 只承擔「讀」。讀的延遲仍需在 design 決定是否快取，或只在 intake 讀一次。
3. **寫入序列與 gate 位置的流程圖**留給 design 階段繪製並驗證渲染（`documentation.md` 要求每張圖交付前確認渲染通過，本次為唯讀分析未繪製）。

## 6. 訪談中被跳過的問題與理由

- **Q「六個 stage 是否變七個」**：未問，採預設維持六個。程式證據已關閉此問題——`track_state.py:121-126` 要求 `state.md` 列數等於 `stages.json` 列數，加第七列會讓 `done/` 底下兩條已歸檔 track 的 `status` 直接 exit 2，需要 migration，而使用者的需求裡沒有要付這個代價。
- **Q「設定作用域」**：未問，採預設 per-project 並進版控。它是唯一能讓「團隊」成立的作用域；憑證在 D2 之下不由 plugin 管，沒有東西需要避開版控。
- **Q「ticket 編號要不要進 commit/PR」**：砍掉。它是 D1 的必然結果，不是獨立決策。

## 7. 給下一階段的建議

**`discover` 可以跳過。** 四個原本會是技術未知的問題（憑證機制、不可達語意、`validate.py` 約束、既有 track 相容性）都已由程式層答案關閉；剩下的第 5 節兩項是 design 階段的查證工作，不是 discover 的探索工作。
