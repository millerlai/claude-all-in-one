# agent-viewer-language-switch — detail design

## 維護說明（2026-10-27）

本檔是歷史設計紀錄，保留決策、驗收依據與實作偏差；不是待執行計畫。原簽核狀態、版本、行號及未驗證標記描述撰寫當時，整併不代表重新簽核或重做實測。

名詞：設計立場（stance）說明取捨；決策紀錄（decisions）保存選擇理由；細部設計（detail）記錄建造規格；需求盤點（intake）保存驗收條件。下方英文標題與識別碼沿用原文，便於對照歷史。

語言切換的獨立設計與取捨保留，實作見 [`plugins/cai/scripts/viewer.py:294`](../../plugins/cai/scripts/viewer.py#L294)。它與入口頁及存活狀態修正的需求不同，因此各保留一份細部設計。

已併入並移除的同主題文件：`2026-09-26-agent-viewer-language-switch-decisions.md`、`2026-09-26-agent-viewer-language-switch-stance.md`。

補充段落保留原文與原決策編號，避免把不同時點同號的決策當成一項；重複的概覽圖、施工排程與階段交接文字不再複製。

## Reference

Stance doc: docs/design/2026-09-26-agent-viewer-language-switch-detail.md
Decisions doc: docs/design/2026-09-26-agent-viewer-language-switch-detail.md
Status: approved 2026-09-26（stance）；decisions 的 Tier 1 零項，沒有待答的 `Decided:`；decisions 本身隨 Gate 1 一起簽。

照 decisions 的 D1–D3 與 Tier 3 全部條目執行，不再重述。下文行號一律是 `plugins/cai/scripts/viewer.py` 在分支起點（`aabb2e1`）的行號，簡寫為 `viewer.py:<n>`。

### Traceability

| From the referenced document | Satisfied by | Status |
|---|---|---|
| UC1 首次打開整頁英文 | `### 語言偏好` 的 `langPref` 預設 `en`、`<html lang="en">`；`### 字串表` 的 en 欄；`### 各處改寫` 換掉每段寫死的中文 | covered |
| UC2 頁首切換、不重新載入、狀態保留 | `### 語言偏好` 的 `#langSeg` 與 `applyLang()`；`render()` 簽名加 `langPref` | covered |
| UC3 重開沿用、首次繪製前讀出 | `### 語言偏好` 的 head 腳本片段與 `LANG_KEY` | covered |
| UC4 繁體中文逐字不變 | `### 字串表` 的 zh-Hant 欄逐字搬自原行；頁尾三句拆鍵保留原空白；`## Verification` 的一次性比對 | covered |
| UC5 server 的兩句備註依語言顯示 | `### server：noteCodes`；attention 分支先查代碼再接原文 | covered |
| UC6 原 UC1–UC6 照舊、驗證全綠、Codex 重產、版本 1.37.0 | `### 出貨`；`## Work breakdown` 單元 3 | covered |
| R1 `PAGE_HTML` 寫死繁中 | 同 UC1、UC4 | covered |
| R2 原 detail:114「照 mockup 用中文」被取代 | `## Design decisions` 第一條記下取代；launcher 仍印 ASCII 英文不變 | covered |

## Requirement

Agent Viewer 的網頁今天只有繁體中文（`viewer.py:285`，介面文字散在 `:503-940`）。改成：沒存偏好時整頁英文，頁首有「English／繁體中文」切換，選擇存在瀏覽器、下次沿用；繁體中文模式與今天逐字相同；server 自己寫、會上頁面的備註改送代碼由頁面翻譯，平台原文照原樣。怎麼知道做對了：intake 的 AC1–AC7（intake.md:16-22），逐條對到 `## Verification`。

## Glossary

| Term | Definition | Where it lives |
|---|---|---|
| 字串表 | 頁面內每種語言一個、鍵完全相同的 JSON 相容物件字面值，值是該語言的介面文字 | new — plugins/cai/scripts/viewer.py（主 `<script>` 開頭） |
| 鍵 | 字串表裡一段介面文字的名字，例如 `state.working` | new — plugins/cai/scripts/viewer.py（字串表） |
| 佔位 | 字串值裡以大括號包住的參數名，例如 `{n}`，由 `tr()` 換成實際值 | new — plugins/cai/scripts/viewer.py（`tr()`） |
| `tr()` | 以目前語言查鍵、代入佔位、回傳字串的函式 | new — plugins/cai/scripts/viewer.py（字串表之後） |
| `langPref` | 目前語言，只會是 `en` 或 `zh-Hant` | new — plugins/cai/scripts/viewer.py（字串表之後） |
| `applyLang()` | 依 `langPref` 重寫所有靜態文字與幾個由狀態決定的標籤 | new — plugins/cai/scripts/viewer.py（主題區段之後） |
| 靜態元素 | HTML 裡帶 `data-i18n*` 屬性、文字由 `applyLang()` 填入的元素 | new — plugins/cai/scripts/viewer.py（`<body>`） |
| 語言切換鈕 | 頁首 `#langSeg`，兩個按鈕「English」「繁體中文」 | new — plugins/cai/scripts/viewer.py（主題切換之後） |
| head 腳本 | `<head>` 內在首次繪製前執行的內嵌腳本，今天只定主題 | plugins/cai/scripts/viewer.py:290 |
| 簽名 | `render()` 判斷一列要不要重畫所比對的字串 | plugins/cai/scripts/viewer.py:759 |
| `notes` | 列上的平台原文陣列（改完後只放原文） | plugins/cai/scripts/viewer.py:1565 |
| `noteCodes` | 列上的新欄位，server 自己的備註，每項一個代碼 | new — plugins/cai/scripts/viewer.py（`classify_claude`、`classify_codex`） |
| 代碼 | 與語言無關、頁面拿去查表的短字串，例如 `reason-unknown` | concept |
| 原文 | 平台或使用者寫的字，頁面照原樣顯示、不查表（L3） | concept |
| attention 方框 | attention 列活動欄裡顯示備註的方框，今天唯一顯示 `notes` 的地方 | plugins/cai/scripts/viewer.py:690 |
| `aliveCertainty` | 列上「存活」的確定度，頁面據此顯示身分欄的「存活：推斷」 | plugins/cai/scripts/viewer.py:1721 |
| `format` | launcher 與 server 之間的協定版本（本次不改，D3） | plugins/cai/scripts/viewer.py:1039 |
| CJK | 中日韓文字與其標點、全形字元，範圍見 `### 測試` | concept |
| gen-codex 改寫 | 產生 Codex 樹時對每個檔做的字面替換 | scripts/gen-codex.py:277 |
| `DENY_LIST` | Codex 樹裡不得出現的字串清單 | scripts/gen-codex.py:129 |

## Budgets

| What | Number | Where it comes from |
|---|---|---|
| 字串表的鍵數（每種語言） | 64 | `### 字串表` 逐列計數 |
| 新增的 localStorage 鍵 | 1 | `agent-viewer-lang`；L4 |
| 新增的網路請求、檔案、字型 | 0 | L6；CSP 不改（`viewer.py:275`） |
| 切換語言時的重新載入 | 0 | AC2 |
| 新增的第三方套件 | 0 | AC7 |
| CJK 檢查涵蓋的 Unicode 區段 | 9 | `### 測試` |
| zh-Hant 表以外允許的 CJK 字串 | 1 | 切換鈕上的「繁體中文」（L1，stance 核准時的例外） |
| 輪詢間隔（不變） | 1000 ms | `viewer.py:947` |
| toast 顯示時間（不變，切換時不重寫） | 2200 ms | `viewer.py:816` |
| cai 版本 | 1.37.0 | intake AC7 |
| cai-codex `--release` 版本的下限（須大於） | 0.2.28 | `plugins/cai-codex/.codex-plugin/plugin.json:3` |

## Design decisions

這一層新出現、decisions 沒有的決定：

- **R2：原 detail:114「頁面是 UTF-8 的 HTML，照 mockup 用中文」由本設計取代。** 同一條的「launcher 印英文、只用 ASCII」不變，launcher 一行都不改。服務 UC1。
- **頁尾那段三行的說明拆成三個鍵，HTML 裡保留原本的換行與縮排。** 今天那三行（`viewer.py:531-533`）之間的換行在畫面上摺成空白；三個 `<span>` 之間留著同樣的換行，zh-Hant 顯示的空白就與今天完全一樣，不必在值裡放換行或反斜線（C7）。服務 UC4。
- **中文相同、角色相同的地方共用一個鍵。** 狀態標籤「等你核准權限」與權限方框第一行（`viewer.py:625`、`:683`）共用 `state.permission`；「執行中」的狀態與頂端計數（`:630`、`:788`）共用 `state.working`；「需要你」的篩選與計數（`:521`、`:787`）共用 `common.needsYou`；身分欄與備註的「存活：推斷」（`:711`、`:1708`）共用 `note.alive-inferred`。中文相同才共用，所以 zh-Hant 不變；英文因此也只有一種說法。
- **空列表的提示在切換時要改字。** `render()` 今天只在沒有提示時插入（`viewer.py:773-775`），已插入的提示切換後會留在舊語言；改成已存在時重寫它的文字。服務 UC2。
- **`applyLang()` 只在腳本最後與切換時呼叫，不在定義處呼叫。** 它會讀 `soundOn`（`:595`）與 `failCount`（`:845`），兩者是 `let`，在宣告之前讀會丟 ReferenceError。服務 UC1、UC2。
- **`clock` 改成函式宣告，參數改名 `ms`。** 今天的參數叫 `t`（`:616`）；改名避免讀的人以為它是查表。英文分支用 `pad()`（`:604`）組 `HH:MM:SS`。

## Diagrams

### Architecture

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart LR
  subgraph BR["瀏覽器"]
    LS["localStorage：agent-viewer-lang"]:::added
    HEAD["head 腳本：主題與語言，設 html lang"]:::modified
    TBL["STRINGS_EN 與 STRINGS_ZH_HANT"]:::added
    TR["tr(key, params)"]:::added
    AL["applyLang()：靜態元素、聲音鈕、離線徽章"]:::added
    REN["render、summary、tick、toast"]:::modified
    SEG["語言切換鈕 langSeg"]:::added
  end
  subgraph SV["server：viewer.py"]
    CC["classify_claude 與 claude_rows"]:::modified
    CX["classify_codex"]:::modified
    API["GET /api/rows：notes 原文、noteCodes 代碼"]:::modified
    PG["GET /：PAGE_HTML"]:::modified
  end
  PG -- "一次" --> HEAD
  LS --> HEAD
  SEG --> LS
  SEG --> AL
  TBL --> TR
  TR --> AL
  TR --> REN
  CC --> API
  CX --> API
  API -- "每秒" --> REN
  classDef added fill:#d4edda,stroke:#28a745,color:#155724
  classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404
  classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057
```

看哪裡：server 到瀏覽器只有兩條線（頁面一次、列每秒一次），沒有任何線從語言鍵或切換鈕回到 server（L2）。綠框全在瀏覽器；server 那側黃框改的只是列上多一個 `noteCodes`。

### Component

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TB
  ROW["列 JSON：notes 為原文陣列，noteCodes 為代碼陣列"]:::modified
  ACT["activityHTML 的 attention 分支"]:::modified
  TR["tr(key, params) 回傳字串"]:::added
  TBL["STRINGS[langPref][key]"]:::added
  PREF["langPref：en 或 zh-Hant"]:::added
  SIG["render 簽名：列、已讀、展開、langPref"]:::modified
  OUT["esc() 後寫入 HTML"]:::existing
  ROW --> ACT
  ACT -- "note. 加代碼" --> TR
  ACT -- "原文不查表" --> OUT
  TR --> TBL
  PREF --> TBL
  PREF --> SIG
  TR --> OUT
```

看哪裡：attention 分支出去有兩條路，只有代碼那條經過 `tr()`，原文那條直接到 `esc()`（L3）。`langPref` 同時接到字串表與簽名——少了簽名那條，切換後已畫好的列不會重畫（C6）。

### Flow

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TD
  A["收到 PAGE_HTML，html lang 為 en"]:::modified --> B{"head 腳本：語言鍵是 zh-Hant？"}
  B -- "是" --> C["html lang 改為 zh-Hant"]:::added
  B -- "否、沒存或讀不到" --> E
  C --> E["解析 body：靜態元素只帶鍵名，沒有文字"]:::modified
  E --> F["主腳本：讀 langPref，非 zh-Hant 一律 en"]:::added
  F --> G["applyLang()：填靜態文字、聲音鈕、離線徽章"]:::added
  G --> H["render()：列、計數、分頁標題、相對時間"]:::modified
  H --> I{"按了切換鈕？"}
  I -- "是" --> J["langPref 改值，寫入 localStorage"]:::added
  J --> G
  I -- "否" --> K["每秒 poll 與 tick"]:::existing
  K --> H
  classDef added fill:#d4edda,stroke:#28a745,color:#155724
  classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404
  classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057
```

看哪裡：切換鈕的迴圈回到 `applyLang()`，不回到「收到 PAGE_HTML」——沒有重新載入（AC2）。head 腳本只決定 `lang`，文字一律由主腳本的 `applyLang()` 填（L1：一個出處）。

### Sequence — UC1 與 UC3（打開或重開頁面）

```mermaid
sequenceDiagram
  participant U as 使用者
  participant B as 瀏覽器
  participant L as localStorage
  participant S as viewer server
  U->>B: 打開 127.0.0.1 的網址
  B->>S: GET /
  S-->>B: PAGE_HTML，html lang 為 en
  B->>L: head 腳本讀 agent-viewer-lang
  L-->>B: 沒有、en 或 zh-Hant
  B->>B: 是 zh-Hant 才改 html lang
  B->>L: 主腳本再讀一次，定 langPref
  B->>B: applyLang() 然後 render()
  B->>S: GET /api/rows
  S-->>B: 列，含 notes 與 noteCodes
  B->>B: render()：代碼查表，原文照原樣
```

看哪裡：語言讀了兩次（head 腳本一次、主腳本一次），比照主題（`viewer.py:293`、`:557`）；兩次之間沒有任何請求帶著語言出去。

### Sequence — UC2（切換語言）

```mermaid
sequenceDiagram
  participant U as 使用者
  participant G as 語言切換鈕
  participant J as 主腳本
  participant L as localStorage
  U->>G: 按「繁體中文」
  G->>J: click，data-lang-pref 為 zh-Hant
  J->>J: langPref 設為 zh-Hant
  J->>L: setItem agent-viewer-lang
  J->>J: applyLang()：html lang、靜態文字、聲音鈕、離線徽章
  J->>J: render()：簽名含 langPref，每列重畫
  J->>J: summary() 與 tick()：計數、分頁標題、相對時間
```

看哪裡：`filter`、`acks`、`expanded` 三個集合沒有出現在這張圖上——切換不碰它們，所以篩選、已讀、展開都保留（AC2）。

### Sequence — UC5（server 的備註）

```mermaid
sequenceDiagram
  participant R as Claude 登記檔
  participant C as claude_rows 與 classify_claude
  participant A as GET /api/rows
  participant P as 頁面
  R-->>C: status 為 waiting，沒有 waitingFor，存活未驗證
  C->>C: notes 為空，noteCodes 為 alive-inferred、reason-unknown
  C->>A: 列
  P->>A: 每秒輪詢
  A-->>P: 列
  P->>P: 兩個代碼各自查表，再接 notes 原文，以 list.separator 接起
```

看哪裡：server 送出的列裡沒有任何一種語言的字；zh-Hant 下接起來是「存活：推斷、原因未知」，與今天 `viewer.py:1708`、`:1715`、`:1585`、`:691` 組出的字相同。

UC4（逐字不變）與 UC6（原有用例照舊）沒有新的呼叫順序可畫：UC4 是字串表的內容，UC6 是既有行為不變，兩者都由 `## Verification` 的檢查涵蓋。

## Implementation spec

### 字串表

- **Responsibility:** 頁面上每段會隨語言變的文字，只在這裡寫一次。
- **Interface:** 主 `<script>`（`viewer.py:540`）開頭三個常數：`const STRINGS_EN = {...};`、`const STRINGS_ZH_HANT = {...};`、`const STRINGS = {'en': STRINGS_EN, 'zh-Hant': STRINGS_ZH_HANT};`。前兩個各自從 `{` 開頭、以單獨一行的 `};` 結尾，中間是嚴格的 JSON（雙引號鍵、無尾逗號、無註解），供測試以 `json.loads` 解析。
- **Data:** 鍵 → 字串，64 個鍵，兩表相同。值不得含反斜線或 ASCII 雙引號（C7；要引號用 `“ ”`）。只有 `footer.terminal` 的值可含 HTML（`<b>`）。
- **Errors:** 無執行期錯誤路徑；鍵不齊或 JSON 壞由 pytest 擋。
- **Concurrency:** 常數，不變動。
- **Observability:** 無。
- **Where it lives:** `plugins/cai/scripts/viewer.py`，主 `<script>` 開頭（存在的檔案）。
- **What it reuses:** 無。

### 字串表內容

en 為本設計的提案，Gate 1 一起看；zh-Hant 是今天的字，逐字搬過來。「取代」指它換掉的 `viewer.py` 行。

| 鍵 | en | zh-Hant | 取代 |
|---|---|---|---|
| `lang.aria` | `Language` | `語言` | 新增（切換鈕群組的 `aria-label`） |
| `theme.aria` | `Theme` | `主題` | :503 |
| `theme.system.title` | `Follow the operating system setting` | `跟隨作業系統設定` | :504 的 `title` |
| `theme.system` | `◐ System` | `◐ 系統` | :504 |
| `theme.dark` | `☾ Dark` | `☾ 深色` | :505 |
| `theme.light` | `☀ Light` | `☀ 淺色` | :506 |
| `sound.on` | `🔔 Sound: on` | `🔔 聲音：開` | :508、:934 |
| `sound.off` | `🔕 Sound: off` | `🔕 聲音：關` | :934 |
| `chime.done` | `Also chime when done` | `完成時也響` | :509 |
| `chime.inferred` | `Also chime for inferred permission waits` | `推斷的等權限也響` | :510 |
| `unlock.text` | `Browsers only let a page play sound after it has been clicked once →` | `瀏覽器規定頁面要先被點過一次才能發出聲音 →` | :515 |
| `unlock.button` | `Enable chimes (plays one now so you can hear it)` | `啟用提示音（會先響一次給你聽）` | :516 |
| `filter.all` | `All` | `全部` | :520 |
| `common.needsYou` | `Needs you` | `需要你` | :521、:787 |
| `filter.plain` | `Other agents` | `一般 agent` | :523 |
| `footer.codexLock` | `Codex: thread-writer-locks not found, so it cannot tell which sessions are open` | `Codex：找不到 thread-writer-locks，無法判斷哪個 session 開著` | :529 |
| `footer.terminal` | `Answering questions, approving permissions and signing off still happen in the terminal; this page only lets you <b>see</b> who is waiting for you.` | `回答問題、核准權限、簽核仍然在終端機做；這一頁只負責讓你<b>看見</b>誰在等你。` | :530 |
| `footer.inference1` | `One list shows the main sessions of both Claude Code and Codex. “Maybe waiting for permission” appears only on Codex rows and is inferred:` | `同一張表列出 Claude Code 與 Codex 的主 session。「可能在等權限」只出現在 Codex 的列上，是推斷出來的：` | :531 |
| `footer.inference2` | `a tool call with no result after 30 seconds counts, so a call that is merely slow looks the same;` | `一次工具呼叫超過 30 秒還沒有結果就算，只是跑得比較久的呼叫看起來會一樣；` | :532 |
| `footer.inference3` | `Claude's “Waiting for permission” is read from its own session registry file, so it is confirmed, not inferred.` | `Claude 的「等你核准權限」是從它自己的登記檔讀到的，是確定，不是推斷。` | :533 |
| `footer.order` | `Order: rows that need you first (longest wait first) → running. Press “Seen” to stop the flashing; it lights up again when the state changes.` | `排序：需要你的在最上面（等最久的優先）→ 執行中。按「已讀」停止閃爍，狀態再變時會重新亮起。` | :534 |
| `footer.theme` | `Your theme choice is kept in this browser and used next time.` | `主題選擇記在這個瀏覽器裡，下次打開沿用。` | :535 |
| `dur.seconds` | `{n} s` | `{n} 秒` | :612 |
| `dur.minutes` | `{n} min` | `{n} 分鐘` | :613 |
| `dur.hoursMinutes` | `{h} h {m} min` | `{h} 小時 {m} 分` | :614 |
| `state.gate` | `Waiting for your sign-off` | `等你簽核` | :620 |
| `state.question` | `Waiting for your answer` | `等你回答` | :621 |
| `state.permission` | `Waiting for permission` | `等你核准權限` | :625、:683 |
| `state.permissionInferred` | `Maybe waiting for permission` | `可能在等權限` | :626 |
| `state.attention` | `Needs your attention` | `等你處理` | :628 |
| `state.done` | `Done, awaiting instructions` | `完成，等指示` | :629 |
| `state.working` | `Running` | `執行中` | :630、:788 |
| `state.workingBackground` | `Running (background)` | `執行中（背景）` | :630 |
| `state.unknown` | `Unknown` | `未知` | :631 |
| `gate.title` | `Human gate` | `人工閘門` | :643 |
| `now.recent` | `Just now:` | `剛剛：` | :662 |
| `now.subagents` | `subagents:` | `subagents：` | :663 |
| `question.hint` | `Answer in the terminal · this page only shows, it never answers for you` | `回終端機作答 · 這一頁只顯示，不代答` | :679 |
| `permission.lineInferred` | `Maybe waiting for your permission (inferred)` | `可能在等你核准權限（推斷）` | :683 |
| `permission.hint` | `To approve, go back to the terminal` | `要核准請回終端機` | :685 |
| `permission.hintInferred` | `Inferred: this tool call has had no result for a long time · if it is only slow it will recover by itself · to approve, go back to the terminal` | `推斷：這個工具呼叫太久沒有結果 · 若只是跑得久會自己恢復 · 要核准請回終端機` | :686 |
| `list.separator` | `, `（逗號加一個空白） | `、` | :691 |
| `certainty.confirmed` | `confirmed` | `確定` | :710 |
| `certainty.inferred` | `inferred` | `推斷` | :710 |
| `ack.button` | `Seen` | `已讀` | :713 |
| `expand.open` | `▾ History` | `▾ 經過` | :724 |
| `expand.close` | `▴ Collapse` | `▴ 收起` | :724 |
| `copy.title` | `Copy the resume command` | `複製 resume 指令` | :741 |
| `empty.list` | `No agents in this view right now` | `這個分類目前沒有 agent` | :774 |
| `summary.unread` | `{n} unread` | `未讀 {n}` | :785 |
| `title.unread` | `({n}) Needs you · Agent Viewer` | `({n}) 需要你 · Agent Viewer` | :789 |
| `stale.note` | `Data stopped at {time}` | `資料停在 {time}` | :796 |
| `since.wait` | `Waiting {time}` | `已等 {time}` | :806 |
| `since.run` | `This turn {time}` | `本輪 {time}` | :806 |
| `since.ago` | `Ended {time} ago` | `{time}前結束` | :806 |
| `offline.badge` | `OFFLINE` | `離線` | :854 |
| `offline.note` | `The viewer is not responding (it may have been stopped)` | `viewer 沒有回應（可能已經 stop）` | :856 |
| `toast.copied` | `Copied: {cmd}` | `已複製：{cmd}` | :917 |
| `toast.noAudio` | `This browser does not support Web Audio` | `這個瀏覽器不支援 Web Audio` | :940 |
| `note.reason-unknown` | `Reason unknown` | `原因未知` | server :1585 |
| `note.alive-inferred` | `Alive: inferred` | `存活：推斷` | :711；server :1708 |
| `note.background-shell` | `Background shell running` | `背景 shell 執行中` | server :1608 |
| `note.registry-may-be-stale` | `Session registry may be stale` | `登記檔可能過時` | server :1626 |
| `note.previous-turn-failed` | `Previous turn failed/interrupted` | `上一輪 failed／interrupted` | server :1893 |

`now.recent`、`now.subagents` 與後面的項目之間不需要空白：兩個容器是 `display:flex` 加 `gap`（`viewer.py:462`、`:464`）；頂端計數的 `common.needsYou` 與數字之間同理（`:357`）。

### tr()

- **Responsibility:** 以目前語言取一個鍵的字串，代入佔位。
- **Interface:** `function tr(key, params)`；`key: string`，`params: object | undefined`（值會以 `String()` 轉字串）；回傳 `string`。
- **Data:** `s = STRINGS[langPref][key]`；`undefined` 時 `s = key`；對 `params` 的每個名字，`s = s.split('{' + name + '}').join(String(params[name]))`。不用正規式（C7）。
- **Errors:** 找不到鍵時回傳鍵名本身（decisions Tier 3），不丟例外。
- **Concurrency:** 純函式，讀 `langPref`。
- **Observability:** 畫面上出現鍵名（例如 `note.xyz`）即表示缺鍵或未知代碼。
- **Where it lives:** `viewer.py`，緊接在字串表與 `langPref` 之後。
- **What it reuses:** 無。回傳值寫進 HTML 時由呼叫端以 `esc()`（`viewer.py:603`）包住，唯一例外是 `applyLang()` 對 `data-i18n-html` 的寫入（值只來自頁內表）。

### 語言偏好與切換鈕

- **Responsibility:** 決定、記住並套用目前語言。
- **Interface:**
  - head 腳本（`viewer.py:290-297`）在既有 `try` 區塊之後加一個：`try { if (localStorage.getItem('agent-viewer-lang') === 'zh-Hant') document.documentElement.setAttribute('lang', 'zh-Hant'); } catch (e) {}`，前面加一行英文註解說明「在首次繪製前定語言」。
  - `<html lang="zh-Hant">`（`:285`）改為 `<html lang="en">`。
  - 字串表之後：`const LANG_KEY = 'agent-viewer-lang';`、`let langPref = 'en';`、`try { if (localStorage.getItem(LANG_KEY) === 'zh-Hant') langPref = 'zh-Hant'; } catch (e) {}`。
  - 頁首，緊接在 `#themeSeg`（`:503-507`）之後：`<div class="seg" id="langSeg" role="radiogroup" data-i18n-aria-label="lang.aria">`，內含 `<button data-lang-pref="en" lang="en">English</button>` 與 `<button data-lang-pref="zh-Hant" lang="zh-Hant">繁體中文</button>`。兩個標籤兩種語言都一樣，不走表（L1 的例外）。
  - `function renderSoundBtn()`：`document.getElementById('soundBtn').textContent = tr(soundOn ? 'sound.on' : 'sound.off');`。
  - `function applyLang()`，依序：`setAttribute('lang', langPref)` 於 `<html>`；每個 `[data-i18n]` 設 `textContent = tr(el.dataset.i18n)`；每個 `[data-i18n-html]` 設 `innerHTML = tr(el.dataset.i18nHtml)`；每個 `[data-i18n-title]` 設 `title`；每個 `[data-i18n-aria-label]` 設 `aria-label`；每個 `[data-lang-pref]` 依是否等於 `langPref` 切換 `active` class 與 `aria-checked`（比照 `applyTheme()`，`:561-564`）；`renderSoundBtn()`；`setOffline(failCount >= 3)`。
  - `#langSeg` 的 click：取 `closest('[data-lang-pref]')`，沒有就 return；`langPref = b.dataset.langPref`；`localStorage.setItem(LANG_KEY, langPref)` 包在 `try` 裡；`applyLang()`；`render()`。
  - 腳本最後（今天 `:945` 的 `render();` 之前）呼叫一次 `applyLang();`。
- **Data:** localStorage `agent-viewer-lang` ∈ {`en`, `zh-Hant`}；其他值與讀不到都當 `en`。
- **Errors:** localStorage 丟例外時（例如隱私模式）：讀當 `en`，寫就不記，當下切換照常生效——與主題相同（`viewer.py:557`、`:571`）。
- **Concurrency:** 單執行緒；`applyLang()` 讀 `soundOn`、`failCount` 兩個 `let`，只能在腳本跑完宣告後呼叫（見 `## Design decisions`）。兩個分頁各自有 `langPref`，只在開頁時讀 localStorage，一個分頁切換不會即時改另一個分頁（與主題相同）。
- **Observability:** `<html lang>` 屬性可在開發者工具看到。
- **Where it lives:** `viewer.py` 的 `<head>`、頁首 HTML、主題區段（`:553-574`）之後的新區段「language: en / zh-Hant, remembered per browser」。
- **What it reuses:** 主題切換的形狀與 CSS（`.seg`，`viewer.py:366-370`；`applyTheme()`，`:558-565`；click 處理，`:567-573`）；`setOffline()`（`:849`）。

### 各處改寫

每一處都保留原本的結構，只把中文字面值換成查表。模板字串 `${...}` 裡的查表一律寫成 `${esc(tr('...'))}`，所以 `tests/test_viewer_page.py:22-59` 的允許清單不必改。模板字串裡的查表不帶參數物件：該測試的正規式不跨大括號（`tests/test_viewer_page.py:73`），`${esc(tr('x', {n: 1}))}` 會被切壞；要帶參數的查表一律先以 `+` 組好字串（今天的 `unreadHTML` 就是這樣，`viewer.py:785`）。

| 位置 | 改成 |
|---|---|
| :503 | 拿掉 `aria-label="主題"`，改帶 `data-i18n-aria-label="theme.aria"` |
| :504-506 | 三個按鈕內容清空，各帶 `data-i18n="theme.system"`／`theme.dark`／`theme.light`；:504 另把 `title` 換成 `data-i18n-title="theme.system.title"` |
| :508 | `<button id="soundBtn" class="toggle on"></button>`（文字由 `renderSoundBtn()` 填） |
| :509-510 | 文字包進 `<span data-i18n="chime.done"></span>`／`chime.inferred`，`<input>` 留在 `<label>` 裡、`<span>` 之前保留一個空白 |
| :515-516 | 文字包進 `<span data-i18n="unlock.text"></span>`；按鈕內容清空、帶 `data-i18n="unlock.button"` |
| :520、:521、:523 | 內容清空，帶 `data-i18n="filter.all"`／`common.needsYou`／`filter.plain`；:522 的 `cai track` 不動 |
| :529 | `<span id="codexLockNote" hidden><span data-i18n="footer.codexLock"></span><br></span>` |
| :530 | `<span data-i18n-html="footer.terminal"></span><br>` |
| :531-533 | 三行各換成 `<span data-i18n="footer.inference1"></span>`、`inference2`、`inference3`，行與行之間保留原本的換行與兩格縮排，第三個之後接 `<br>` |
| :534、:535 | `<span data-i18n="footer.order"></span><br>`、`<span data-i18n="footer.theme"></span>` |
| :610-615 `humanFmt` | `tr('dur.seconds', {n: s})`、`tr('dur.minutes', {n: Math.floor(s / 60)})`、`tr('dur.hoursMinutes', {h: Math.floor(s / 3600), m: Math.floor(s % 3600 / 60)})` |
| :616 `clock` | `function clock(ms)`：`langPref === 'zh-Hant'` 時回傳原呼叫 `new Date(ms).toLocaleTimeString('zh-TW', {hour12:false})`，否則 `pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds())` |
| :618-632 `stateLabel` | 每個 `label` 改成對應的 `tr('state.…')`；working 那行維持 `return {label: row.background === true ? tr('state.workingBackground') : tr('state.working'), icon:''};` 的形狀（`tests/test_viewer_page.py:178` 以此行比對） |
| :643 | `'" title="' + esc(tr('gate.title')) + '">⚑</li>…'` |
| :655-656、:714 | 註解改寫成英文，不留任何 CJK（引號「」改成 ASCII 引號） |
| :662、:663 | `esc(tr('now.recent'))`、`esc(tr('now.subagents'))` 取代字面值 |
| :679 | `<div class="hint">${esc(tr('question.hint'))}</div>` |
| :683-686 | `qline = confirmed ? tr('state.permission') : tr('permission.lineInferred')`；`hint = confirmed ? tr('permission.hint') : tr('permission.hintInferred')` |
| :691 | `const notes = (row.noteCodes \|\| []).map(c => tr('note.' + c)).concat(row.notes \|\| []).join(tr('list.separator'));`（D1：先代碼、後原文） |
| :710 | `tr('certainty.confirmed')`／`tr('certainty.inferred')` |
| :711 | `'<div class="meta">' + esc(tr('note.alive-inferred')) + '</div>'` |
| :713 | `'<button class="ack" data-act="ack">' + esc(tr('ack.button')) + '</button>'` |
| :723-724 | `esc(expanded.has(row.key) ? tr('expand.close') : tr('expand.open'))` |
| :741 | `title="${esc(tr('copy.title'))}"` |
| :759 | `JSON.stringify([row, acks.has(row.key), expanded.has(row.key), langPref])` |
| :773-775 | 沒有列時：提示不存在就插入 `'<div class="empty">' + esc(tr('empty.list')) + '</div>'`，已存在就設 `empty.textContent = tr('empty.list')` |
| :785 | `'<em>' + esc(tr('summary.unread', {n: unread})) + '</em>'` |
| :787-788 | `${esc(tr('common.needsYou'))}<b>…`、`${esc(tr('state.working'))}<b>…` |
| :789 | `document.title = unread ? tr('title.unread', {n: unread}) : 'Agent Viewer';` |
| :796 | `tr('stale.note', {time: clock(lastGeneratedAt)})` |
| :806 | `wait: tr('since.wait', {time: clockFmt(d)})`、`run: tr('since.run', {time: clockFmt(d)})`、`ago: tr('since.ago', {time: humanFmt(d)})`，`dur` 不變 |
| :854 | `badge.textContent = tr('offline.badge');` |
| :856 | `note.textContent = tr('offline.note');` |
| :917 | `toast(tr('toast.copied', {cmd}));` |
| :931-935 | `soundOn = !soundOn; e.currentTarget.classList.toggle('on', soundOn); renderSoundBtn();` |
| :940 | `toast(tr('toast.noAudio'))` |
| :945 | 前面加 `applyLang();` |

### server：noteCodes

- **Responsibility:** server 自己寫的備註以代碼送出，`notes` 只留平台原文（D1、D2）。
- **Interface:** 列多一個鍵 `"noteCodes": list[str]`，永遠存在（可為空）。代碼只有五個：`reason-unknown`、`alive-inferred`、`background-shell`、`registry-may-be-stale`、`previous-turn-failed`。
- **Data:**
  - `classify_claude` 的起始 dict（`viewer.py:1553`）加 `"noteCodes": []`。
  - `:1585` 改為 `notes=[waiting_for] if waiting_for else [], noteCodes=[] if waiting_for else ["reason-unknown"]`。
  - `:1608` 改為 `notes=[], noteCodes=["background-shell"]`；`:1626` 改為 `notes=[], noteCodes=["registry-may-be-stale"]`。
  - `_unknown_domain_row`（`:1667`）加 `"noteCodes": []`。
  - `claude_rows`：`:1708` 改為 `codes = ["alive-inferred"] if alive == "alive-unverified" else []`；`:1715` 改為 `classified["noteCodes"] = codes + classified["noteCodes"]`，`notes` 不再被加前綴。
  - `classify_codex` 的起始 dict（`:1840`）加 `"noteCodes": []`；`:1893-1895` 改為 `codes = ["previous-turn-failed"] if turn_status in ("failed", "interrupted") else []`，`notes=[], noteCodes=codes`。
  - 其餘每個 `notes=[]` 不動；`_as_background`（`:1542`）沿用傳入 dict 的 `noteCodes`。
- **Errors:** 無新路徑。`waiting_for` 是非字串的真值時照舊原樣進 `notes`，由頁面 `esc(String())`。
- **Concurrency:** 純函式，無共享狀態。
- **Observability:** `/api/rows` 的 JSON 直接看得到 `noteCodes`。
- **Where it lives:** `viewer.py` 的 `claude_source` 與 `codex_source` 區段。
- **What it reuses:** 既有的 `result.update(...)` 形狀；docstring 的「always carries」慣例（`:1547-1550`）。

### 測試

`tests/test_viewer_page.py` 新增：

- `test_string_tables_have_the_same_keys`：以 `re.search(r"const STRINGS_EN = (\{.*?\n\});", js, re.S)` 取出兩表、`json.loads`，鍵集合相等且為 64。
- `test_no_cjk_outside_the_zh_hant_table`：自 `PAGE_HTML` 移除以同一個正規式（換成 `STRINGS_ZH_HANT`）比對到的整段，從 `const STRINGS_ZH_HANT = ` 到結尾的 `};`，剩下的恰有一個「繁體中文」；再移除它後，沒有任何字元落在九個區段：U+2E80–2FDF、U+3000–303F、U+3040–30FF、U+3100–31BF、U+3400–4DBF、U+4E00–9FFF、U+AC00–D7AF、U+F900–FAFF、U+FF00–FFEF。
- `test_every_i18n_attribute_names_a_key`：`data-i18n`、`data-i18n-html`、`data-i18n-title`、`data-i18n-aria-label` 的每個值都是英文表的鍵。
- `test_every_note_code_has_a_key`：五個代碼的 `note.<code>` 都在英文表。
- `test_html_defaults_to_english_and_prepaint_reads_the_language_key`：`<html lang="en">`；head 腳本含 `agent-viewer-lang`。
- `test_language_switch_has_two_labelled_buttons`：`data-lang-pref="en"` 的按鈕文字是 `English`，`data-lang-pref="zh-Hant"` 的是 `繁體中文`。
- `test_render_signature_includes_language`：`const sig = ...` 那行含 `langPref`。
- `test_attention_notes_put_codes_before_raw_text`：`activityHTML` 的 `const notes = ` 那行含 `row.noteCodes` 且其位置在 `row.notes` 之前。

修改：`test_footer_has_the_codex_lock_note_hidden_by_default`（`:163-166`）改為斷言 span 內帶 `data-i18n="footer.codexLock"`，且英文表該鍵的值含 `thread-writer-locks`。`:135-136`、`:177-180` 不改仍會過：兩段中文在 zh-Hant 表裡、也就在主 `<script>` 裡。

`tests/test_viewer_claude.py`：`:195` 改為 `notes == []` 且 `noteCodes == ["reason-unknown"]`；`:259`、`:334` 改為 `notes == []` 且 `noteCodes == ["background-shell"]`；`:345` 改為 `noteCodes == ["registry-may-be-stale"]`；`:760` 改為 `"alive-inferred" in rows[0]["noteCodes"]`；`:162` 與新增一條斷言原文 `waitingFor` 在 `notes`、`noteCodes` 為空。`tests/test_viewer_codex.py`：`:219`、`:225` 改為 `notes == []` 且 `noteCodes == ["previous-turn-failed"]`。

### 出貨

- `plugins/cai/.claude-plugin/plugin.json` 的 `version` 由 `1.36.2` 改為 `1.37.0`。
- `python scripts/gen-codex.py` 重產 `plugins/cai-codex/`，再 `python scripts/gen-codex.py --release <大於 0.2.28 的版本>`；確切版號由 ship 決定，比照原 detail:728。
- `python scripts/validate.py` 全 PASS、`python -m pytest` 全綠（CLAUDE.md「Before pushing」）。

## Naming

| Name | What it is | Chosen by |
|---|---|---|
| `English`、`繁體中文` | 切換鈕上的兩個標籤 | the user, 2026-09-26（intake AC2；stance 核准時含 L1 例外） |
| `agent-viewer-lang` | localStorage 的語言鍵 | follows `agent-viewer-theme` at viewer.py:554 與 `agent-viewer-done-chime` at viewer.py:578 |
| `en`、`zh-Hant` | 語言值：存的值、`<html lang>`、`STRINGS` 的鍵 | follows `lang="zh-Hant"` at viewer.py:285（BCP 47 語言標籤） |
| `LANG_KEY`、`langPref`、`applyLang`、`langSeg`、`data-lang-pref` | 語言偏好的常數、變數、函式、元素 id、按鈕屬性 | follows `THEME_KEY`、`themePref`、`applyTheme`、`themeSeg`、`data-theme-pref` at viewer.py:554、:556、:558、:503、:504 |
| `STRINGS_EN`、`STRINGS_ZH_HANT`、`STRINGS` | 字串表常數 | 大寫常數 follows `STAGES`、`META` at viewer.py:541、:544；名字本身 designer 提案，Gate 1 待確認 |
| `tr` | 查表函式 | designer 提案，Gate 1 待確認（不用 `t` 的理由見 decisions Tier 3） |
| `renderSoundBtn` | 依 `soundOn` 寫聲音鈕文字的函式 | designer 提案，Gate 1 待確認 |
| `data-i18n`、`data-i18n-html`、`data-i18n-title`、`data-i18n-aria-label` | 靜態元素的鍵屬性 | `data-` 前綴 follows `data-act` at viewer.py:713；名字本身 designer 提案，Gate 1 待確認 |
| `noteCodes` | 列上的代碼陣列欄位 | camelCase follows `aliveCertainty` at viewer.py:1721；名字本身 designer 提案，Gate 1 待確認 |
| `reason-unknown`、`alive-inferred`、`background-shell`、`registry-may-be-stale`、`previous-turn-failed` | 五個代碼 | kebab-case follows `alive-unverified` at viewer.py:1706；名字本身 designer 提案，Gate 1 待確認 |
| `### 字串表內容` 的 64 個鍵 | 字串表的鍵 | designer 提案，Gate 1 待確認 |
| `### 測試` 的八個新測試名 | pytest 函式名 | `test_` 加描述 follows tests/test_viewer_page.py:76；名字本身 designer 提案 |

## Change points

| Path | Change | Exists today |
|---|---|---|
| `plugins/cai/scripts/viewer.py` | `PAGE_HTML`：字串表、`tr()`、語言偏好與切換鈕、`### 各處改寫` 全部；server：`noteCodes` | yes |
| `tests/test_viewer_page.py` | 八個新測試，一個改寫 | yes |
| `tests/test_viewer_claude.py` | 五處斷言改寫，一條新增 | yes |
| `tests/test_viewer_codex.py` | 兩處斷言改寫 | yes |
| `plugins/cai/.claude-plugin/plugin.json` | 版本 1.37.0 | yes |
| `plugins/cai-codex/scripts/viewer.py` 與 `.codex-plugin/plugin.json` | 由 `gen-codex.py` 重產與 `--release` | yes |
| 新相依套件 | 無 | — |

## Failure modes

| Situation | What happens | What the caller sees |
|---|---|---|
| 沒存偏好（第一次打開） | `langPref = 'en'` | 整頁英文 |
| localStorage 存了其他值（手改、未來版本） | 當 `en` | 英文；按一次切換就覆寫 |
| localStorage 讀寫丟例外 | 讀當 `en`；寫略過 | 可切換，但下次打開回到英文 |
| 字串表缺鍵（測試應已擋下） | `tr()` 回傳鍵名 | 畫面出現 `state.xyz` 之類的鍵名 |
| 較新的 server 送來未知代碼 | `tr('note.<code>')` 回傳鍵名 | attention 方框出現 `note.<code>`，經 `esc()` |
| attention 列：沒有 `waitingFor`、存活未驗證 | `noteCodes = ["alive-inferred", "reason-unknown"]`，`notes = []` | zh-Hant「存活：推斷、原因未知」（與今天同）；en「Alive: inferred, Reason unknown」 |
| attention 列：`waitingFor` 為 `input needed` | `notes = ["input needed"]`，不查表 | 兩種語言都顯示 `input needed`（L3） |
| 主腳本在 `applyLang()` 之前丟例外 | 靜態元素保持空白 | 控制項沒有文字；今天同樣情況下列表也不會出現（`:945-948` 不會執行） |
| 首次繪製發生在主腳本之前（C10，UNVERIFIED） | 一幀空白控制項 | 與今天的列表、計數一樣先空後填 |
| 切換時正顯示 toast | toast 不重寫 | 最多 2200 ms 仍是舊語言 |
| 切換時列表是空的 | 已存在的提示改字 | 提示換成新語言 |
| 更新後舊 viewer 仍在跑（D3） | launcher 回「already running」 | 仍是舊的中文頁面、沒有切換鈕，直到 `stop` 或重開機 |
| viewer 重啟後仍開著的舊分頁（D1） | 舊 JS 讀新列：只顯示 `notes` 原文 | attention 方框少了「原因未知」「存活：推斷」；身分欄的「存活：推斷」照舊（`:711` 讀 `aliveCertainty`）；重新整理後正常 |
| 兩個分頁 | 各自在開頁時讀偏好 | 一個分頁切換，另一個要重新整理才跟上（與主題相同） |

## Rollout

- **分段：** 一個 PR 出貨。單元 2（`noteCodes`）單獨上線時英文模式會少翻兩句，單元 1 單獨上線時 attention 方框仍是中文句；兩者都不值得分開發版。
- **既有資料：** 沒有遷移。新增一個 localStorage 鍵；主題與聲音的既有鍵不動。
- **進行中的呼叫者：** 見 `## Failure modes` 的最後三列——舊 viewer 行程、舊分頁、兩個分頁。launcher 與 `format` 不動（D3），Claude 與 Codex 兩份不同版本仍互認。
- **Rollback：** revert 這個 commit、重跑 gen-codex 與 `--release`。瀏覽器裡留下的 `agent-viewer-lang` 無害：舊頁面不讀它。

## Verification

| Criterion | Level | What it needs | Green before |
|---|---|---|---|
| AC1／UC1：沒存偏好就整頁英文 | unit＋manual | `test_html_defaults_to_english_and_prepaint_reads_the_language_key`、`test_no_cjk_outside_the_zh_hant_table`；verify 在語言設為中文的瀏覽器、清掉該站 localStorage 後實開 | 單元 1 合併 |
| AC2／UC2：切換、不重載、狀態保留、`lang` 跟著換 | unit＋manual | `test_language_switch_has_two_labelled_buttons`、`test_render_signature_includes_language`；verify 先設篩選、按已讀、展開一列，再切換兩次並看開發者工具的 `<html lang>` | 單元 1 合併 |
| AC3／UC3：重開沿用、首次繪製前讀出 | unit＋manual | `test_html_defaults_to_english_and_prepaint_reads_the_language_key`；verify 選 zh-Hant 後重新整理 | 單元 1 合併 |
| AC4／UC4：zh-Hant 逐字不變 | one-off＋manual | build 改動前先以一次性指令抄下 `PAGE_HTML` 裡每段中文字面值，改完逐一確認出現在 zh-Hant 表（不進 repo）；verify 以 zh-Hant 對照改動前的頁面看一次 | 單元 1 合併 |
| AC5：兩表同鍵、表外無 CJK | unit | `test_string_tables_have_the_same_keys`、`test_no_cjk_outside_the_zh_hant_table`、`test_every_i18n_attribute_names_a_key` | 單元 1 合併 |
| AC6／UC5：server 備註依語言、原文不翻 | unit | `tests/test_viewer_claude.py` 與 `tests/test_viewer_codex.py` 的改寫、`test_every_note_code_has_a_key`、`test_attention_notes_put_codes_before_raw_text` | 單元 2 合併 |
| AC7／UC6：不多寫、無新套件、CSP 不變、驗證全綠、Codex 重產、1.37.0 | unit＋CI | 既有 `tests/test_viewer_*.py` 全綠；`python scripts/validate.py`；`python scripts/gen-codex.py --check` 無 DENY／DRIFT／UNRELEASED | 單元 3 合併 |
| R1、R2 | unit | 同 AC1、AC5 | 單元 1 合併 |

## Work breakdown

| Unit | Depends on | Can run alongside | Done when |
|---|---|---|---|
| 1 頁面：字串表（含 `note.*` 五鍵）、`tr()`、語言偏好與切換鈕、`### 各處改寫` 除 :691 外全部、頁面測試 | nothing | 無（同一個檔案） | `python -m pytest tests/test_viewer_page.py` 全綠；AC4 的一次性比對通過 |
| 2 server `noteCodes` 與頁面 :691；claude、codex 測試 | 1（`tr()` 與 `note.*` 鍵） | 無 | `python -m pytest tests/test_viewer_claude.py tests/test_viewer_codex.py tests/test_viewer_page.py` 全綠 |
| 3 版本 1.37.0、gen-codex 重產與 `--release` | 1、2 | 無 | `python scripts/validate.py` 全 PASS；`python -m pytest` 全綠；`gen-codex.py --check` 乾淨 |

單元 1 風險最高（64 個鍵、L5 逐字），又沒有未滿足的相依，所以先做。build 中發現本文件有誤，依 `stage-build.md` 定的格式記偏差。

### Upstream blockers

| What | Owned by | Needed before |
|---|---|---|
| 無：不依賴本 repo 以外的任何東西 | — | — |


## 整併補充：agent-viewer-language-switch-decisions

來源為原 `2026-09-26-agent-viewer-language-switch-decisions.md`；以下僅保留上游背景或實作補充，現況以本檔維護說明為準。

#### Feasibility

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | 首次繪製前，`<head>` 內嵌腳本讀 localStorage 並改 `<html>` 的屬性 | verified | 主題已這樣做：`plugins/cai/scripts/viewer.py:290-297`；CSP 允許內嵌腳本：`viewer.py:275` |
| C2 | 在元素上設任意屬性（`lang`、`aria-label`），以及用屬性選擇元素 | verified | `setAttribute` 已用於 `viewer.py:563`；`querySelectorAll('[data-theme-pref]')` 已用於 `viewer.py:561` |
| C3 | 頁面與 `/api/rows` 由同一個 server 行程送出，新頁面不會讀到另一版 server 的資料 | verified | `viewer.py:1005-1011`（同一個 `do_GET` 送 `/` 與 `/api/rows`） |
| C4 | 已開著的舊分頁在 viewer 重啟到同一 port 後，會以舊的 JS 繼續輪詢、顯示新 server 的資料 | verified | `viewer.py:890` 以相對路徑 fetch；`:947` 每秒輪詢；`:894-897` 失敗只累計並標離線，不停止輪詢 |
| C5 | 舊頁面把 `notes` 陣列逐項轉字串再接起來；項目若是物件，會顯示成 `[object Object]` | verified | `viewer.py:691`；https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/join ：「The string conversions of all array elements are joined into one string.」；https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Object/toString ：「Everything else, including user-defined classes, unless with a custom `Symbol.toStringTag`, will return "[object Object]".」 |
| C6 | 列的 keyed update 只重畫「簽名」變了的列，簽名今天不含語言 | verified | `viewer.py:759-768` |
| C7 | `PAGE_HTML` 是一般（非 raw）的 Python 字串，今天整段沒有反斜線；表內若寫反斜線，Python 會先改寫它 | verified | `viewer.py:284` 以 `"""` 開頭、無 `r` 前綴；Grep 反斜線在 `viewer.py` 的命中全在 `:1084` 之後，`:284-952` 零筆 |
| C8 | 測試能以正規式從 `PAGE_HTML` 取出一段物件字面值再解析 | verified | `tests/test_viewer_page.py:104-108` 已這樣取 `META` |
| C9 | gen-codex 照抄 `viewer.py`，改寫 `/cai:` 與反引號包住的 agent 名，並對它套 `DENY_LIST` | verified | `scripts/gen-codex.py:98-108`、`:129-144`、`:277-292` |
| C10 | 瀏覽器會不會在頁尾的內嵌腳本執行前，先畫出一幀靜態 HTML | UNVERIFIED | 沒查 HTML 規範。站在它上面的只有 D7（首幀可能是空的控制項），與今天的列表、頂端計數同一處境（`viewer.py:501`、`:526` 也是空的，等 `:945` 的 `render()` 填） |
| C11 | launcher 只比對 `/identity` 的 `format`；Claude 與 Codex 兩份腳本共用同一個狀態檔 | verified | `viewer.py:2495-2505`；`viewer.py:201-205`（路徑只看暫存目錄與 uid）；原 detail:120「gen-codex 產生的 Codex 副本不必與 Claude 那份逐位相同也能互認」 |
| C12 | zh-Hant 的時鐘沿用今天的 `toLocaleTimeString('zh-TW', {hour12:false})`，輸出與今天相同 | verified | `viewer.py:616`（同一個呼叫原樣保留） |

#### Ruled out

| Option | Invariant it violates | Evidence |
|---|---|---|
| 在 `notes` 陣列裡以字首標記代碼（例如 `@reason-unknown`） | L3：平台的 `waitingFor` 是任意字串，恰好同形就會被當代碼查表 | `waitingFor` 原樣進 `notes`：`viewer.py:1562-1565`、`:1585`；stance:27 |
| 靜態元素在 HTML 裡另寫一份英文，避免首幀空白 | L1：每段文字只有一個出處；HTML 裡的英文與英文表是兩個出處，會各自漂移 | stance:25 |
| server 依語言送頁，或以查詢參數、cookie 傳語言 | L2 | stance:26 |
| 沒存偏好時跟隨 `navigator.language` | L4（沒存就是英文） | stance:28；intake.md:25 |
| 字串表放成獨立檔案由頁面另外抓 | L6（不多抓任何檔案） | stance:30 |
| 把已知的 `waitingFor` 值（如 `input needed`）也翻譯 | L3 | stance:27 |

#### Requirement gaps

| # | The behavioural assumption | Veto condition, or verification path | Deletes |
|---|---|---|---|

#### Tier 1

（無。見 `## Reference` 下的本輪結果。）

#### Tier 2

##### D1 — server 自己的備註以什麼形狀送代碼？

選列上的新欄位 `noteCodes`（字串陣列，每項一個代碼），`notes` 只留平台原文，頁面先列代碼的翻譯、再列原文。物件混進 `notes` 會讓重啟後仍開著的舊分頁顯示 `[object Object]`（C4、C5）；字首標記違 L3（Ruled out）；不送代碼、由頁面自己推導，違反核准方案寫的「The two server notes become language-neutral codes」（intake.md:31）。先代碼後原文重現今天每一種組合：存活推斷永遠在最前（`viewer.py:1715`），「原因未知」與 `waitingFor` 互斥（`:1585`）。
**Found out when:** 下次 pytest（`tests/test_viewer_claude.py:195`、`:760` 要改）；舊分頁的樣子在 verify 重啟 viewer 時看得到。

##### D2 — 今天上不了頁面的三句備註，也改成代碼嗎？

也改：「背景 shell 執行中」（`viewer.py:1608`）、「登記檔可能過時」（`:1626`）、「上一輪 failed／interrupted」（`:1893`）一起進 `noteCodes`。D1 之後 `notes` 的意思是「平台原文，不翻譯」（L3）；server 自己的中文句留在那裡，就被標成了原文，日後任何一種狀態開始顯示 `notes`（今天只有 attention，`:690-692`）時，英文模式會出現中文，而且沒有測試擋。
**Found out when:** 下次 pytest（`tests/test_viewer_claude.py:259`、`:334`、`:345`，`tests/test_viewer_codex.py:219`、`:225` 要改）；不改的話，要等日後有人顯示 `notes`、使用者回報。

##### D3 — 要不要升 `/identity` 的 `format`，讓 launcher 叫仍在跑的舊 viewer 先 `stop`？

不升，維持 `1`。`format` 定義為協定版本、刻意不看腳本內容（原 detail:120）；Claude 與 Codex 兩份共用同一個狀態檔（C11），升了之後，版本不同的 cai 與 cai-codex 會互相要求對方 `stop`。「更新後舊 server 照跑，要換新版得先 `stop`」是原設計已接受的行為（原 detail:720）；頁面與 API 同一行程送出（C3），不會錯配，舊分頁對新 server 也只是少了代碼的翻譯（D1）。
**Found out when:** 發版後——更新時正開著 viewer 的人重跑 `/cai:viewer` 只得到「already running」（`viewer.py:2504-2505`），仍看到中文頁面、沒有切換鈕，直到 `stop` 或重開機。

#### Tier 3

| Decision | Chose | Instead of | Found out when |
|---|---|---|---|
| 今天兩種語言都一樣的字（`Agent Viewer`、`LIVE`、`CLAUDE`／`CODEX`、`CAI TRACK`、`AGENT`、`TRACK ·`、`SID`、階段名、`⧉ resume`、篩選的 `cai track`） | 留在原處、不進表 | 全部走表（只有第三種語言用得到，stance:99 排除） | pytest 的 CJK 檢查不受影響；verify 看頁面 |
| D7 靜態文字（頁首、篩選列、解鎖列、頁尾）怎麼換語言 | HTML 裡這些元素留空、只帶鍵名，主腳本一開始就依所選語言填入；與列表、頂端計數等腳本填入的內容同一條路（C10 仍 UNVERIFIED） | HTML 內寫英文（Ruled out，L1）；另加 CSS 在換字前隱藏 | verify 以兩種語言各重開一次頁面 |
| 英文措辭，以及使用者在哪一關看到它 | detail 的 `### 字串表` 列出每一句的 en 與今天的 zh-Hant，Gate 1 一起看；verify 在瀏覽器再看一次 | 另開一輪 Tier 1 選單；或由 build 自訂、verify 才第一次看到 | Gate 1 |
| 英文模式的時鐘 | 以既有的 `pad()`（`viewer.py:604`）組 `HH:MM:SS`；zh-Hant 保留原呼叫（C12，L5） | 英文也走 `toLocaleTimeString` 的某個 locale（各瀏覽器的 24 小時輸出沒查證） | verify |
| 相對時間的語序 | 表值帶 `{n}`、`{time}` 等佔位，以 `split`／`join` 替換，不用正規式（C7：不引入反斜線） | 每種語言一個格式函式；字串串接 | pytest＋verify |
| 字串表的寫法 | 兩個 JSON 相容的物件字面值，放主 `<script>` 開頭；測試以 `json.loads` 比對鍵（C8） | 一個巢狀物件；一般 JS 物件寫法（測試得自己解析 JS） | pytest |
| 切換語言時，已畫好的列怎麼重畫 | 把目前語言放進 `render()` 的簽名（C6） | 切換時清空整個節點快取 | verify 手動切換 |
| 頁尾帶 `<b>` 的那一句 | 該鍵的值可含 `<b>`，以另一個屬性標記、用 `innerHTML` 寫入（值只來自頁內表，不含列資料）；其他一律 `textContent`；`<br>` 與換行留在 HTML 結構裡，zh-Hant 的空白與今天一樣 | 拆成更多鍵 | verify 逐字比對 zh-Hant |
| 查表函式的名字 | 不用 `t`：`stepperHTML` 的 `const t = row.track`（`viewer.py:635`）、`toast` 的 `const t`（`:812`）、`clock` 的參數 `t`（`:616`）都會遮住它 | `t` | pytest／verify（執行期 TypeError） |
| localStorage 裡存的不是 `en` 也不是 `zh-Hant` | 當成 `en` | 顯示錯誤 | verify |
| `PAGE_HTML` 裡帶中文的 JS 註解（`viewer.py:655-656`、`:714`） | 改寫成英文 | 讓 CJK 檢查略過註解（檢查會變複雜） | pytest |
| `problems` 裡的中文句（`viewer.py:2149`） | 不動：頁面不讀 `problems`（`:901-904`），不在 L1、L2 的範圍 | 改成英文 | 不會上頁面 |
| `CONTEXT.md:22-23` 以中文畫面標籤定義的兩個詞 | 不改：兩個詞是概念，zh-Hant 模式下畫面標籤逐字不變（L5） | 補上英文標籤 | 下一個讀 `CONTEXT.md` 的人 |
| README 與 MANUAL | 不改：兩處都沒說頁面是中文（`README.md:143`、`MANUAL.md:30`） | 加一句「可切換英文／繁體中文」 | 無 |
| 切換鈕的形狀與位置 | 與主題切換同形的分段按鈕，放在主題切換之後；兩個按鈕各帶自己語言的 `lang` 屬性（C2）；群組的 `aria-label` 走表 | 下拉選單 | verify |
| CJK 的判定範圍 | 列舉 Unicode 區段：CJK 部首、符號與標點、假名、注音、擴充 A、統一漢字、諺文、相容漢字、全形與半形 | 只查 U+4E00–U+9FFF（漏掉 `：、（`，AC5 明寫要含） | pytest |
| 表裡找不到鍵 | 顯示鍵名本身 | 顯示空字串 | verify |
| 首次繪製前讀語言 | 既有的 head 腳本多讀一個鍵，存的是 `zh-Hant` 才把 `<html lang>` 改掉（C1）；HTML 本身寫 `lang="en"` | 等主腳本再設 `lang`（首幀的 `lang` 會錯） | pytest 檢查 head 腳本含該鍵；verify |
| 英文字串與 gen-codex | 英文措辭不含任何 `DENY_LIST` 項目，不用反引號包 agent 名，不寫 `/cai:`（C9） | 事後靠 `gen-codex.py --check` 報錯再改 | `python scripts/gen-codex.py` 與 `validate.py` |
| 切換語言後誰要重寫 | 靜態元素、聲音鈕、離線徽章與說明、「資料停在」、頂端計數與分頁標題、所有列；toast 不重寫（2.2 秒後自己消失，`viewer.py:816`） | 連 toast 一起重寫 | verify |


## 整併補充：agent-viewer-language-switch-stance

來源為原 `2026-09-26-agent-viewer-language-switch-stance.md`；以下僅保留上游背景或實作補充，現況以本檔維護說明為準。

#### Optimises for

不讀中文的人打開 Agent Viewer 就能用英文看懂每一個地方，讀中文的人在頁首按一次就回到今天的畫面並一直沿用；所有措辭只由頁面自己決定，server 與它送出的資料不因語言而分岔。判準：AC5 的兩個 pytest（兩張表的鍵相同；zh-Hant 表以外沒有中日韓文字，CJK），加 verify 依 AC1–AC3 在瀏覽器手動核對。

#### Sacrifices

- **今天在用的人更新後先看到英文。** 沒存過偏好就是英文、不看瀏覽器語言（intake.md:25、:28）；讀中文的人得自己按一次切換。
- **加第三種語言要改 `viewer.py` 本身。** 沒有可以丟進來的語言檔，也沒有給譯者的流程；新表跟現有兩張一樣大，放在出貨的腳本裡（B 才有的好處，intake.md:31）。
- **每段介面文字都要寫兩次。** 新增或改一句，兩張表都得動，少一張 pytest 就紅；英文措辭全是新文字，沒有 mockup 核准過。
- **一列裡仍會混兩種語言。** 平台與使用者的原文照原樣顯示。今天的中文頁面已經如此（注意列顯示登記檔的 `waitingFor` 原文，例如 `input needed`，原 stance :17；進入 notes 見 `viewer.py:1565`、`:1585`）；英文模式下反過來，中文提問仍是中文。
- **`/api/rows` 裡 server 自己寫的備註不再是看得懂的句子。** 直接讀 JSON 的人看到的是代碼；出貨程式裡讀它的只有頁面本身（`viewer.py:890`）。

#### Invariants

**This system's:**

- L1 — 一個出處：頁面上今天寫成中文的每段文字（可見文字、`title`、`document.title`、toast（畫面下方短暫浮出的提示）、相對時間與時鐘格式、分隔符號如 `、`），以及新增的 `aria-label`（給螢幕閱讀器的標籤），都從 `PAGE_HTML` 裡每種語言一張的表查出；兩張表的鍵完全相同；zh-Hant 表以外的 `PAGE_HTML` 不含任何 CJK 字元（含 `：、（`），唯一例外是切換鈕上用該語言自己寫的名稱「繁體中文」（AC2 指定的標籤）。兩項各有 pytest（AC5）。
- L2 — server 不知道語言：語言選擇不離開瀏覽器，不新增請求、查詢參數、標頭或 cookie；server 自己寫、會上頁面的字串一律以與語言無關的代碼送出，由頁面查表翻譯（AC6）。
- L3 — 原文照原樣：`waitingFor`、提問與選項、summary、工具輸入、track 名稱、路徑一律不翻譯，也不得被頁面當成代碼去查表（AC6）。
- L4 — 語言是瀏覽器端的偏好，比照主題：存在 localStorage（瀏覽器替每個網站保存的鍵值資料）自己的鍵（主題的鍵見 `viewer.py:554`），首次繪製前就讀出（比照 `:290-297`）；沒存就是英文；切換不重新載入，篩選、已讀、展開照舊，`<html lang>` 跟著換（AC1–AC3）。
- L5 — 繁體中文模式下，今天已有的每段文字逐字不變；新增的只有切換鈕（AC4）。
- L6 — 頁面仍是一個自足的回應：內容安全政策（CSP，`viewer.py:275`）不改，不多抓任何檔案或字型，不加相依套件（AC7）。
- 原 stance 的 V1–V7（:26-32）照舊，尤其 V1：server 不多寫任何東西。

**Cross-project:**

- 原 stance 的四條（:36-39）照舊。其中 gen-codex 的行號已移動：禁字清單 `DENY_LIST` 現在是 `scripts/gen-codex.py:129-139`，`rewrite()` 是 `:277-292`。
- 英文字串也是出貨文字，gen-codex 會照抄並改寫：不得含任何 `DENY_LIST` 項目，`/cai:` 會被改成 `$`（`scripts/gen-codex.py:289`）；`tests/test_viewer_page.py:96-100` 已斷言 `PAGE_HTML` 不含其中四項。

#### Rejected stances

- **B：每種語言一個 JSON 檔，server 送頁時嵌入。** 加語言不必動 `viewer.py`；但 server 送頁時要讀語言檔，多一條失敗路徑（檔案缺或壞時送什麼）、出貨檔變多，輸在「措辭只由頁面決定」。使用者選 A（intake.md:31）。
- **server 依語言產生頁面（cookie 或查詢參數）。** 切換得重新載入（違 AC2），每秒更新的相對時間仍要一張頁內表，等於兩套機制（intake.md:31）。
- **預設跟隨瀏覽器語言。** 讀中文的現有使用者更新後不必多按一次；但使用者指定預設英文，核准的假設明寫不偵測（intake.md:25）。
- **只翻頁面自己的字，server 備註維持中文句子。** 不必動 server 與 `tests/test_viewer_claude.py` 的五處斷言（:195、:259、:334、:345、:760）；但英文模式仍會出現「原因未知」「存活：推斷」（`viewer.py:1585`、`:1708`），違 AC1、AC6。

#### Out of scope

- 第三種語言；偵測瀏覽器語言（intake.md:25）；`/cai:viewer` 的終端機輸出，由模型以使用者的語言轉述（`plugins/cai/skills/viewer/SKILL.md:14-16`、intake.md:27）；翻譯平台與使用者原文（L3）。
- `CONTEXT.md:22-23` 以中文畫面標籤定義兩個詞（執行中（背景）、存活確定度）；本階段不寫 `CONTEXT.md`，要不要改寫由 Decisions 提出。
- 留給 Decisions：
  - 代碼的形狀，以及頁面如何分辨代碼與原文：`waitingFor` 與「原因未知」同在 notes 陣列的同一個位置（`viewer.py:1585`），「存活：推斷」被併在最前面（`:1715`）。
  - 今天上不了頁面的三句備註（`:1608`、`:1626`、`:1893`；notes 只在注意列顯示，`:690-692`）與頁面不讀的 `problems`（`:2149`；頁面只取 rows、generatedAt、codexLockDirMissing，`:901-904`）要不要也改成代碼。
  - 更新後仍在跑的舊 viewer：launcher 只比對 `format`（`:2495`），相同就回「already running」（`:2505`），舊行程繼續送舊的中文頁面，直到 `stop` 或重開機；要不要升 `format`。
  - 頁首、篩選列、頁尾這些寫在 HTML 裡的靜態文字，能不能在首次繪製前就換成所選語言、選中文的人不先閃一下英文：UNVERIFIED，進可行性表。
  - 今天兩種語言都一樣的英文字（`Agent Viewer`、`LIVE`、`CLAUDE`／`CODEX`、階段名、`resume`）要不要也走表，L1 不強制。
  - 英文措辭與它在哪一關給使用者看、兩種語言的時鐘格式（今天寫死 `'zh-TW'`，`:616`）、相對時間的語序佔位（`:612-614`、`:806`）、切換鈕的 `aria-label`。
- `docs/` 被 git 忽略；本檔要進 PR 需在 ship 時 `git add -f`。
