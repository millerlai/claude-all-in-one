# intake — track-context-budget

- Track: `track-context-budget`
- Branch: `fix/track-context-budget`
- Date: 2026-09-07
- Stage: `intake` (architect, 2 rounds)
- Status: handed back, not implemented (`stage-intake.md:49-55`)

---

## 1. 問題陳述

`/cai:track` 的六個 stage 全在同一個 main session 內跑完。三條完成軌道的
`ledger.jsonl` 各只有一個 `session_id`（`pr60-followups` 全 7 列
`2162ccb5…`、`ticket-integration` 全 9 列 `962f8ff6…`、
`track-status-vocabulary` 全 6 列 `a990d2d9…`）。主 session 的 context
單調累積，沒有任何 stage 邊界會回收。

**峰值第一次被量到。** 從 orchestrator transcript 逐則 `message.usage`
分段 grep `cache_read_input_tokens`（該檔 `isSidechain:true` 零命中，
subagent 另存 `subagents/` 子目錄，故全屬主 session）：

| track | 主 session cache_read 峰值 | 對 1M 的佔比 |
|---|---|---|
| pr60-followups | 507,696 起跳，6xx 以上零命中 → < 600K | < 60% |
| ticket-integration | 681,493 且仍在爬，7 位數零命中 → 681K–700K | 68–70% |

`ticket-integration` 那條曲線單調上升、全程沒有一次驟降，證明整段執行沒有
跑過 `/compact`，也沒有任何機制修剪過視窗。加計單次 `cache_creation`
（>=100K 者去重後約 3 次請求）真實峰值約 **0.70–0.75M**，即 1M 的七成，
餘裕約三成。

**方法學保留（不可省）**：這是分段 grep 的區間估計，不是精算——intake 階段
只有 `Read/Grep/Glob`，無法逐筆相加 `input + cache_read + cache_creation`；
`track-status-vocabulary` 未測。ledger 結構上答不出峰值：
`usage_collector.py:264-269` 逐 model 累加五個 token 欄位、不保留 max。

問題的形狀因此不是「即將爆掉」，而是「最壞一條用掉七成、剩三成餘裕，
而且沒有任何東西會回收」。

### 同根因、且與 context 預算無關也成立的結構缺陷三項

1. **`note` cell 有兩個宣告的擁有者。** 六份 reference 的 Closing 一致要求
   stage 自己寫（`stage-intake.md:59`、`stage-discover.md:146`、
   `stage-design.md:249`、`stage-build.md:263`、`stage-verify.md:106`、
   `stage-ship.md:152`），而 `SKILL.md:80-82` 把同一格指派給主 session。
2. **六個 agent 有四個做不到那個動作。** `architect.md:7` =
   `Read, Grep, Glob`（跑 intake 與 discover）、`verifier.md:7`、
   `shipper.md:7` 皆無 `Write`；只有 `designer.md:8` 與 `implementer.md:6`
   有。實害已記錄在 `.claude/track/done/pr60-followups/state.md:12`
   （verify 寫序顛倒須由主 session 重寫）與 `:8`（intake 未派 explorer）。
   本次 intake 原樣重演。
3. **例外條款的描述比實際窄。** `SKILL.md:68` 只說 Step 5.5 寫 `status`，
   但 `stage-build.md:236-237` 實際還寫 `note` = `unit <N> of <total>`、
   `:226` 還 append `## Handoff`。（round 2 新發現，主 session 已獨立複驗。）

### 本該擋下這些的檢查有洞

`validate.py:1271-1274` 的註解明說 `STAGE_TOOL_NEEDS` 存在的理由就是
「stage 的 reference 要求了它的 agent 沒有的工具」，套用在 `:1409-1424`。
但 `:1275-1304` 的表缺 `intake` 與 `discover` 兩個 key，`Write` 只對
`design` 檢查。今天全綠的未受檢要求：intake 的 `Agent`
（`stage-intake.md:14`）+ `Write`、discover 的 `Agent`
（`stage-discover.md:44`）+ `Write`、verify 的 `Write`、ship 的 `Write`。

### 兩者的連結

只要 `note` 由主 session 擁有，每一格 note 都必須穿過主 session 的視窗
兩次（從 subagent report 讀進來一次、寫出去一次）。而 stage report 今天
**沒有任何格式或大小契約**——`^## Report` 在 `references/` 與 `SKILL.md`
全樹零命中（主 session 複驗）。對照之下 ledger 的 note 早有程式層上限：
`ledger.py:58 MAX_NOTE = 3840`，`:54-56` 記著那是使用者 2026-08-29 的裁決。

### 對原始問題的結構性答案

使用者問「每個 stage 能否自動只保留下一個 stage 需要的東西」。答案是
**不能自動**。`stage-build.md:219-221` 已把理由寫死——`SessionStart`、
`SessionEnd`、`UserPromptSubmit`、`Stop`、`StopFailure`、`PreToolUse`、
`PostToolUse` 沒有一個會在預算用盡前示警。沒有事件可掛，所以「保留」
只能是**交接點上的程序**，不能是預算逼近時的反應。

本軌道因此**不承諾視窗變小**，只承諾三件事：修掉所有權矛盾、給 report
一個上限、讓「還剩多少餘裕」變成零 token 可重複的數字。

---

## 2. 驗收條件

每條後附「後續 stage 怎麼機械檢查」。

**AC1 — `note` 擁有權單一化，六份一致。**
六份 reference 的 Closing 不再出現「write into `state.md`'s `note` cell」，
一律改為「在 `## Report` 交出這些欄位」；欄位內容即各自今天 Closing 要求的
東西（`stage-intake.md:59-63`、`stage-discover.md:146-147`、
`stage-design.md:249-251`、`stage-build.md:263-265`、
`stage-verify.md:106-108`、`stage-ship.md:152-154`），一項不減。
*檢法*：`state.md` 在 `references/` 的命中只剩 `stage-build.md:96`（散文
提及）、`:226`、`:236`（Step 5.5）三處；六個 Closing 段內零命中。

**AC2 — Step 5.5 的例外，兩份文件描述一致。**
`SKILL.md:68` 的例外句加寬到涵蓋 `stage-build.md:236-239` 實際指示的三件
事：`status` = `in-progress`、`note` = `unit <N> of <total>`、append
`## Handoff`。`stage-build.md:217-243` 本身一個字不動。
*檢法*：`SKILL.md:68` 必須同時出現 `status` 與 `note` 兩字，且
`stage-build.md:236-238` 的 diff 為空。

**AC3 — 六份 reference 各含一個 `## Report` 契約。**
每份一個 `## Report` 段，明列欄位與**一個大小上限數字**，格式沿用
`ledger.py:54-58` 已建立的形式（一個數字、一句為什麼、裁決日期）。證據去
該 stage 本來就會產出的 artifact，不進 report。
*檢法*：六個檔各數 `^## Report` 出現次數 == 1；段內配到一個 `\d{3,}` 的
數字與一個 `\d{4}-\d{2}-\d{2}` 的日期。
*註*：**數字本身由 design 提、使用者簽**——`SKILL.md:93-94` 的 design
人工閘門正是簽它的地方。intake 不代定。

**AC4 — `STAGE_TOOL_NEEDS` 對 `stages.json` 六個 stage id 全部有 entry。**
且每個 entry 涵蓋該 stage reference 中所有祈使句要求的工具。依 Q2 的裁決，
**沒有任何 stage 的 agent 因為 `state.md` 而需要 `Write`**；`Write` 只剩
兩個獨立理由：design 寫設計文件（`validate.py:1277` 已有）、build 寫程式碼
與 Step 5.5。`Agent` 的六處根據：`stage-intake.md:14`、
`stage-discover.md:44`、`stage-design.md:50`、`stage-build.md:82,148`、
`stage-verify.md:38`。
*檢法*：`set(STAGE_TOOL_NEEDS) == set(STAGE_ORDER)`（`validate.py:1309`
已有 `STAGE_ORDER`）可寫成一條 check；再跑 `python scripts/validate.py`
exit 0。

**AC5 — 突變式：證明 AC4 的檢查真的在守。**
暫時把任一處已修好的矛盾改回去（例：把 `Write` 要求塞回某份 architect 跑的
reference），`validate.py` 必須 FAIL 並在訊息中點名該 stage 與該工具；
還原後 exit 0。
*檢法*：改壞 → 跑 → 讀輸出 → 還原 → 再跑。**突變前先 commit**——
`git checkout` 還原的是「到 HEAD」，不是「撤銷剛才那筆」。

**AC6 — 一支峰值量測 script。**
給一個 track dir 或 session id，印出該 orchestrator session 逐次請求的
`input_tokens + cache_read_input_tokens + cache_creation` 峰值與出現位置。
**重用** `usage_collector.py` 既有的 transcript 讀取與 requestId 去重
（`usage_collector.py:9-13` 記著不去重會灌水 5 倍；`:249-256` 是讀
`message.usage` 的地方），不得寫第二套 parser。
*檢法*：對三條已完成軌道各跑一次都印得出數字；且 ticket-integration 的
峰值落在本階段估的 0.68–0.75M 區間內。落在區間外代表估計或 script 有一個
是錯的，要查明再收。

**AC7 — `python scripts/validate.py` exit 0；`python -m pytest` 全綠；
不新增執行期相依。**
*檢法*：跑兩個指令讀真實輸出（`CLAUDE.md` 的 Before pushing 已規定）；
新增檔案的 import 只用標準庫。

**AC8 — `.claude/track/done/**` 一個位元組都不動。**
那是本軌道唯一的量測母體。
*檢法*：`git diff --stat -- .claude/track/done/` 為空。

---

## 3. 已定的做法（E + C + 峰值量測）

| 動什麼 | 具體檔案 |
|---|---|
| 六份 Closing 改成 `## Report` 交欄位 | `stage-intake.md:57-63`、`stage-discover.md:144-147`、`stage-design.md:247-251`、`stage-build.md:261-265`、`stage-verify.md:104-108`、`stage-ship.md:150-154` |
| 六份各加 `## Report` 段（欄位 + 一個上限數字 + 理由 + 日期） | 同上六檔 |
| 例外條款描述加寬 | `SKILL.md:68` 一句；`stage-build.md:217-243` **不動** |
| 補齊工具檢查 | `scripts/validate.py:1275-1304` 的 `STAGE_TOOL_NEEDS`，加 `intake`/`discover` 兩個 key 與各 stage 缺的項；套用點 `:1409-1424` 不必改 |
| 新增 `## Report` / 擁有權的形狀檢查 | `scripts/validate.py`（AC1、AC3、AC4 各一條 check） |
| 新增峰值量測 script | `plugins/cai/scripts/` 下一支新檔，重用 `usage_collector.py` |
| 可能改 agent 授權 | `plugins/cai/agents/architect.md:7`（僅在下述子決策選 (i) 時） |

### 留給 design 的兩個未定數

1. **AC3 的上限數字**——由 design 提，走 `SKILL.md:93-94` 的人工閘門簽核。
2. **AC4 的子決策**：加了 intake/discover 的 `Agent` 檢查後今天會紅
   （`architect.md:7` 無 `Agent`）。兩條路——
   (i) 授予 `architect` `Agent`：它仍是唯讀角色，`explorer` 也唯讀，
   `architect.md:12` 的 "Read-only" 不因此失效，但會改變 architect 在
   track 之外所有用途的授權面；
   (ii) 把 dispatch 指示移出兩份 reference，改由主 session 在派 architect
   前先派 explorer：會把探索成本原封不動搬回主 session 視窗，與本軌道目的
   反向。
   intake 傾向 (i)。design 決定並記錄理由。

---

## 4. 明確排除，後續 stage 不得悄悄加回

- **A（一個 stage 一個 session）**——實測餘裕仍有三成；且它會第一次真的
  行使從未被行使過的跨 session resume 承諾（`SKILL.md:3`、
  `stage-intake.md:61-63`），三條完成軌道沒有一條跑過。
- **D（主 session 降為純排程器）**——它會刪掉
  `pr60-followups/state.md:13` 記錄的唯一防線：主 session 拿 diff 重推、
  抓出 ship 報告六處與 diff 不符的宣稱（行號錯、檔名錯、方向錯、手法錯、
  引用了已被 squash 掉的 SHA），全是散文對 diff 的錯配，沒有 digest 抓得到。
  `stage-ship.md:42-45` 明說那個成本是刻意付的。
- **B（縮短 `state.md` 的 note）維持現狀，不列為變更項**——六列 note 約
  15 KB 約 4K token，佔實測峰值不到 1%。拿 context 當理由去砍它，是替
  使用者做一個他沒要求的需求決策。

### 會讓「排除 A」作廢的條件

AC6 的 script 量到峰值 > 0.85M，或量到主 session 佔用的六成以上來自
subagent report 回填。前者代表餘裕不夠，A 的硬保證變成唯一選項；後者代表
AC3 要從「加一節」升級成「硬性截斷 + 拒收超長 report」。

---

## 5. 使用者裁決（2026-09-07）

- **Q1 範圍** = E + C + 峰值量測。A 與 D 出局，B 維持現狀不列為變更項。
- **Q2 `note` 擁有者** = 主 session 全權，六份 reference 一律改成「在
  `## Report` 交出這些欄位」。`stage-build.md` Step 5.5 的 `## Handoff` 與
  `status` 寫入維持不變。

依 round 2 新發現的第三處不一致，擁有權規則須寫成：**passed 後的終局
note 歸主 session，in-flight 的 `unit N of M` 歸 build stage**，並把
`SKILL.md:68` 的例外描述加寬到與 `stage-build.md:236-239` 相符；Step 5.5
本身不動。

---

## 6. 程序偏離

四項，前三項與 `done/pr60-followups` 的 intake 是同樣的偏離、原樣重演，
而它們正是本軌道要修的東西本身：

1. Step 1 未派 `explorer`——`architect.md:7` 無 `Agent`；探索由 architect
   自行完成，全程附 `file:line`。
2. Step 2 訪談未由本階段進行——平台移除 subagent 的 `AskUserQuestion`；
   兩題經 `pending-questions.md` 上交主 session，2026-09-07 裁決後於
   round 2 重派。
3. Closing 的「write into `state.md`'s `note` cell」由主 session 代寫
   ——architect 無 `Write`。
4. round 2 報告本身亦由主 session 落檔（本檔）——同上。

## 7. 未驗證處

- 「Agent tool 一定把 subagent 最終訊息回填進 parent context」是平台行為，
  無法從本 repo 驗證，沿用前提。
- 第 1 節的峰值仍是區間估計，AC6 的 script 跑出來才算數。

## 8. 下一個 stage

**`design`**，不需要 `discover`——解空間已明確（改哪幾個檔、加哪幾條 check
都已點名）。design 要處理的兩個未定數見 §3。
