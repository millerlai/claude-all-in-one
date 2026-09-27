# agent-viewer-language-switch — decisions

## Reference

- Stance: `docs/design/2026-09-26-agent-viewer-language-switch-stance.md` — status: approved 2026-09-26
- Intake：`.claude/track/support-multiple-langauge-for-agent-viewer/intake.md`（approved 2026-09-26，方案 A）
- 原 viewer 的 detail：`docs/design/2026-09-25-agent-viewer-web-portal-detail.md`（下稱「原 detail」）

本輪結果：Tier 1 零項。stance「留給 Decisions」的每一項（stance:101-107）與 `CONTEXT.md:22-23` 的問題，不是證據只剩一個選項（Tier 2），就是三項成本都低（Tier 3）。沒有需求缺口。英文措辭歸 Tier 3，但完整對照表寫在 detail 的 `### 字串表`，Gate 1 會一起看到。

## Feasibility

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

## Ruled out

| Option | Invariant it violates | Evidence |
|---|---|---|
| 在 `notes` 陣列裡以字首標記代碼（例如 `@reason-unknown`） | L3：平台的 `waitingFor` 是任意字串，恰好同形就會被當代碼查表 | `waitingFor` 原樣進 `notes`：`viewer.py:1562-1565`、`:1585`；stance:27 |
| 靜態元素在 HTML 裡另寫一份英文，避免首幀空白 | L1：每段文字只有一個出處；HTML 裡的英文與英文表是兩個出處，會各自漂移 | stance:25 |
| server 依語言送頁，或以查詢參數、cookie 傳語言 | L2 | stance:26 |
| 沒存偏好時跟隨 `navigator.language` | L4（沒存就是英文） | stance:28；intake.md:25 |
| 字串表放成獨立檔案由頁面另外抓 | L6（不多抓任何檔案） | stance:30 |
| 把已知的 `waitingFor` 值（如 `input needed`）也翻譯 | L3 | stance:27 |

## Requirement gaps

| # | The behavioural assumption | Veto condition, or verification path | Deletes |
|---|---|---|---|

## Tier 1

（無。見 `## Reference` 下的本輪結果。）

## Tier 2

### D1 — server 自己的備註以什麼形狀送代碼？

選列上的新欄位 `noteCodes`（字串陣列，每項一個代碼），`notes` 只留平台原文，頁面先列代碼的翻譯、再列原文。物件混進 `notes` 會讓重啟後仍開著的舊分頁顯示 `[object Object]`（C4、C5）；字首標記違 L3（Ruled out）；不送代碼、由頁面自己推導，違反核准方案寫的「The two server notes become language-neutral codes」（intake.md:31）。先代碼後原文重現今天每一種組合：存活推斷永遠在最前（`viewer.py:1715`），「原因未知」與 `waitingFor` 互斥（`:1585`）。
**Found out when:** 下次 pytest（`tests/test_viewer_claude.py:195`、`:760` 要改）；舊分頁的樣子在 verify 重啟 viewer 時看得到。

### D2 — 今天上不了頁面的三句備註，也改成代碼嗎？

也改：「背景 shell 執行中」（`viewer.py:1608`）、「登記檔可能過時」（`:1626`）、「上一輪 failed／interrupted」（`:1893`）一起進 `noteCodes`。D1 之後 `notes` 的意思是「平台原文，不翻譯」（L3）；server 自己的中文句留在那裡，就被標成了原文，日後任何一種狀態開始顯示 `notes`（今天只有 attention，`:690-692`）時，英文模式會出現中文，而且沒有測試擋。
**Found out when:** 下次 pytest（`tests/test_viewer_claude.py:259`、`:334`、`:345`，`tests/test_viewer_codex.py:219`、`:225` 要改）；不改的話，要等日後有人顯示 `notes`、使用者回報。

### D3 — 要不要升 `/identity` 的 `format`，讓 launcher 叫仍在跑的舊 viewer 先 `stop`？

不升，維持 `1`。`format` 定義為協定版本、刻意不看腳本內容（原 detail:120）；Claude 與 Codex 兩份共用同一個狀態檔（C11），升了之後，版本不同的 cai 與 cai-codex 會互相要求對方 `stop`。「更新後舊 server 照跑，要換新版得先 `stop`」是原設計已接受的行為（原 detail:720）；頁面與 API 同一行程送出（C3），不會錯配，舊分頁對新 server 也只是少了代碼的翻譯（D1）。
**Found out when:** 發版後——更新時正開著 viewer 的人重跑 `/cai:viewer` 只得到「already running」（`viewer.py:2504-2505`），仍看到中文頁面、沒有切換鈕，直到 `stop` 或重開機。

## Tier 3

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
