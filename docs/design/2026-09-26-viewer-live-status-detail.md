# viewer-live-status — detail design

## 維護說明（2026-10-27）

本檔是歷史設計紀錄，保留決策、驗收依據與實作偏差；不是待執行計畫。原簽核狀態、版本、行號及未驗證標記描述撰寫當時，整併不代表重新簽核或重做實測。

名詞：設計立場（stance）說明取捨；決策紀錄（decisions）保存選擇理由；細部設計（detail）記錄建造規格；需求盤點（intake）保存驗收條件。下方英文標題與識別碼沿用原文，便於對照歷史。

併入同主題診斷的根因與測試證據。以鎖檔辨識各 Codex 對話、區分背景子代理與本輪工作的取捨仍有價值；現行實作見 [`plugins/cai/scripts/viewer.py:569`](../../plugins/cai/scripts/viewer.py#L569)。鎖檔格式與當時量到的消失延遲是平台內部行為，未在本次重新量測。

已併入並移除的同主題文件：`2026-09-26-viewer-live-status-decisions.md`、`2026-09-26-viewer-live-status-diagnosis.md`、`2026-09-26-viewer-live-status-stance.md`。

補充段落保留原文與原決策編號，避免把不同時點同號的決策當成一項；重複的概覽圖、施工排程與階段交接文字不再複製。

## Reference

Stance doc: docs/design/2026-09-26-viewer-live-status-detail.md
Diagnosis doc: docs/design/2026-09-26-viewer-live-status-detail.md
Decisions doc: docs/design/2026-09-26-viewer-live-status-detail.md
Status: approved 2026-09-26（stance 與 diagnosis；decisions 的 Tier 1 只有 design-footer 一條，已由使用者 2026-09-26 回答）

被修正、不改動的舊設計：docs/design/2026-09-25-agent-viewer-web-portal-detail.md、docs/design/2026-09-25-agent-viewer-web-portal-detail.md、docs/design/2026-09-25-agent-viewer-web-portal-detail.md。本文件取代其中這幾段：decisions 的 D6（`2026-09-25-agent-viewer-web-portal-detail.md:797-797`）與 Tier 3「`idle`、`shell`、過時的 `busy`」一列（`:225`）；detail 的 `### liveness`（`2026-09-25-agent-viewer-web-portal-detail.md:3-509`）、claude_source 的第 3 條規則（`:518`）、codex_source 的 Interface 與存活（`:533`、`:535`）、Budgets 的 50 筆（`:89`）、Failure modes 兩列（`:711-712`）、Verification 兩列（`:747`、`:749`）、Work breakdown 的 unit 3（`:769`）。舊檔照 diagnosis 的決定不改（`docs/design/2026-09-26-viewer-live-status-detail.md:564`）。

程式行號都是 main d514f6b 的檔案；`plugins/cai/scripts/viewer.py` 自 #162（8ce3dd8）起沒有再變。

用詞（第一次出現的英文詞）：背景子代理（background agent，主 session 派出後不等它做完就結束這一輪的助手，Workflow 同樣算）；派出（launch，工具結果 `toolUseResult.status` 是 `async_launched` 的那一列）；結束通知（task notification，`queue-operation` 列帶 `<task-notification>`，其 `<status>` 是 completed、failed、killed、stopped 之一）；一輪結束紀錄（`turn_duration` 列）；待完成計數（它上面的 `pendingBackgroundAgentCount`、`pendingWorkflowCount`）；簿記列（bookkeeping row，Claude Code 在兩輪之間自己寫的 `last-prompt`、`mode`、`pr-link`、`cost-state` 這類紀錄）；配對（pairing，派出找到它的結束通知）；登記檔（registry，`~/.claude/sessions/<pid>.json`）；檔尾（tail，transcript 或 rollout 最後 262144 位元組）；快照（snapshot，viewer 每 2 秒組出的 JSON）；鎖檔（lock file，Codex 的 `<codex_home>/thread-writer-locks/<thread-id>.lock`）；對話串（thread，Codex 的一段對話）；主路徑／退回路徑（primary／fallback，Codex 讀 sqlite 的一條，與 sqlite 讀不了時掃 rollout 的一條）；合成測試資料（fixture）。

### Traceability

| From the high-level design | Satisfied by | Status |
|---|---|---|
| UC3（Codex 列 TUI 關掉後約一分鐘內消失、一律推斷；Claude 列照舊） | `### codex_locked_thread_ids`、`### codex_rows`（只列有鎖檔的對話串、`aliveCertainty` 一律 `inferred`）；Verification 的 AC1–AC4 列與 AC8 實機 | covered |
| UC4（只剩背景工作時顯示「執行中（背景）」、推斷、不閃不響、列名稱） | `### classify_claude 與背景檢查`、`### page` 的 `stateLabel`；Verification 的 AC5、AC6 列與 AC8 實機 | covered |
| R2（Codex 假列、列錯專案） | diagnosis 的三個失敗測試，列在 Verification 最前；`### codex_rows` 不再數行程、不再照名額挑 | covered |
| R3（背景子代理在跑時被顯示成「完成，等指示」） | `### classify_claude 與背景檢查`：`idle` 也檢查（main 不查，`plugins/cai/scripts/viewer.py:1524-1527`），字樣與確定度照 V8 | covered |
| diagnosis 的 Failing test（三個） | Verification 第 1–3 列，build 的第一件事 | covered |

## Requirement

Agent Viewer 的兩個錯：（1）Codex 列以行程數推名單，會列出沒開的、別的專案的對話串（diagnosis）；（2）主 session 派出背景子代理後結束這一輪，那一行被判成「完成，等指示」，或照 #162 顯示成和「這一輪還在跑」一樣的「執行中 · 確定」（stance UC4、R3）。給同時開好幾個 Claude Code 與 Codex session 的使用者。怎麼知道做對了：diagnosis 的三個失敗測試轉綠；AC1–AC6 每種情況一個 fixture 測試綠；`python scripts/validate.py` 與 `python -m pytest` 全綠；AC8 實機開關一次 Codex TUI、跑一個背景子代理，看到的和 UC3、UC4 寫的一樣。

## Glossary

| Term | Definition | Where it lives |
|---|---|---|
| 派出 | 背景 Agent 或 Workflow 呼叫的工具結果列，`toolUseResult.status` 是 `async_launched`，id 在 `agentId` 或 `taskId` | plugins/cai/scripts/viewer.py:1437 |
| 配對 | 依檔尾順序，每個派出的 id 找它之後的結束通知；找不到就還在跑 | plugins/cai/scripts/viewer.py:1404 |
| 結束通知 | `queue-operation` 列，`content` 帶 `<task-notification>`、`<task-id>`，且 `<status>` 是四種之一 | new — plugins/cai/scripts/viewer.py（`_task_end`） |
| 一輪結束紀錄 | `type` 為 `system`、`subtype` 為 `turn_duration` 的列 | plugins/cai/scripts/viewer.py:1541 |
| 待完成計數 | 一輪結束紀錄上 `pendingBackgroundAgentCount` 與 `pendingWorkflowCount` 兩個鍵的值 | plugins/cai/scripts/viewer.py:1474 |
| 簿記列 | 不是 `user`、`assistant`、結束通知、一輪結束紀錄的其他列；它們不改變這一輪的結束狀態 | concept |
| 最後的一輪結束 | 檔尾裡最後一筆一輪結束紀錄，且它後面沒有 `user`／`assistant` 列、也沒有結束通知；否則沒有 | new — plugins/cai/scripts/viewer.py（`_last_turn_end`） |
| 背景檢查 | V8 的判斷：最後的一輪結束的待完成計數大於 0，或配對後還有派出在跑 | new — plugins/cai/scripts/viewer.py（`_background_pending`） |
| 執行中（背景） | `state` 為 `working`、`certainty` 為 `inferred`、`background` 為 `true` 的 Claude 列在頁面上的字樣 | new — plugins/cai/scripts/viewer.py（`_as_background`、`stateLabel`） |
| 登記檔 | Claude Code 每個 session 的 `sessions/<pid>.json`，`status` 是 `busy`、`idle`、`waiting`、`shell` 之一 | plugins/cai/scripts/viewer.py:1609 |
| 檔尾 | 讀檔案最後 262144 位元組所得、解析成 dict 的列清單 | plugins/cai/scripts/viewer.py:1173 |
| codex_home | `CODEX_HOME` 環境變數，沒有就是 `~/.codex` | plugins/cai/scripts/viewer.py:2209 |
| 鎖檔 id 集合 | `thread-writer-locks` 裡合格檔名去掉 `.lock` 的集合；目錄列不出來時是 `None` | new — plugins/cai/scripts/viewer.py（`codex_locked_thread_ids`） |
| 主路徑 | 以 `state_*.sqlite` 的 `threads` 與 `thread_history_*.sqlite` 的 `thread_turns` 組 Codex 列 | plugins/cai/scripts/viewer.py:1963 |
| 退回路徑 | sqlite 讀不了時，掃 `sessions/**/rollout-*.jsonl` 組 Codex 列 | plugins/cai/scripts/viewer.py:2018 |
| 快照 | `build_snapshot` 的回傳：`format`、`generatedAt`、`rows`、`problems`，本次加 `codexLockDirMissing` | plugins/cai/scripts/viewer.py:2251 |
| 頁尾那一行 | 頁尾第一行「Codex：找不到 thread-writer-locks，無法判斷哪個 session 開著」，平時隱藏 | new — plugins/cai/scripts/viewer.py（`PAGE_HTML` 的 `#codexLockNote`） |
| 存活確定度 | 列的 `aliveCertainty`，頁面在 `inferred` 時顯示「存活：推斷」 | plugins/cai/scripts/viewer.py:822 |

## Budgets

| What | Number | Where it comes from |
|---|---|---|
| 讀 transcript 檔尾的大小 | 262144 bytes | `plugins/cai/scripts/viewer.py:1236`，不改 |
| 伺服器組快照的間隔 | 2 s | `plugins/cai/scripts/viewer.py:2205`，不改 |
| 頁面輪詢間隔 | 1000 ms | `plugins/cai/scripts/viewer.py:1057`，不改 |
| 過時 busy 規則的門檻 | 60000 ms | `plugins/cai/scripts/viewer.py:1543`，不改（stance Out of scope 第二條） |
| 認得的待完成計數鍵 | 2 | decisions C5 |
| 算結束的 `<status>` | 4 | V8（`docs/design/2026-09-26-viewer-live-status-detail.md:634`） |
| 對話串 id 長度 | 36 characters | decisions C9 |
| 每次組快照列鎖檔目錄 | 1 `os.listdir` | 本設計；不開任何鎖檔（V1、V9） |
| TUI `/quit` 後 Codex 列消失 | 34–62 s（量過一次） | `.claude/track/viewer-live-status-fixes/probe/lock-watch.jsonl:2-3`、`intake.md:46`（00:45:22–00:45:50 之間離開，00:46:24 消失） |
| 退回路徑的 rollout 範圍 | 24 h、200 files | `plugins/cai/scripts/viewer.py:1664-1665`，不改；先以鎖檔 id 篩，再取 200 個 |
| 背景子代理名稱消失（派出被擠出檔尾）的比例 | 5.0 % | decisions C8（40／796） |
| 一輪結束後先來簿記列、子代理還在跑的比例 | 6.3 % | decisions C6（65／1030） |
| 主路徑一次查的對話串數 | 不設上限（原本 `LIMIT 50`），只查鎖檔 id 集合裡的 | `plugins/cai/scripts/viewer.py:1662`、`:1972` |

## Design decisions

- Codex 的存活只看鎖檔檔名（V9、diagnosis 的 Fix）：`build_snapshot` 讀一次鎖檔 id 集合，主路徑以 `id IN (…)` 查、退回路徑以檔名尾的 id 篩；不數行程、不看來源欄、不照名額挑。服務 UC3、R2。
- 鎖檔目錄列不出來（不在、不是目錄、沒權限）一律當成沒有：不出 Codex 列；codex_home 在才在頁尾說明（decisions design-footer、D6）。服務 AC4。
- 頁尾那一行由快照頂層布林欄位 `codexLockDirMissing` 帶過去，字樣寫死在頁面，不顯示 `problems`（decisions D5）。
- Claude 的背景檢查照 V8 兩個訊號並用；「檔尾那筆一輪結束」讀成「最後一個對話事件是一輪結束」，簿記列不擋（decisions D2）。`idle` 一律檢查，`busy` 在最後的一輪結束存在時檢查，`shell` 不查。服務 UC4、R3。
- 派出認 `toolUseResult.status == "async_launched"`，不是 AC5 字面的 `run_in_background`（decisions D3）；結束只認四種 `<status>`（decisions Ruled out 第三列）；待完成計數只認兩個具名的鍵（Ruled out 第一列）。
- 「執行中（背景）」是 `working` 加 `certainty: inferred` 加列欄位 `background: true`，不是第七個狀態；頁面只改 `stateLabel`，排序、計數、不閃不響都沿用 `working`（decisions Tier 3 第一列）。
- 配對找不到名稱（接續、派出在檔尾外）時照樣顯示「執行中（背景）」，名稱清單空著（stance Sacrifices 第五條、decisions D4）；這改變了 AC6 的字面行為。
- 移除 #162 加的行程計數與名額程式及只測它們的測試（diagnosis 的 Blast radius）。

## Diagrams

### Architecture

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart LR
  subgraph FS["本機檔案（唯讀）"]
    REG["~/.claude/sessions/*.json 登記檔"]:::existing
    TR["transcript 檔尾"]:::existing
    LOCK["codex_home/thread-writer-locks 的檔名"]:::added
    SQL["state_*.sqlite、thread_history_*.sqlite"]:::existing
    RO["sessions/**/rollout-*.jsonl"]:::existing
    PROC["codex.exe 行程清單"]:::removed
  end
  subgraph SRV["viewer.py 背景 server"]
    POL["Poller 每 2 秒"]:::existing
    BS["build_snapshot"]:::modified
    CR["claude_rows 與 classify_claude"]:::modified
    CL["codex_locked_thread_ids"]:::added
    CX["codex_rows"]:::modified
    API["GET /api/rows"]:::existing
  end
  subgraph WEB["瀏覽器"]
    PG["PAGE_HTML：stateLabel、頁尾那一行"]:::modified
  end
  POL --> BS
  BS --> CR
  BS --> CL
  BS --> CX
  CR --> REG
  CR --> TR
  CL --> LOCK
  CX --> SQL
  CX --> RO
  PROC -.->|"移除"| BS
  BS -->|"rows、problems、codexLockDirMissing"| API
  API --> PG
  classDef added fill:#d4edda,stroke:#28a745,color:#155724
  classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404
  classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057
  classDef removed fill:#f8d7da,stroke:#dc3545,color:#721c24
```

看哪裡：左上紅框的行程清單整格離開架構，綠色的鎖檔檔名取而代之，而且只經過新的 `codex_locked_thread_ids` 一個入口；跨過 server 與瀏覽器邊界的只多了一個布林欄位。

### Component

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TB
  BS["build_snapshot(config_root, codex_home, now_ms) -> dict"]:::modified
  CL["codex_locked_thread_ids(codex_home) -> set 或 None"]:::added
  CX["codex_rows(codex_home, now_ms, locked_ids) -> (rows, problems)"]:::modified
  PRI["_codex_rows_primary(state_db, history_db, now_ms, locked_ids)"]:::modified
  FB["_codex_rows_fallback(codex_home, now_ms, locked_ids)"]:::modified
  CROW["_codex_row(...)（不改）"]:::existing
  CC["classify_claude(reg, tail, now_ms) -> dict"]:::modified
  BP["_background_pending(tail) -> bool"]:::added
  LTE["_last_turn_end(tail) -> dict 或 None"]:::added
  TE["_task_end(row) -> str 或 None"]:::added
  AS["_async_subagents(tail)"]:::modified
  TSP["_turn_still_pending(row)"]:::modified
  AB["_as_background(result, tail, since) -> dict"]:::added
  BS -->|"一次"| CL
  BS -->|"locked_ids"| CX
  CX -->|"sqlite 在"| PRI
  CX -->|"sqlite 讀不了"| FB
  PRI --> CROW
  FB --> CROW
  CC --> BP
  CC --> AB
  BP --> LTE
  BP --> TSP
  BP --> AS
  LTE --> TE
  AS --> TE
  AB --> AS
  classDef added fill:#d4edda,stroke:#28a745,color:#155724
  classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404
  classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057
```

看哪裡：`_task_end` 是配對與「最後的一輪結束」共用的一個判斷，兩邊對「什麼算結束通知」不會各說各話；`codex_rows` 的第三個參數從兩個數字換成一個集合。

### Flow

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TD
  S{"登記檔 status"}:::existing
  S -->|"waiting 或未知"| OLD["照舊"]:::existing
  S -->|"shell"| SH["完成，等指示 · 背景 shell 執行中（照舊，不查）"]:::existing
  S -->|"idle"| BPI{"背景檢查"}:::added
  S -->|"busy"| LT{"有最後的一輪結束？"}:::added
  LT -->|"有"| BPB{"背景檢查"}:::added
  LT -->|"沒有：這一輪還在跑或剛收到通知"| ST
  BPB -->|"沒有背景"| ST{"tail[-1] 是一輪結束、計數為 0、超過 60 秒？"}:::existing
  BPI -->|"有背景"| BG["執行中（背景）· 推斷 · 不閃不響"]:::added
  BPB -->|"有背景"| BG
  BPI -->|"沒有背景"| DN["完成，等指示 · 確定"]:::existing
  ST -->|"是"| DI["完成，等指示 · 推斷 · 登記檔可能過時"]:::existing
  ST -->|"否"| WK["執行中 · 確定"]:::existing
  classDef added fill:#d4edda,stroke:#28a745,color:#155724
  classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057
```

看哪裡：綠色的背景檢查插在 `idle` 與 `busy` 兩條路的「完成」之前；它只會多判出「執行中（背景）」，灰色的原有結論在各自的條件下一個都沒改。`busy` 在一輪還在跑（最後的一輪結束不存在）時不做檢查，直接走原本的路。

### Sequence — UC3 與 R2

R2 的呼叫順序與 UC3 相同（開一個 TUI、只列它的對話串），不另畫。

```mermaid
sequenceDiagram
  participant U as 使用者
  participant TUI as Codex TUI
  participant APP as Codex app-server
  participant FS as thread-writer-locks
  participant P as Poller.build_snapshot
  participant DB as state_N.sqlite
  U->>TUI: 開啟並送第一則訊息
  APP->>FS: 建立 <thread-id>.lock
  P->>FS: os.listdir（只看檔名）
  FS-->>P: {thread-id}
  P->>DB: SELECT ... WHERE id IN (thread-id)
  DB-->>P: 一列（cwd、rollout_path）
  P-->>U: 快照多一列 Codex，存活：推斷
  U->>TUI: /quit
  Note over APP,FS: 約 34–62 秒後才刪鎖檔
  P->>FS: os.listdir
  FS-->>P: 空集合
  P-->>U: 那一列消失
```

看哪裡：刪鎖檔的是 app-server，不是 TUI，所以 `/quit` 到那一列消失之間隔著約一分鐘；Poller 在這段時間照實列著它、標推斷。

### Sequence — UC4 與 R3

R3 是 UC4 裡「一輪結束時還有背景子代理」那一段，不另畫。

```mermaid
sequenceDiagram
  participant M as 主 session
  participant T as transcript
  participant R as 登記檔
  participant P as Poller.classify_claude
  participant W as 頁面
  M->>T: Agent 呼叫、結果 status async_launched、agentId
  M->>T: turn_duration，pendingBackgroundAgentCount 1
  R-->>P: status busy（或 idle）
  P->>T: 讀檔尾：最後的一輪結束計數 1、派出沒有結束通知
  P-->>W: working、inferred、background true
  W-->>W: 執行中（背景）· 推斷，不閃不響，列出名稱
  T->>T: queue-operation 結束通知，status completed
  M->>T: 新的一輪：user、assistant、turn_duration 計數 0
  R-->>P: status idle
  P->>T: 讀檔尾：計數 0、沒有未配對的派出
  P-->>W: done、confirmed
  W-->>W: 完成，等指示（「完成時也響」開著才響）
```

看哪裡：結束通知一到，主 session 就開新的一輪（decisions C6），所以要看的是「最後的」一輪結束，不是檔尾任何一筆；背景期間的計數只在那一筆一輪結束之後還沒有新對話事件時才可信。

## Implementation spec

所有程式都在 `plugins/cai/scripts/viewer.py`（存在）；`plugins/cai-codex/scripts/viewer.py` 由 `python scripts/gen-codex.py` 重產，不手改。

### codex_locked_thread_ids

- **Responsibility:** 列出 codex_home 底下有鎖檔的對話串 id。
- **Interface:** `def codex_locked_thread_ids(codex_home: str) -> set[str] | None`
- **Data:** 輸入 codex_home 路徑；輸出 id 集合。一個名稱算數的條件：以 `.lock` 結尾、不以 `.` 開頭、去掉 `.lock` 後剛好 36 字元（`CODEX_THREAD_ID_LENGTH`）。目錄列不出來回 `None`；目錄在但沒有合格檔名回空集合。
- **Errors:** `os.listdir` 拋的任何 `OSError`（不在、不是目錄、沒權限，https://docs.python.org/3/library/os.html 「All functions in this module raise OSError (or subclasses thereof)」）→ 回 `None`；不寫 `problems`、不往外拋（decisions D6）。
- **Concurrency:** 只列目錄，不開檔（V1、V9）；Codex 在列目錄與後面的查詢之間新增或刪除鎖檔，最多晚一個輪詢週期反映。
- **Observability:** 回 `None` 時由 `build_snapshot` 轉成 `codexLockDirMissing`。
- **Where it lives:** `plugins/cai/scripts/viewer.py` 的 codex_source 段，放在 `_codex_row` 之前；新增常數 `CODEX_LOCK_DIR = "thread-writer-locks"`、`CODEX_LOCK_SUFFIX = ".lock"`、`CODEX_THREAD_ID_LENGTH = 36`，放在 `CODEX_FALLBACK_MAX_FILES` 之後（取代被移除的 `CODEX_RECENT_THREADS_LIMIT` 與 `CODEX_VSCODE_SOURCE`）。
- **What it reuses:** `os.listdir` 本身；舊 stance V5（`docs/design/2026-09-25-agent-viewer-web-portal-detail.md:995`）指定只用 stdlib。

### codex_rows

- **Responsibility:** 把鎖檔 id 集合變成 Codex 列。
- **Interface:** `def codex_rows(codex_home: str, now_ms: int, locked_ids: set[str] | None) -> tuple[list[dict], list[str]]`；`def _codex_rows_primary(state_db: str, history_db: str, now_ms: int, locked_ids: set[str]) -> tuple[list[dict], list[str]]`；`def _codex_rows_fallback(codex_home: str, now_ms: int, locked_ids: set[str]) -> tuple[list[dict], list[str]]`。
- **Data:** `locked_ids` 是 `None` 或空集合 → 直接回 `([], [])`，不開 sqlite。主路徑查詢改為 `SELECT id, rollout_path, cwd, updated_at_ms, name FROM threads WHERE archived = 0 AND originator = 'codex-tui' AND thread_source = 'user' AND id IN (<每個 id 一個 ?>) ORDER BY updated_at_ms DESC`，參數是 `sorted(locked_ids)`；拿掉 `PRAGMA table_info` 與 `source` 欄、`LIMIT`；`thread_turns` 查法、`_codex_subagents_by_parent` 照舊。每個查到的對話串一列：`_codex_row(thread_id, cwd, name, "inferred", turn_status, rollout_path, now_ms)`，再照舊以 sqlite 的 subagents 覆寫。退回路徑：24 小時內的 rollout 先以檔名去掉 `.jsonl` 後最後 36 字元（`plugins/cai/scripts/viewer.py:2046-2049` 的取法）對 `locked_ids` 篩，依修改時間由新到舊取最多 200 個，再照舊讀首行、以 `originator`、`thread_source` 過濾；每個一列、`aliveCertainty` 與 `certainty` 都是 `inferred`（照舊，`:2065-2066`）；不再以 `_codex_in_progress` 分組。列的形狀不變（`:1920-1926`）。
- **Errors:** 主路徑任何 `sqlite3.Error`（包括 `id IN` 參數太多時）→ 照舊走退回路徑並在 `problems` 前加「Codex 資料庫讀不了，改看紀錄檔」（`:2086-2094`）；單一 rollout 讀不了照舊記一行 `problems`。
- **Concurrency:** 每次呼叫開關各自的 sqlite 連線（照舊）；只有 Poller 一個執行緒呼叫。
- **Observability:** `problems` 照舊。
- **Where it lives:** 現有函式，`plugins/cai/scripts/viewer.py:1963-2094`。
- **What it reuses:** `_codex_row`（`:1911`）、`_codex_subagents_by_parent`（`:1930`）的 `IN` 佔位符寫法（`:1942-1947`）、`_highest_numbered_sqlite`（`:1834`）、`read_first_line`（`:1213`）、`classify_codex`（不改）。

### build_snapshot

- **Responsibility:** 組一份快照。
- **Interface:** `def build_snapshot(config_root: str, codex_home: str, now_ms: int) -> dict`（簽名不變）。
- **Data:** 回傳多一個鍵：`{"format": 1, "generatedAt": int, "rows": list, "problems": list[str], "codexLockDirMissing": bool}`。`locked_ids = codex_locked_thread_ids(codex_home)`；`codex_rows(codex_home, now_ms, locked_ids)`；`codexLockDirMissing = locked_ids is None and os.path.isdir(codex_home)`（decisions design-footer）。`EMPTY_SNAPSHOT` 與沒有 Poller 時 `/api/rows` 的空快照不改（`:2206`、`:1138-1139`），頁面把沒有這個鍵當成 `false`。
- **Errors:** 照舊，未預期例外由 `Poller.run()` 保留上一份快照（`:2337-2343`）。
- **Concurrency:** 照舊。
- **Observability:** 新欄位本身。
- **Where it lives:** `plugins/cai/scripts/viewer.py:2251-2277`，刪掉 `:2257-2259` 的兩次行程計數。
- **What it reuses:** `_codex_home`（`:2209`）由 `cmd_serve` 傳入，不改。

### classify_claude 與背景檢查

- **Responsibility:** 在 `idle` 與 `busy` 的「完成」判斷之前，照 V8 判出只剩背景工作的主 session。
- **Interface:**
  - `CLAUDE_PENDING_COUNT_KEYS = ("pendingBackgroundAgentCount", "pendingWorkflowCount")`；`TASK_END_STATUSES = ("completed", "failed", "killed", "stopped")`，放在 `TASK_NOTIFICATION_TAG`（`:1392`）之後。
  - `def _task_end(row: dict) -> str | None`：`row["type"] == "queue-operation"`、`content` 是含 `TASK_NOTIFICATION_TAG` 的字串、以 `str.partition` 取出的 `<status>` 在 `TASK_END_STATUSES` 裡 → 回 `<task-id>` 的內容（空字串回 `None`）；其餘 `None`。不看 `operation`（照 #162，`:1422-1427`）。
  - `def _async_subagents(tail: list[dict]) -> list[tuple[str, dict]]`：簽名不變；`queue-operation` 那一段改成 `task_id = _task_end(row)`，不是 `None` 才 `running.pop(task_id, None)`。
  - `def _turn_still_pending(row: dict) -> bool`：`any(isinstance(row.get(k), (int, float)) and row[k] > 0 for k in CLAUDE_PENDING_COUNT_KEYS)`。
  - `def _last_turn_end(tail: list[dict]) -> dict | None`：由尾往前走；遇到一輪結束紀錄回它；先遇到 `type` 為 `user` 或 `assistant` 的列，或 `_task_end(row)` 不是 `None` 的列，回 `None`；其餘列略過；走完回 `None`。
  - `def _background_pending(tail: list[dict]) -> bool`：`turn_end = _last_turn_end(tail)`；回 `(turn_end is not None and _turn_still_pending(turn_end)) or bool(_async_subagents(tail))`。
  - `def _as_background(result: dict, tail: list[dict], since) -> dict`：取 `_async_subagents(tail)` 最後一個的呼叫當 `current`（`{"tool", "input", "since"}`，同 `:1555-1560` 的形狀；沒有就留 `None`），再 `result.update(state="working", certainty="inferred", entryId="working:%s" % since, notes=[], background=True)`。
  - `classify_claude(reg: dict, tail: list[dict], now_ms: int) -> dict`：簽名不變。`result` 初值加 `"background": False`（`:1490`）。`idle`：`_background_pending(tail)` 為真 → `return _as_background(result, tail, since)`，否則照舊 `done`。`busy`：最前面加 `if _last_turn_end(tail) is not None and _background_pending(tail): return _as_background(result, tail, since)`；之後的過時規則與一般 `working` 一字不改（`:1535-1563`）。`shell`、`waiting`、未知照舊。
- **Data:** 回傳 dict 多一個鍵 `background: bool`；背景時 `state` `working`、`certainty` `inferred`、`notes` `[]`、`entryId` `working:<statusUpdatedAt>`、`since` `statusUpdatedAt`。`claude_rows` 的 `subagents`（`_claude_subagents`，`:1465-1471`）不改，背景名稱從這裡來；配對找不到名稱時是空清單。
- **Errors:** 無新的例外路徑；transcript 讀不到時檔尾是空清單（`:1632`），兩個訊號都沒有，照舊判做完。
- **Concurrency:** 純函式，只有 Poller 呼叫。
- **Observability:** 列上的 `background` 與 `certainty`。
- **Where it lives:** `plugins/cai/scripts/viewer.py:1384-1563`（claude_source 段）。
- **What it reuses:** `_async_subagents`（`:1404`）、`_param_summary`（`:1258`）、`ACTION_INPUT_MAX`（`:1241`）、`_subagent_name`（`:1395`）。

### page

- **Responsibility:** 顯示「執行中（背景）」與頁尾那一行。
- **Interface:** `PAGE_HTML` 裡三處：`stateLabel(row)` 的 `working` 分支改為 `return {label: row.background === true ? '執行中（背景）' : '執行中', icon:''};`（`:741`）；`<footer>` 的第一個子節點加 `<span id="codexLockNote" hidden>Codex：找不到 thread-writer-locks，無法判斷哪個 session 開著<br></span>`（`:640`）；`poll()` 在 `lastGeneratedAt = data.generatedAt;` 之後加 `document.getElementById('codexLockNote').hidden = data.codexLockDirMissing !== true;`（`:1014`）。
- **Data:** 讀列的 `background` 與快照的 `codexLockDirMissing`，都是布林；兩者都沒有時當 `false`。
- **Errors:** 無；字樣是頁面裡的常數，不插入任何列欄位，`tests/test_viewer_page.py` 的跳脫檢查不受影響。
- **Concurrency:** 無。
- **Observability:** 畫面本身。
- **Where it lives:** `plugins/cai/scripts/viewer.py:396-1062`。
- **What it reuses:** 「等你簽核」以次要欄位換標籤的寫法（`:729-732`）；`#offlineNote`、`#staleNote` 以 `hidden` 切換的寫法（`:610`、`:903-911`）；`META` 的 `working`（`:660`）讓排序、頂端計數、不閃不響自動成立。

### 移除

照 diagnosis 的 Blast radius（`docs/design/2026-09-26-viewer-live-status-detail.md:564`），在 d514f6b 重新核對過行號：`CODEX_APP_SERVER_MARKER`、`_is_app_server`（`plugins/cai/scripts/viewer.py:73-82`）；`_PROCESSENTRY32W`（`:90-102`）、`_TH32CS_SNAPPROCESS`（`:107`）；`_win_kernel32` 裡 `CreateToolhelp32Snapshot`、`Process32FirstW`、`Process32NextW`、`QueryFullProcessImageNameW` 的型別設定（`:118-124`）；`_process_image_path_windows`（`:127-142`）；`_count_processes_windows`（`:193-215`）、`_count_processes_linux`（`:259-284`）、`count_processes`（`:299-305`）；`CODEX_RECENT_THREADS_LIMIT`（`:1662`）；`CODEX_VSCODE_SOURCE` 與其註解（`:1666-1671`）、`_codex_session_slots`（`:1674-1678`）；主路徑的 `source` 欄與名額（`:1966-1974`、`:1990-2005`）；退回路徑的 `source` 與分組（`:2050`、`:2052-2062`）；`codex_rows` 的兩個數字參數與 `process_count == 0` 判斷（`:2072-2081`）；`build_snapshot` 的兩次計數（`:2257-2259`）。liveness 段開頭的註解（`:65-71`）改成只講 `check_alive`，`_FILETIME`、`process_start`、`check_alive` 與兩個平台實作留下（Claude 列與狀態檔還在用，`:1625`、`:2319`）。測試那一側只因這次變成沒人用的 helper（例如 `_session_meta` 的 `source` 參數）一併移除。

## Naming

| Name | What it is | Chosen by |
|---|---|---|
| 執行中（背景） | 背景時的狀態字樣 | the user, 2026-09-26（`.claude/track/viewer-live-status-fixes/options-design-bglabel.md:15-21`） |
| Codex：找不到 thread-writer-locks，無法判斷哪個 session 開著 | 頁尾那一行 | the user, 2026-09-26（`.claude/track/viewer-live-status-fixes/options-intake-nolock.md:6`） |
| `background` | Claude 列的布林欄位 | follows the row fields' lower-case/camelCase convention at `plugins/cai/scripts/viewer.py:1638-1644` |
| `codexLockDirMissing` | 快照頂層布林欄位 | follows `generatedAt`'s camelCase at `plugins/cai/scripts/viewer.py:2277` |
| `codexLockNote` | 頁尾那一行的元素 id | follows `offlineNote`／`staleNote` at `plugins/cai/scripts/viewer.py:610` |
| `codex_locked_thread_ids` | 鎖檔 id 集合的函式 | follows the public `codex_rows`/`claude_rows` naming at `plugins/cai/scripts/viewer.py:1609`、`:2072` |
| `_task_end`、`_last_turn_end`、`_background_pending`、`_as_background` | 背景檢查的私有 helper | follows the `_turn_still_pending`/`_async_subagents` private-helper convention at `plugins/cai/scripts/viewer.py:1404`、`:1474` |
| `CLAUDE_PENDING_COUNT_KEYS`、`TASK_END_STATUSES` | 兩組常數 | follows `CLAUDE_BACKGROUND_TOOLS`／`ASYNC_LAUNCHED_STATUS` at `plugins/cai/scripts/viewer.py:1390-1392` |
| `CODEX_LOCK_DIR`、`CODEX_LOCK_SUFFIX`、`CODEX_THREAD_ID_LENGTH` | 鎖檔相關常數 | follows the `CODEX_*` constants at `plugins/cai/scripts/viewer.py:1660-1665` |
| `thread-writer-locks`、`.lock` | Codex 自己的目錄與副檔名 | Codex 0.157.1（`.claude/track/viewer-live-status-fixes/probe/findings.md:5-9`） |
| 測試名稱 | 見 `## Verification` | follows `test_<subject>_<behaviour>` at `tests/test_viewer_codex.py:314` |

## Change points

| Path | Change | Exists today |
|---|---|---|
| `plugins/cai/scripts/viewer.py` | 上面的五個元件與移除清單 | yes |
| `tests/test_viewer_codex.py` | diagnosis 三個測試、AC1–AC4 的測試；所有 `codex_rows(..., N)` 呼叫改傳鎖檔集合；移除名額與 `vscode` 的測試 | yes |
| `tests/test_viewer_claude.py` | AC5、AC6 的測試；改寫 #162 的兩個 `busy` 背景測試 | yes |
| `tests/test_viewer_http.py` | `build_snapshot` 的兩個測試改替換 `codex_locked_thread_ids` | yes |
| `tests/test_viewer_liveness.py` | 移除四個行程計數測試；V2 測試只打 `check_alive`、`process_start` 與 `codex_locked_thread_ids` | yes |
| `tests/test_viewer_page.py` | 背景字樣與頁尾那一行的靜態測試 | yes |
| `plugins/cai-codex/scripts/viewer.py` | `python scripts/gen-codex.py` 重產 | yes |
| `plugins/cai/.claude-plugin/plugin.json`、`plugins/cai-codex/.codex-plugin/plugin.json`、`scripts/codex-release.json`、`plugins/cai-codex/agents/*.toml` | 版本號（ship 時決定） | yes |

沒有新相依。

## Failure modes

| Situation | What happens | What the caller sees |
|---|---|---|
| 沒裝 Codex（codex_home 不在） | 鎖檔 id 集合是 `None`，不出 Codex 列，`codexLockDirMissing` 為 false | 頁面和今天一樣，沒有任何 Codex 字樣 |
| codex_home 在、鎖檔目錄不在或讀不了（Linux、macOS、舊版 Codex 未查） | 不出 Codex 列，`codexLockDirMissing` 為 true | 頁尾第一行「Codex：找不到 thread-writer-locks，無法判斷哪個 session 開著」 |
| 鎖檔目錄在、沒有合格檔名（只有 `.coordination.lock`） | 空集合，不開 sqlite | 沒有 Codex 列，頁尾不說明 |
| 還沒送第一則訊息的 TUI（暫時 id 的鎖檔） | 查不到 `threads` 列 | 沒有它的列（照舊，`intake.md:42`） |
| TUI `/quit` 後鎖檔還在約一分鐘 | 那一列照列 | 「存活：推斷」的列多掛約一分鐘（UC3） |
| 強制關閉視窗後鎖檔殘留（只量到一次，數分鐘，`probe/findings.md:7`） | 那一列照列到鎖檔被清 | 多掛數分鐘；留給 AC8 實機確認 |
| VS Code 擴充套件開的對話串若沒有鎖檔（本機量不到） | 不成列 | main 在 `inProgress` 時列出的這種列看不到（diagnosis Out of scope） |
| 主路徑查詢失敗（任何 `sqlite3.Error`） | 退回路徑，以同一個 id 集合篩 | Codex 列全標推斷；`problems` 一行（頁面不顯示） |
| sqlite 壞掉、又接續了 24 小時沒動、還沒送訊息的舊對話串 | 退回路徑看不到它的 rollout | 送出第一則訊息、rollout 被寫入後才出現（decisions D7） |
| 背景子代理以 SendMessage 接續，或派出被擠出檔尾（5.0 %） | 計數仍大於 0 → 背景；配對找不到名稱 | 「執行中（背景）· 推斷」，沒有名稱、「目前」空著（AC6 的字面行為改了，decisions D4） |
| 一輪結束後先寫了簿記列（6.3 % 的背景等待） | 最後的一輪結束仍然成立 | 照樣「執行中（背景）」（decisions D2） |
| 結束通知到了、主 session 在處理它 | 最後的一輪結束不存在，走原本 `busy` 路線 | 「執行中 · 確定」，正確：主 session 真的在做事 |
| 某個背景子代理一直沒有結束通知，或 Claude Code 改了 `<status>` 的用字（不在四種之內） | 配對一直認為它在跑 | 那一行一直「執行中（背景）」，直到派出被擠出檔尾且計數也不再大於 0（stance Sacrifices 第五條）。注意：`<status>` 用字改變落在這一格，不是 Sacrifices 第六條說的「退回 fa1a0e0 的行為」；會退回 fa1a0e0 的是派出標記或計數鍵改名 |
| session 結束後被接續、上次留下計數大於 0 的一輪結束、沒有補發 `stopped` | 在使用者送出第一則訊息前，最後的一輪結束仍說有背景 | 短暫的「執行中（背景）」；掃描裡補發 `stopped` 的例子見 decisions C3 |
| 將來多一種待完成計數（例如背景 shell 的） | 不認 | 照 V8 不算背景 |
| 登記檔 `shell` 而同時有背景子代理 | 不做檢查（stance Out of scope） | 「完成，等指示 · 背景 shell 執行中」照舊 |

## Rollout

- **分段：** 一個 PR 出貨兩題。兩題碰的是 `viewer.py` 不同段落，但同一個檔、同一次版本號；分兩個 PR 要 bump 兩次版本，沒有好處。Work breakdown 的 unit 1、2 可以各自先綠，合在同一個分支。
- **既有資料：** 沒有遷移也沒有回填；viewer 不寫任何資料（舊 stance V1）。
- **在跑的呼叫者：** 已在跑的 viewer server 會繼續跑舊程式，直到使用者 `/cai:viewer stop` 再 `/cai:viewer`（launcher 沿用同 `format` 的 server，`plugins/cai/scripts/viewer.py:2436-2451`；decisions D8）。PR 說明要寫這一句。頁面是由同一個 server 送出，新舊頁面與快照不會混用。
- **版本與 Codex 樹（AC7）：** 版本號在 ship 時對當時的 main 取——本 track 期間 main 已從 41cb6e1 前進到 d514f6b（1.34.2、0.2.20），合併前可能再動。順序：把 `plugins/cai/.claude-plugin/plugin.json` 的 `version` 改成高於 main 的號碼；`python scripts/gen-codex.py`；`python scripts/gen-codex.py --release <高於 main 的 cai-codex 號碼>`；`python scripts/gen-codex.py --check` exit 0；`python scripts/validate.py` 與 `python -m pytest` 全綠。
- **回滾：** revert 那一個 commit；沒有寫過任何資料，使用者 stop／start viewer 即回到舊行為。

## Verification

diagnosis 的三個失敗測試最先，其次 AC1–AC6，最後是被取代或移除的既有測試。所有 fixture 都是合成的，不抄任何真實 transcript 或 Codex 資料。

| Criterion | Level | What it needs | Green before |
|---|---|---|---|
| R2／diagnosis 1：`tests/test_viewer_codex.py::test_build_snapshot_lists_the_locked_thread_whatever_its_source`——較舊的 `cli` 對話串（別的專案、沒鎖檔）與較新的 `vscode` 對話串（有鎖檔），只列較新那一列 | unit | `tmp_path` 當 codex_home；`_write_rollout`、`_make_state_db(..., sources=...)`、`_make_history_db`；`thread-writer-locks/` 放 `.coordination.lock` 與指定的 `<id>.lock`；空的 Claude config root；`monkeypatch.setattr(viewer, "count_processes", lambda name, skip_app_server=False: 1 if skip_app_server else 3, raising=False)`；呼叫 `viewer.build_snapshot`（diagnosis 的共同設定，`docs/design/2026-09-26-viewer-live-status-detail.md:578`） | unit 1 合併；先寫、先確認在 d514f6b 上失敗 |
| R2／diagnosis 2：`test_build_snapshot_lists_no_codex_row_before_the_first_message`——一個 `cli` 對話串沒鎖檔，另有一個 id 不在 `threads` 的暫時鎖檔，0 列 | unit | 同上 | unit 1 合併；先失敗 |
| R2／diagnosis 3：`test_build_snapshot_lists_only_the_resumed_older_thread`——兩個 `cli` 對話串、只有較舊的有鎖檔，只列較舊那一列 | unit | 同上 | unit 1 合併；先失敗 |
| AC1：`test_codex_rows_returns_empty_without_locked_threads`（取代 `:314-325`）——`locked_ids` 為 `None` 或空集合時 `([], [])`；一個 `inProgress` 對話串沒鎖檔也不成列 | unit | `codex_rows` 直接呼叫 | unit 1 合併 |
| AC2：`test_codex_rows_keeps_the_turn_classification_of_a_locked_thread`——有鎖檔的 `inProgress` 對話串 `state` `working`、`certainty` `confirmed`、`aliveCertainty` `inferred`；`completed` 的是 `done` | unit | 同上 | unit 1 合併 |
| AC2：`test_codex_rows_lists_every_locked_thread_as_inferred`（取代 `:369-389` 的名額測試）——四個有鎖檔的對話串四列，全標推斷 | unit | 同上 | unit 1 合併 |
| AC3：`test_codex_locked_thread_ids_reads_only_thread_lock_names`——`.coordination.lock`、`<36>.lock.tmp`、`short.lock`、沒有副檔名的 `<36>` 都不算，只回合格的 id | unit | `tmp_path` 下建目錄與空檔 | unit 1 合併 |
| AC3：`test_codex_locked_thread_ids_never_opens_a_lock_file`——`builtins.open` 與 `os.open` 對 `thread-writer-locks` 底下的路徑一律拋 `AssertionError`，函式照樣回正確集合 | unit | `monkeypatch` | unit 1 合併 |
| AC4：`test_codex_locked_thread_ids_is_none_when_the_dir_cannot_be_listed`——目錄不在、同名的是一般檔案，兩種都回 `None` | unit | `tmp_path` | unit 1 合併 |
| AC4：`test_codex_rows_fallback_lists_only_locked_rollouts`（取代 `:639-666` 兩個）——沒有 sqlite、兩個 24 小時內的 rollout、只有一個有鎖檔，只列那一個、標推斷 | unit | `_write_rollout` | unit 1 合併 |
| AC4：`test_build_snapshot_flags_a_missing_lock_dir_when_codex_home_exists`、`test_build_snapshot_does_not_flag_when_codex_home_is_absent`、`test_build_snapshot_does_not_flag_when_the_lock_dir_exists` | unit | `tmp_path`；空的 Claude config root | unit 1 合併 |
| AC4 頁面：`tests/test_viewer_page.py::test_footer_has_the_codex_lock_note_hidden_by_default`、`test_poll_toggles_the_codex_lock_note` | unit（靜態） | `viewer.PAGE_HTML` 字串 | unit 3 合併 |
| AC5：`tests/test_viewer_claude.py::test_idle_with_an_unpaired_background_agent_is_background_working`——派出、計數 1 的一輪結束、`idle` → `working`、`inferred`、`background` true、`entryId` `working:<since>`、`notes` 空、`current` 是那次 Agent 的 description | unit | `_reg`、`_tool_use`、`_async_launch_result`、`_turn_duration`（`tests/test_viewer_claude.py:99-146`） | unit 2 合併 |
| AC5：`test_busy_turn_end_with_pending_agents_is_background_working`、`test_busy_turn_end_with_pending_workflow_is_background_working`（取代 `:248-262`、`:282-289`：確定度改推斷、多 `background` true） | unit | 同上、`_workflow_launch` | unit 2 合併 |
| AC5／decisions D2：`test_busy_turn_end_behind_bookkeeping_rows_is_still_background`——計數 1 的一輪結束後接 `{"type": "last-prompt"}`、`{"type": "mode"}`、`{"type": "pr-link"}`，仍是背景 | unit | 同上 | unit 2 合併 |
| AC5：`test_busy_after_a_completion_notice_is_plain_working`——派出、計數 1、結束通知在最後 → `working`、`confirmed`、`background` false | unit | `_task_notification` | unit 2 合併 |
| AC5：`test_idle_after_every_background_task_ended_is_done`——派出、計數 1、結束通知、`user`、`assistant`、計數 0 的一輪結束 → `done`、`confirmed` | unit | 同上 | unit 2 合併 |
| AC5／V8：`test_a_notice_with_another_status_does_not_end_a_launch`——`<status>progress</status>` 的通知不算結束；`stopped` 算 | unit | `_task_notification(task_id, status=...)` | unit 2 合併 |
| AC5／V8：`test_turn_still_pending_only_counts_positive_numbers`（`:274-279` 加一條）——`pendingShellCount=1` 不算 | unit | `_turn_duration` | unit 2 合併 |
| AC5：`test_shell_with_a_background_agent_is_still_done_with_note`——`shell` 不做檢查 | unit | 同上 | unit 2 合併 |
| AC5 頁面：`tests/test_viewer_page.py::test_state_label_shows_background_working`——`PAGE_HTML` 有「執行中（背景）」且 `stateLabel` 看 `row.background === true`；`test_meta_has_exactly_the_six_real_state_keys`（`:103-110`）不改、照樣綠，證明沒有第七個狀態 | unit（靜態） | `viewer.PAGE_HTML` | unit 3 合併 |
| AC6：`test_idle_with_only_a_pending_count_is_background_without_names`——檔尾只有計數 1 的一輪結束（接續或派出在檔尾外）→ 背景、`current` `None`，`viewer._claude_subagents(tail) == []` | unit | `_turn_duration` | unit 2 合併 |
| 取代：`tests/test_viewer_codex.py` 其餘 `codex_rows(..., N)` 呼叫（`:328-366`、`:461-578`、`:583-636`、`:669-682`）改傳鎖檔集合，斷言不變；移除 `:408-458` 五個名額與 `vscode` 測試；`_two_threads` 若沒人用就移除 | unit | 既有 fixture | unit 1 合併 |
| 取代：`tests/test_viewer_http.py::test_build_snapshot_assembles_rows_and_problems`、`test_build_snapshot_track_is_none_when_cwd_missing` 改替換 `codex_locked_thread_ids` 與三參數的 `codex_rows`，斷言傳進去的是那個集合、`codexLockDirMissing` 為 false | unit | `monkeypatch` | unit 1 合併 |
| V2 不減（舊 stance `docs/design/2026-09-25-agent-viewer-web-portal-detail.md:992`）：`tests/test_viewer_liveness.py::test_no_os_kill_is_ever_called` 拿掉 `count_processes` 兩行（`:35-38`），保留所有 `check_alive`、`process_start` 呼叫，加一次 `codex_locked_thread_ids`；移除 `:104-171` 四個計數測試；`test_check_alive_*` 三個不動 | unit | `monkeypatch`、`tmp_path` | unit 1 合併 |
| AC7：`python scripts/validate.py` 與 `python -m pytest` 全綠；`python scripts/gen-codex.py --check` exit 0 | integration | 本機 Windows；CI 的 Linux | unit 4 合併、ship 前 |
| AC8／UC3：開一個 Codex TUI、送一則訊息，看到那一列（存活：推斷、正確的專案與 track）；`/quit` 後約一分鐘內消失；另外按視窗 X 強制關閉一次，記下那一列多久消失（`probe/findings.md:7` 只量過一次、與另一個 TUI 結束重疊） | end-to-end（手動） | 使用者操作 Codex 0.157.1；新版 viewer（先 stop 再 start） | verify |
| AC8／UC4：主 session 派一個背景子代理後結束這一輪，那一行是「執行中（背景）· 推斷」、不閃不響、列出名稱；子代理結束、主 session 回報後才變「完成，等指示」 | end-to-end（手動） | 同上 | verify |

## Work breakdown

照 stage-build.md 的格式記錄偏離。風險最高的是 unit 1：它刪掉 #162 剛加的程式、改寫最多既有測試，而且 diagnosis 要求它的三個測試先寫、先看到失敗。

| Unit | Depends on | Can run alongside | Done when |
|---|---|---|---|
| 1 Codex 只看鎖檔：先寫 diagnosis 的三個測試並確認在 d514f6b 上失敗；再做 `codex_locked_thread_ids`、`codex_rows` 三個函式、`build_snapshot` 的接線與 `codexLockDirMissing`；刪移除清單；改寫 `test_viewer_codex.py`、`test_viewer_http.py`、`test_viewer_liveness.py` | nothing | 2（不同段落；同一個檔，依序合進分支） | Verification 裡標 unit 1 的列全綠 |
| 2 Claude 背景檢查：`_task_end`、`_last_turn_end`、`_background_pending`、`_as_background`，改 `_async_subagents`、`_turn_still_pending`、`classify_claude`；`test_viewer_claude.py` 的 AC5、AC6 測試 | nothing | 1 | Verification 裡標 unit 2 的列全綠 |
| 3 頁面：`stateLabel`、頁尾那一行、`poll()`；`test_viewer_page.py` | 1（`codexLockDirMissing`）、2（`background`） | nothing | Verification 裡標 unit 3 的列全綠 |
| 4 出貨準備：版本號、`gen-codex.py`、`--release`、`--check`、`validate.py`、`pytest` | 1、2、3 | nothing | AC7 那一列全綠 |
| 5 實機驗證（verify 階段） | 4，且使用者 stop／start viewer | nothing | AC8 兩列照寫的看到；強制關閉的殘留時間記進 verify 報告 |

### Upstream blockers

| What | Owned by | Needed before |
|---|---|---|
| 使用者在本機開關一次 Codex TUI（含一次按視窗 X）、讓主 session 跑一個背景子代理 | 使用者 | unit 5 |
| ship 時當下的 main 版本號（本 track 期間 main 已前進） | main 分支 | unit 4 的版本號，ship 前再對一次 |


## 整併補充：viewer-live-status-decisions

來源為原 `2026-09-26-viewer-live-status-decisions.md`；以下僅保留上游背景或實作補充，現況以本檔維護說明為準。

#### Feasibility

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | 認出一次背景派出：`toolUseResult.status == "async_launched"`，id 在 `agentId`（Agent）或 `taskId`（Workflow） | verified | `~/.claude/projects/D--project-claude-all-in-one/a8af33f2-a42d-4e02-b0d5-10d322d5ac2b.jsonl:100-101`；#162 的讀法 `plugins/cai/scripts/viewer.py:1437-1442`。掃描：801 次 `async_launched`，Agent 783 次都另帶 `isAsync: true`，Workflow 18 次都沒有 `isAsync` |
| C2 | AC5 字面的 `run_in_background: true` 認不出派出 | verified | Agent 呼叫常常沒有這個參數（`~/.claude/projects/D--project-day-trading-monarch-3/402ed4d7-e8c2-4eee-afec-1b47cdf054ec.jsonl:1043`）；有的時候值是字串 `"true"`（`a8af33f2-a42d-4e02-b0d5-10d322d5ac2b.jsonl:100`）；布林值 `true` 只出現在 Bash 呼叫（同檔 `:146`） |
| C3 | 結束通知帶 `<task-id>` 與 `<status>`；每一則指向派出的通知，`<status>` 都是 `completed`、`failed`、`killed`、`stopped` 之一 | verified | `a8af33f2-a42d-4e02-b0d5-10d322d5ac2b.jsonl:108`；`stopped`：`~/.claude/projects/D--project-claude-all-in-one-2-claude-all-in-one/81ee4381-89f2-4ef0-ad00-61b615799747.jsonl:1155`；`killed`：`~/.claude/projects/D--project-day-trading-monarch-4/2a72e8e3-38c2-4ffe-89f0-5fad3ad85779.jsonl:1486`。掃描：801 次派出之後第一則同 id 通知為 completed 787、failed 6、killed 2、stopped 1，另 5 次還沒有通知；32 則沒有 `<status>` 的通知沒有一則指向派出。#162 收到任何通知就算結束（`plugins/cai/scripts/viewer.py:1422-1427`） |
| C4 | SendMessage 接續：結果只有 `resumedAgentId`，沒有派出紀錄；之後同一 id 再來一則通知 | verified | `402ed4d7-e8c2-4eee-afec-1b47cdf054ec.jsonl:1131-1132`、`:1160`；接續後一輪結束的計數是 1（`~/.claude/projects/D--project-claude-all-in-one/2162ccb5-c60c-447a-9112-ce3620300e7b.jsonl:231`、`:241-242`） |
| C5 | 待完成計數只見過兩個鍵，而且只在大於 0 時出現 | verified | `2162ccb5-c60c-447a-9112-ce3620300e7b.jsonl:241`；#162 的萬用比對 `plugins/cai/scripts/viewer.py:1474-1480`。掃描：2397 筆一輪結束，`pendingBackgroundAgentCount` 出現 1010 筆、`pendingWorkflowCount` 20 筆，每一筆的值都大於 0，沒有第三種鍵 |
| C6 | 一輪結束之後會接著寫什麼 | verified | 掃描，1030 筆計數大於 0 的一輪結束：後面還有下一筆一輪結束的 1025 筆，每一筆中間都先有一個 `user` 列（新的一輪）；111 筆後面第一個緊接的是簿記列，其中 65 筆之後等到的第一個對話事件是結束通知，也就是背景子代理那時還在跑（例：`~/.claude/projects/D--project-day-trading-monarch/5672bbdb-faca-4cd4-946f-d8c68405dae4.jsonl:832-837`，一輪結束、四列簿記、才是通知）。`system/away_summary` 只跟在計數為 0 的一輪結束後面（292 筆，約 184 秒後），計數大於 0 的後面 0 筆。主 transcript 裡沒有 `isSidechain: true` 的 `user`／`assistant` 列（92774 列全是主線） |
| C7 | 登記檔：`idle` 是一輪做完在等使用者；背景子代理在跑時一直是 `busy` | verified | `.claude/track/done/agent-viewer-web-portal/discover-evidence.md:11`；`.claude/track/viewer-live-status-fixes/probe/registry-bg.jsonl:3` |
| C8 | 檔尾 262144 位元組裝不下派出紀錄的比例 | verified | 檔尾大小 `plugins/cai/scripts/viewer.py:1236`、`:1632`。掃描：796 次有通知的派出，從派出那一列到通知寫下時檔尾的距離中位數 45001、p90 159428 位元組；40 次（5.0%）超過 262144，也就是子代理還在跑時派出紀錄已被擠出檔尾 |
| C9 | 列 `thread-writer-locks` 的檔名就得到開著的對話串 id；id 是 36 字元；目錄裡另有點開頭的 `.coordination.lock` 與還沒送訊息時的暫時 id | verified | `docs/design/2026-09-26-viewer-live-status-detail.md:564`、`:38`、`:53`；`.claude/track/viewer-live-status-fixes/probe/findings.md:7-9`（Codex 0.157.1、Windows 實機） |
| C10 | `os.listdir` 只回名稱、不含 `.` 與 `..`；目錄不在、不是目錄、沒權限都拋 `OSError` 的子類 | verified | https://docs.python.org/3/library/os.html#os.listdir 「Return a list containing the names of the entries in the directory given by path.」；https://docs.python.org/3/library/os.html 「All functions in this module raise OSError (or subclasses thereof) in the case of invalid or inaccessible file names and paths」；https://docs.python.org/3/library/exceptions.html 「The following exceptions are subclasses of OSError」（FileNotFoundError、NotADirectoryError、PermissionError） |
| C11 | 頁面今天不顯示快照的 `problems`；頁尾是寫死的文字；`problems` 裡是路徑與錯誤原文 | verified | 頁尾 `plugins/cai/scripts/viewer.py:640-647`；`poll()` 只取 `rows` 與 `generatedAt`（`:998-1016`）；`problems` 的內容 `:1571`、`:1575`、`:2028`、`:2040`、`:2094` |
| C12 | codex_home 的決定方式；沒裝 Codex 的人今天看不到任何 Codex 字樣 | verified | `plugins/cai/scripts/viewer.py:2209-2211`；行程數 0 時 `codex_rows` 直接回空（`:2080-2081`），頁尾沒有 Codex 的字（`:640-647`） |
| C13 | 頁面怎麼處理狀態：六個狀態值有測試釘住；排序、「需要你」、閃燈都看 `META`；標籤可由次要欄位換（「等你簽核」）；頂端「執行中」計數看 `state`；只有 `HUMAN_STATES` 會響 | verified | `tests/test_viewer_page.py:103-110`；`plugins/cai/scripts/viewer.py:655-662`、`:729-732`、`:815-818`、`:894`、`:954`、`:976-996` |
| C14 | launcher 看到已在跑、`/identity` 回 `format` 1 的 server 就沿用它，不換成新版程式 | verified | `plugins/cai/scripts/viewer.py:2436-2451`、`:1149` |
| C15 | Codex 兩條讀取路徑今天的形狀：主路徑取最近 50 筆再照名額挑；退回路徑掃 24 小時內最多 200 個 rollout，id 取檔名最後 36 字元 | verified | `plugins/cai/scripts/viewer.py:1966-1974`、`:1990-2005`；`:1664-1665`、`:2020-2034`、`:2046-2049` |

#### Ruled out

| Option | Invariant it violates | Evidence |
|---|---|---|
| 照 #162 以 `pending*Count` 萬用比對任何計數（`plugins/cai/scripts/viewer.py:1478-1480`） | V8「有沒有背景子代理（含 Workflow）在跑……背景 shell 不算」（`docs/design/2026-09-26-viewer-live-status-detail.md:634`）：將來多一個背景 shell 或其他種類的計數，萬用比對會照單全收 | C5 |
| 照 main 在 `idle` 時直接判做完、不檢查（`plugins/cai/scripts/viewer.py:1524-1527`） | V8：`idle` 也要做這道檢查（`stance.md:29`） | C7 |
| 照 #162 收到任何 `<task-notification>` 就算那次派出結束，不看 `<status>`（`plugins/cai/scripts/viewer.py:1424-1426`） | V8：結束通知是 completed、failed、killed、stopped 之一（`stance.md:29`）；其他 status 不算結束 | C3 |
| 以登記檔 `status` 判斷有沒有背景工作 | V8：登記檔只決定要不要檢查（`stance.md:29`）；背景在跑時它一直是 `busy` | C7 |
| 背景時照 #162 顯示「執行中 · 確定」 | V8：「執行中（背景）」、確定度「推斷」（`stance.md:29`） | C13 |
| 數 `codex.exe`、看 rollout 修改時間、或開啟鎖檔來決定 Codex 列 | V9：只看鎖檔目錄裡的檔名（`stance.md:30`） | C9 |
| 鎖檔目錄不在時退回數行程 | V9（`stance.md:30`）；使用者否決（`.claude/track/viewer-live-status-fixes/options-intake-nolock.md:23-29`） | C9 |

#### Requirement gaps

本輪沒有。會影響使用者怎麼用的取捨——背景 shell 算不算、沒有鎖檔目錄怎麼辦、約一分鐘的延遲、字樣與確定度、沒裝 Codex 的頁尾——都已由使用者以選單決定（`intake.md:17-23`、`:46`；`options-design-bglabel.md`、`options-design-footer.md`），下面各條的失敗條件都是技術事實。

#### Tier 1

##### design-footer — 根本沒裝 Codex（連 codex_home 都沒有）的人，頁尾也要顯示「找不到 thread-writer-locks」那一行嗎？


| Option | Rests on | What it costs | Fails when |
|---|---|---|---|
| A — 只在 codex_home 存在、鎖檔目錄列不出來時顯示 (recommended) | C12 | 一個目錄判斷、一個測試 | 有人把 `CODEX_HOME` 指到不存在的地方，卻期待被提醒 |
| B — 列不出鎖檔目錄就顯示，不管有沒有裝 Codex | C12 | 零 | 每個只用 Claude Code 的人頁尾都多一行 Codex 的字 |

- **Blast radius:** 快照組裝與頁面頁尾，同一支 `viewer.py` 的兩處。
- **Found out when:** 只用 Claude Code 的人打開頁面時——發版後。
- **Undo cost:** 改一個條件；使用者看到的頁尾會變。
- **Decided:** A — 使用者 2026-09-26 以選單選「只在有裝 Codex 時說明 (Recommended)」（`.claude/track/viewer-live-status-fixes/options-design-footer.md`；diagnosis 的 `## Fix` 已記，`docs/design/2026-09-26-viewer-live-status-detail.md:602`）。

#### Tier 2

##### D2 — V8 的「檔尾那筆一輪結束」指哪一筆？

選：檔尾裡最後一筆一輪結束紀錄，只要它後面沒有 `user`／`assistant` 列、也沒有結束通知（C3 的四種 status）；簿記列不算數。`busy` 的閘門「檔尾最後是一輪結束」照同一讀法：最後一個對話事件是一輪結束。不選「`tail[-1]` 本身」：111／1030 筆計數大於 0 的一輪結束後面先來簿記列，其中 65 筆子代理還在跑（C6），那段時間 `busy` 會退回 #162 的「執行中 · 確定」（使用者否決的樣子，`.claude/track/viewer-live-status-fixes/options-design-bglabel.md:23-29`），`idle` 會漏掉計數而判成做完；不選「檔尾裡任何一筆一輪結束」：結束通知一到，主 session 就開新的一輪（1025／1025，C6），舊計數已過時，`busy` 時會把正在做事的主 session 標成背景。比起字面讀法，這個讀法只會讓更多列判成背景（`busy` 的「執行中 · 確定」、`idle` 的「完成」），而且只在那筆一輪結束之後還沒有任何對話事件時；過時 busy 規則照舊只看 `tail[-1]`（`stance.md` Out of scope 第二條，`plugins/cai/scripts/viewer.py:1540-1543`）。若你把 V8 讀成字面上的最後一列，這一條等於改 V8，Gate 1 請說，會回 stance。**Found out when:** 簿記列只在實機出現——發版後，或 AC8 實機剛好碰到。

##### D3 — AC5 寫的 `run_in_background: true` 認不出派出，改用什麼？

選：`toolUseResult.status == "async_launched"`，id 取 `agentId` 或 `taskId`，照 #162 現有讀法（`plugins/cai/scripts/viewer.py:1437-1442`，C1）。AC5 字面的參數多半不存在或是字串，照字面一次也對不到（C2）；`isAsync` 也不行，Workflow 的派出沒有它（C1）。行為與 AC5 相同、只換辨認的欄位，Gate 1 要讓使用者看到這一條。**Found out when:** fixture 測試，下一次測試；Claude Code 改欄位要到發版後，那時退回 fa1a0e0 的行為（`stance.md:22`）。

##### D4 — AC6「派出紀錄落在檔尾之外照舊判做完」改成什麼？

選：照 V8 的兩個訊號並用，派出紀錄在檔尾之外、但一輪結束的計數大於 0 時，仍顯示「執行中（背景）」，只是列不出名稱（`stance.md:21`）；計數也說 0 時才判做完。配對只看這一列本來就讀的 262144 位元組，不另讀整份 transcript（`plugins/cai/scripts/viewer.py:1236`、`:1632`）。這是 AC6 字面行為的改變，約 5.0% 的背景子代理會碰到名稱消失（C8），寫進 detail 的已知限制；Gate 1 要讓使用者看到。**Found out when:** 發版後，那 5.0% 被使用者看到。

##### D5 — 「找不到 thread-writer-locks」那一行怎麼從快照帶到頁面？

選：快照頂層多一個布林欄位，頁尾多一行寫死的字、平時隱藏，由 `poll()` 依欄位切換；不改成「頁尾顯示 `problems`」。`problems` 裡是路徑與錯誤原文、今天沒顯示（C11），顯示它是沒人要的新功能；舊 detail 曾寫「頁尾顯示有 N 個來源讀不了」卻沒做（`docs/design/2026-09-25-agent-viewer-web-portal-detail.md:538`），仍不在本 track，寫在這裡讓它不被默默丟掉。**Found out when:** 頁面靜態測試，下一次測試；那一行真正出現要在沒有鎖檔目錄的機器上，發版後。

##### D6 — 鎖檔目錄存在卻列不出來（權限等）怎麼辦？

選：任何 `OSError` 都當成列不出來，不出 Codex 列；codex_home 存在就顯示頁尾那一行（C10、C12）。不另寫 `problems`：頁面不顯示它（C11），寫了也沒人看到；不拋出去：`Poller.run()` 會把整份快照換成上一份（`plugins/cai/scripts/viewer.py:2337-2343`），連 Claude 列都停住。字樣說「找不到」而實際是讀不了，但「無法判斷哪個 session 開著」仍是真的。**Found out when:** 發版後，某台機器的權限設定特殊時。

##### D7 — 退回路徑（sqlite 讀不了時）要找多遠的 rollout？

選：照舊只看 24 小時內修改過的 rollout、最多 200 個，但先以檔名最後 36 字元對鎖檔集合篩、再取 200 個（`plugins/cai/scripts/viewer.py:1664-1665`、`:2020-2034`、`:2046-2049`，C15）；不改成每個鎖檔 id 各做一次遞迴搜尋、不限時間。後者每 2 秒一次全樹掃描，只為 sqlite 壞掉又接續超過一天沒動的舊對話串、而且還沒送第一則訊息的那一段。**Found out when:** 發版後，sqlite 壞掉時才走得到。

##### D8 — 更新 plugin 後舊的 viewer server 還在跑，要不要逼它換新？

選：`/identity` 的 `format` 維持 1，改在 PR 說明寫「更新後先 `/cai:viewer stop` 再 `/cai:viewer`」。`format` 是 launcher 與 server 之間的協定版本，這次 `/identity`、`/shutdown`、狀態檔都沒變（C14）；拿它逼重啟，Claude 與 Codex 兩個 plugin 沒同時更新時，舊的那邊 launcher 只會印一行「a different viewer version is running」、不起新的（`plugins/cai/scripts/viewer.py:2440-2444`）。**Found out when:** 發版後，使用者更新了卻沒 stop，看到的還是舊行為。

#### Tier 3

| Decision | Chose | Instead of | Found out when |
|---|---|---|---|
| 「執行中（背景）」在快照怎麼表示 | `state` 仍是 `working`、`certainty` 是 `inferred`，列多一個布林欄位 `background`；頁面 `stateLabel` 看它換字樣。沿用「等你簽核」靠次要欄位換標籤（`plugins/cai/scripts/viewer.py:729-732`），排序、頂端「執行中」計數、不閃不響都自動成立（C13） | 第七個狀態值：要改釘住六個狀態的測試、`META`、頂端計數、`mode` 各一處 | 頁面與分類的 fixture 測試 |
| `background` 放哪些列 | `classify_claude` 的回傳一律帶（預設 `False`，照它「一律帶 question／permission／current」的慣例，`plugins/cai/scripts/viewer.py:1484-1490`）；Codex 列不帶，頁面把沒有當成 `false` | 每種列都補這個鍵 | fixture 測試 |
| `entryId` | `working:<statusUpdatedAt>`，與一般 `working` 同形；轉成 `done:<…>` 時照原規則響（C13） | `background:<…>` | fixture 測試 |
| 列上的計時 | 照 `working` 顯示「本輪 mm:ss」，起點是 `statusUpdatedAt`（`plugins/cai/scripts/viewer.py:818`、`:917`） | 新字樣「背景 mm:ss」：沒人選過的新文字 | verify 實看 |
| 「目前」那一格 | 照 #162：最新一個還在跑的背景派出（`plugins/cai/scripts/viewer.py:1549-1560`）；配對找不到就空著 | 另寫一行說明 | fixture 測試 |
| 配對找不到名稱時（接續、派出在檔尾外） | `subagents` 空清單、`current` 為 `None`，字樣照樣是「執行中（背景）」（`stance.md:21` 已接受，C4、C8） | 用計數猜名稱或顯示「N 個背景 agent」 | fixture 測試 |
| 待完成計數認哪些鍵 | 只認 `pendingBackgroundAgentCount`、`pendingWorkflowCount`（C5；萬用比對見 Ruled out） | 萬用比對 | fixture 測試 |
| `<status>` 的解析 | 照 #162 用 `str.partition` 取 `<task-id>`、`<status>`，status 在四種之內才算結束（C3） | 正規式 | fixture 測試 |
| 登記檔是 `shell` | 照舊判做完並加註，不做這道檢查（`stance.md` Out of scope 第一條） | 也檢查 | 既有測試 `tests/test_viewer_claude.py:206-210` |
| 哪些檔名算對話串 | 結尾 `.lock`、不以點開頭、去掉 `.lock` 後剛好 36 字元（C9） | 任何 `*.lock` | fixture 測試 |
| 鎖檔清單在哪裡讀 | `build_snapshot` 讀一次，交給 `codex_rows`，取代今天傳的兩個行程數（`plugins/cai/scripts/viewer.py:2257-2260`）；同一個值決定頁尾欄位 | `codex_rows` 自己讀，再多回傳一個旗標 | fixture 測試 |
| 主路徑的查詢 | `threads` 加 `id IN (<鎖檔 id>)`，其餘條件照舊，拿掉 `LIMIT 50` 與 `source` 欄（C15） | 照舊取最近 50 筆再篩：接續排在 50 筆之外的舊對話串會漏列 | fixture 測試 |
| 鎖檔清單是空的 | `codex_rows` 直接回空，不開 sqlite | 照樣查一次 | fixture 測試 |
| 頁尾欄位與元素的名字 | 快照鍵 `codexLockDirMissing`（照 `generatedAt` 的駝峰，`plugins/cai/scripts/viewer.py:2277`）；頁尾元素 id `codexLockNote`（照 `offlineNote`、`staleNote`，`:610`）；`EMPTY_SNAPSHOT` 不改，頁面把沒有這個鍵當成 `false` | 字串清單欄位 | 頁面靜態測試 |
| 那一行在頁尾的位置與樣式 | 頁尾第一行，沿用頁尾本身的灰字（`plugins/cai/scripts/viewer.py:584`） | 像「資料停在…」一樣的警示色（`:467`） | verify 實看 |
| 沒有呼叫者的程式 | 照 diagnosis 的 Blast radius 移除（`docs/design/2026-09-26-viewer-live-status-detail.md:564`，`plugins/cai/rules/coding.md:20`），連同只測它們的測試 | 留著不呼叫 | pytest |
| 版本 | ship 時對當時的 main 取號：cai 高於 main 的 `plugins/cai/.claude-plugin/plugin.json`（d514f6b 是 1.34.2），Codex 樹 `--release` 高於 `plugins/cai-codex/.codex-plugin/plugin.json`（0.2.20）；本 track 期間 main 已前進兩次 | 現在就寫死號碼 | `python scripts/validate.py` |


## 整併補充：viewer-live-status-diagnosis

來源為原 `2026-09-26-viewer-live-status-diagnosis.md`；以下僅保留上游背景或實作補充，現況以本檔維護說明為準。

#### Symptom

- 回報時（fa1a0e0）：在 `D:\project\day-trading-monarch` 開 Codex，頁面出現 `demo-auto-package-upgrade`（track `add-sub`）與兩個 `claude-all-in-one` 的 Codex 列；關掉 Codex 後仍有兩列（`post-merge-findings.md:7`）。沒有 TUI、只有兩個常駐 `codex.exe` 時每次重現（`probe/monitor-log.jsonl:2`、`:4`）。錯的 track 由舊對話串的 cwd 算出（`viewer.py:2274-2275`）。
- main 41cb6e1 上，「沒開 TUI 卻有列」這一條在本機不再重現：本輪唯讀檢查（2026-09-26，只呼叫 `viewer.py` 自己的唯讀函式）印出 `count_processes` 全部 2 個、`skip_app_server=True` 為 0，兩個執行檔都在 `~\.codex\packages\app-server-daemon\releases\0.157.1-x86_64-pc-windows-msvc\bin\codex.exe`，所以沒有推斷名額（`viewer.py:1996-1997`）。
- 仍會錯的（讀程式推得，沒有執行）：Codex 0.157.1 的 TUI 對話串來源欄是 `vscode`——本機三個 0.157.1 的 `codex-tui`／`user` 對話串（`ab565c7a30a7`、`7774f7995540`、`cffa03e1fc5e`，正是 `probe/findings.md:7`、`:9` 與 `probe/lock-watch.jsonl:2` 實測時開的 TUI）在資料庫（唯讀）與紀錄檔首行都是 `vscode`，0.155.0–0.156.1 的 14 個都是 `cli`；本機沒有裝 Codex 的 VS Code 擴充套件（`~/.vscode/extensions` 沒有名稱含 openai、codex、chatgpt 的目錄）。#162 把 `vscode` 當成擴充套件的對話串，永不推斷它開著（`viewer.py:1666-1671`、`:1999`、`:2062`），於是 TUI 這一輪做完後自己的列消失，名額給最近的 `cli` 對話串——本機是 0.156.1 的 `68eefa288dba`（claude-all-in-one），也就是回報的「開在 A 專案、列出 B 專案」。`tests/test_viewer_codex.py:419-426` 目前以綠燈守著這個結果。

#### Failing test

建置時第一件事寫進 `tests/test_viewer_codex.py` 的三個測試。本文件只描述，不寫程式；「現在」都是讀程式推得，沒有執行過。

共同設定：`tmp_path` 當 codex_home，用 `_write_rollout`、`_make_state_db(..., sources=...)`、`_make_history_db`（`tests/test_viewer_codex.py:72-123`）造對話串，turn 都是 `completed`；`thread-writer-locks/` 放 `.coordination.lock` 與測試指定的空白 `<id>.lock`；Claude 的 config root 是空目錄；`monkeypatch.setattr(viewer, "count_processes", lambda name, skip_app_server=False: 1 if skip_app_server else 3, raising=False)`，即一個 TUI 加兩個常駐服務（同 `tests/test_viewer_http.py:41-42`）。`raising=False` 是因為修正會移除 `count_processes`，之後這個替身不再被讀、測試照樣成立。呼叫 `viewer.build_snapshot`，只看 `platform == "codex"` 的列。

1. `test_build_snapshot_lists_the_locked_thread_whatever_its_source`：較舊的 `cli` 對話串（別的專案、沒鎖檔）與較新的 `vscode` 對話串（有鎖檔）。斷言：只有較新那一列。現在：只有較舊那一列——名額 1（`viewer.py:1996`），`vscode` 被跳過（`:1999`），補上較舊的（`:2001`）。TUI 行程若其實沒被數成 1，現在是 0 列，一樣失敗。
2. `test_build_snapshot_lists_no_codex_row_before_the_first_message`：一個 `cli` 對話串（沒鎖檔），鎖檔目錄另有一個 id 不在 `threads` 的 `<id>.lock`（還沒送訊息的 TUI，`probe/findings.md:8`）。斷言：0 列。現在：1 列，那個 `cli` 對話串補進名額。
3. `test_build_snapshot_lists_only_the_resumed_older_thread`：兩個 `cli` 對話串，只有較舊那個有鎖檔（用 TUI 接續舊對話串，`probe/findings.md:9`）。斷言：只有較舊那一列。現在：較新那一列（`:1998` 由新到舊補）。

測的承諾：舊 stance 的 UC3「一個主 session 一列……已結束的幾秒內消失」（`docs/design/2026-09-25-agent-viewer-web-portal-detail.md:970`）——測試 1 是開著的沒列、結束的列著，2 與 3 是結束的列著。既有測試直接把數字傳給 `codex_rows`（例如 `tests/test_viewer_codex.py:415`、`:424`），看不到哪個對話串真的開著，所以一直是綠的。

#### Root cause

Codex 列的存活仍是「數行程，再照屬性與最近更新挑對話串」（D6 與 #162 的修正，`docs/design/2026-09-25-agent-viewer-web-portal-detail.md:797-797`、`-detail.md:535`）：一個數字只回答開著幾個，不回答開著哪幾個。#162 把數字修對了，挑的那一步仍在猜。

- 數字：`count_processes`（`viewer.py:299-305`；Windows `:193-215`，Linux `:259-284`）。#162 以執行檔路徑或命令列含 `app-server` 扣掉常駐服務（`:76-82`、`:207-208`、`:271-280`）；本機實測有效（上面 2 → 0）。
- 挑哪幾個：主路徑先放所有 `inProgress`、再依 `updated_at_ms` 由新到舊補滿名額並跳過 `vscode`（`viewer.py:1990-2005`）；退回路徑同一套（`:2059-2062`）。跳過 `vscode` 依據的是「`vscode` 是擴充套件、沒有自己的行程」（`:1666-1671`），在 0.157.1 不成立（Symptom 第三條）。

**修掉那一行之後還會成立什麼？** 拿掉 `vscode` 那條，測試 2 與 3 照樣失敗：由新到舊補名額挑到的不是開著的那個。就算數字完全正確也一樣。另一條路：`inProgress` 的對話串不限數量全列、標「存活：確定」，只要任何 `codex.exe` 在跑（`:1990-1993`、`:2080-2081`），而常駐服務一直在，崩潰後卡在 `inProgress` 的對話串就一直掛著（沒實際看過）。原因在 D6 的「以數量推名單」，#162 沒有動它。

每個對話串自己的訊號是鎖檔（2026-09-26 實機，Codex 0.157.1，Windows）：每個開著的 TUI 各有一個、檔名就是對話串 id（`probe/monitor-log.jsonl:36-50` 的鎖檔名與同時段 `threads` 的 id 相同）；上面三個來源欄是 `vscode` 的 TUI 對話串都有鎖檔（`monitor-log.jsonl:36`、`:42`、`:70`），所以來源欄不影響這條規則；接續舊對話串沿用同一個檔名（`probe/findings.md:9`）；還沒送訊息的 TUI 另有一個暫時 id 的鎖檔，資料庫裡從沒有這個 id（`findings.md:8`）；TUI `/quit` 後鎖檔仍在、仍被握著，約 30 秒到 1 分鐘後才被刪（`probe/lock-watch.jsonl:2-3`，離開時間在 00:45:22–00:45:50 之間，`intake.md:46`）。握著它的是比 TUI 活得久的行程；說是常駐服務是排除法，不是量到的。鎖檔目錄沒有查 Codex 官方文件：UNVERIFIED；它若在某一版消失，下面的修法讓 Codex 列全部不見並在頁尾說明（使用者 2026-09-26 的選擇，`options-intake-nolock.md:15-21`）。

#### Fix

- Codex 的存活只看 `<codex_home>/thread-writer-locks/` 的檔名清單：`<36 字元 id>.lock` 的 id 集合就是「開著的對話串」；點開頭的檔（`.coordination.lock`）不算；只列目錄，不開啟任何鎖檔（AC3）。codex_home 照舊由 `CODEX_HOME` 或 `~/.codex` 決定（`viewer.py:2209-2211`）。
- 主路徑：`threads` 查「id 在鎖檔集合裡」且照舊 `archived = 0`、`codex-tui`、`user`，不再取最近 50 筆、不看來源欄；每個查到的對話串一列，`aliveCertainty` 一律 `inferred`（使用者 2026-09-26，`intake.md:48`）；`inProgress` 與分類規則不變（AC2）。暫時 id 的鎖檔查不到列，自然不成列。
- 退回路徑：同一個 id 集合，對到 rollout 檔名結尾的 id，照舊用 `session_meta` 的 `originator`、`thread_source` 過濾；全部標推斷（照舊）。
- 鎖檔目錄不存在：不出 Codex 列，頁尾顯示一行「Codex：找不到 thread-writer-locks，無法判斷哪個 session 開著」（`options-intake-nolock.md:6`）。頁面至今不顯示快照的 `problems`（頁尾是固定文字，`viewer.py:640-647`；`problems` 只出現在伺服器端，`:1139` 以後），所以這一行要有顯示的地方，怎麼顯示留給 detail。只在 codex_home 存在、裡面沒有 `thread-writer-locks` 時顯示；沒裝 Codex 時頁尾不提 Codex（使用者 2026-09-26 選「只在有裝 Codex 時說明 (Recommended)」，`.claude/track/viewer-live-status-fixes/options-design-footer.md`）。
- Blast radius 列為移除的程式與只測它們的測試一併移除。

#### Invariants preserved

- 舊 stance 的 V1（只列目錄、不開鎖檔、sqlite 唯讀）、V2（不送 signal；修正後連 Codex 的行程列舉都不做）、V4（Codex 列一律標「存活：推斷」）、V5（只用 stdlib 的 `os.listdir`）照舊成立（`docs/design/2026-09-25-agent-viewer-web-portal-detail.md:991-995`）；由 fixture 測試與既有的寫入邊界測試守（`-detail.md:751`）。
- 放寬的只有一條，是使用者的決定：UC3 對 Codex 列從「幾秒內消失」改為「TUI 關掉後約一分鐘內消失」（`options-intake-lockdelay.md:15-21`；`intake.md:48`），寫在 `docs/design/2026-09-26-viewer-live-status-detail.md` 的 UC3。
- 怎麼知道沒弄壞：上面三個測試加退回路徑與目錄不存在各一個 fixture 測試；`python scripts/validate.py` 與 `python -m pytest` 全綠；verify 實機開關一次 Codex TUI（AC7、AC8）。


## 整併補充：viewer-live-status-stance

來源為原 `2026-09-26-viewer-live-status-stance.md`；以下僅保留上游背景或實作補充，現況以本檔維護說明為準。

#### Optimises for

頁面說「完成，等指示」或列出一個 Codex session 時，背後都有那個 session 自己留下的直接證據：Claude 列在背景子代理都結束之前不說做完，而且分得出「這一輪還在跑」與「只剩背景在跑」；Codex 列只列 Codex 自己掛著鎖檔的對話串。判準：AC1–AC6 每種情況一個 fixture 測試，加 AC8 的實機一次。

#### Sacrifices

- Codex 列在 TUI 關掉後約一分鐘才消失，而不是舊 stance UC3 的幾秒，也不是 main 現在的約 2 秒（使用者 2026-09-26 選，`options-intake-lockdelay.md:15-21`、`options-design-main162.md:18-21`）；強制關閉視窗的那一次量到殘留數分鐘（`probe/findings.md:7`），還沒確認。
- Codex 列的存活一律是推斷，連本輪進行中（`inProgress`）的也是；main 把它們全列並標確定（`viewer.py:1990-1993`、`:2005`）。
- 沒有鎖檔目錄的環境——Linux、macOS、較舊的 Codex，都沒查過——看不到任何 Codex 列，只有頁尾一行（`options-intake-nolock.md:15-21`）；還沒送第一則訊息的 Codex TUI 照舊看不到（`intake.md:42`）。
- 背景 shell 在跑時照舊顯示「完成，等指示」並加註（`options-intake-bg.md:19-25`）。
- 背景子代理若一直沒有結束通知，那一行就一直是「執行中（背景）」，蓋掉真的做完。以 SendMessage 接續的子代理、或派出紀錄落在 256 KiB 檔尾之外（AC6）時，那一行仍靠待完成計數顯示「執行中（背景）」，但列不出子代理名稱：配對只認派出紀錄（`viewer.py:1416-1417`），接續不留派出紀錄（下面 V8 的證據）。
- 多讀兩種平台內部紀錄（`queue-operation` 與 `turn_duration` 的待完成計數），格式都沒有文件（舊 stance 的第一條犧牲，`stance.md:15`）；格式一改，這一行退回 fa1a0e0 的行為。

#### Invariants

**This system's:**

- 舊 stance 的 V1–V7 全部照舊（`docs/design/2026-09-25-agent-viewer-web-portal-detail.md:991-997`）。
- V8 — 有沒有背景子代理（含 Workflow）在跑，只看對話紀錄：檔尾那筆一輪結束的待完成計數大於 0，或有派出、沒有它的結束通知（completed、failed、killed、stopped 之一）；背景 shell 不算。登記檔的 `status` 只決定要不要做這道檢查（`idle`，或 `busy` 而檔尾最後是一輪結束），不拿來判斷有沒有背景工作。主 session 這一輪已結束、只剩背景工作時，那一行是「執行中（背景）」、確定度「推斷」、不閃不響，列出配對得到的子代理名稱（使用者 2026-09-26，`options-intake-bg.md:19-22`、`options-design-bglabel.md:15-21`；AC5）。兩個訊號並用是使用者選的「判斷方式沿用 #162」（`options-design-bglabel.md:16`，#162 在 `viewer.py:1474-1480`、`:1540-1543`）；本機 1796 份 transcript 裡，1025 筆計數大於 0 的一輪結束有 188 筆配對找不到在跑的子代理，看過的兩個例子都是 SendMessage 接續（其一：`~/.claude/projects/D--project-claude-all-in-one/2162ccb5-c60c-447a-9112-ce3620300e7b.jsonl:231`、`:241-242`）；反過來「配對有、計數為 0」一筆都沒有（本輪唯讀掃描）。
- V9 — Codex 的存活只看鎖檔目錄裡的檔名：不數行程、不開啟鎖檔、不看 rollout 修改時間（使用者 2026-09-26，`options-intake-nolock.md:15-18`、`options-design-main162.md:30-31`；AC1、AC3）。

**Cross-project:**

- 舊 stance 的 Cross-project 四條照舊（`docs/design/2026-09-25-agent-viewer-web-portal-detail.md:1001-1004`）。

#### Rejected stances

- **連背景 shell 也算數。** 看得到背景還在跑的每一件事，但開發伺服器這類永不結束的指令會讓那一行永遠「執行中」；輸在「只憑會結束的證據說還在跑」（使用者否決，`options-intake-bg.md:27-33`）。
- **沒有鎖檔目錄就退回數行程。** Linux 與 macOS 也看得到 Codex 列，但錯的列會回來，正是要修的問題（使用者否決，`options-intake-nolock.md:23-29`）。
- **鎖檔加「有 TUI 行程在跑」，以及同一家族的 #162「數 `codex.exe`、扣掉路徑含 `app-server` 的」。** 關掉後立刻消失，但要靠常駐服務的安裝路徑辨認它，Codex 更新就可能壞（使用者否決，`options-intake-lockdelay.md:23-29`）；#162 另外仍以數量推名單（diagnosis 的 Root cause）。使用者選接到 main、把它換成只看鎖檔，不照 #162 收掉這條 track（`options-design-main162.md:38-44`）。
- **照 #162 顯示「執行中 · 確定」。** 不必改問題 2 的程式，但這一輪還在跑（要先中斷）和只在等背景（可以直接打字）看起來一樣（使用者否決，`options-design-bglabel.md:23-29`）。
- **讓登記檔告訴我們有沒有背景工作。** 不必讀檔尾，但它分不出來：背景子代理在跑的十幾分鐘裡登記檔一直是 `busy`（`.claude/track/viewer-live-status-fixes/probe/registry-bg.jsonl:3`），和一輪還在進行時同一個值。

#### Out of scope

- 背景 shell 的配對（`options-intake-bg.md`）；登記檔是 `shell` 時照舊判做完並加註，不做這道檢查（AC5 只列 `idle` 與 `busy`）。
- 過時 busy 規則的 60 秒門檻與「登記檔可能過時」照 #162（`viewer.py:1540-1547`，`docs/design/2026-09-25-agent-viewer-web-portal-detail.md:950`）不改；verify 若看到 `busy`、檔尾沒有背景工作卻被判做完的列，再回來處理。
- 還沒送第一則訊息的 Codex TUI、Codex 等權限的 30 秒推斷、舊 track 其餘 Minor（`intake.md:42`）。
- 留給 decisions，證據已找到：派出的標記是 `toolUseResult` 的 `{"isAsync":true,"status":"async_launched","agentId":…}`，Agent 呼叫都沒有 `run_in_background`（`~/.claude/projects/D--project-claude-all-in-one/a8af33f2-a42d-4e02-b0d5-10d322d5ac2b.jsonl:100-101`，該檔每個 `"run_in_background":true` 都在 Bash 呼叫上，如 `:146`）；結束通知同時帶 `<task-id>` 與 `<tool-use-id>`（同檔 `:108`）；SendMessage 接續後同一個子代理 id 再來一次通知（`~/.claude/projects/D--project-day-trading-monarch-3/402ed4d7-e8c2-4eee-afec-1b47cdf054ec.jsonl:1043-1044`、`:1067`、`:1131-1132`、`:1160`）。其餘：#162 以 `pending*Count` 萬用比對任何計數（`viewer.py:1478-1480`），V8 只認子代理與 Workflow 兩種，將來多一種（例如背景 shell 的）要不要算；頁尾那一行怎麼顯示（頁面至今不顯示 `problems`，`viewer.py:640-647`）；「執行中（背景）」在快照裡的欄位與命名。
- `docs/` 被 git 忽略；本檔要進 PR 需在 ship 時 `git add -f`。
