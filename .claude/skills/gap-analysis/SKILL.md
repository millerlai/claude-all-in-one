---
name: gap-analysis
description: Use when asked how far cai is from an external practice — a deck, a playbook, a company's engineering blog, an industry survey — and the answer is expected to be a ranked, evidenced list of what to close rather than a prose comparison. Triggers include 差距、對照、比較、benchmark、"how do we compare".
disable-model-invocation: true
---

# gap-analysis

把一份外部來源拆成 5–8 個**機制**，逐項對照 cai 的現況，產出一份每個判定都有
`file:line` 或 URL、有排序、也更新前幾份未做項目狀態的差距文件。三份範例：
`docs/design/2026-08-29-capability-gap-analysis.md`、
`docs/design/2026-09-01-ai-native-sdlc-playbook-gap-analysis.md`、
`docs/design/2026-09-12-silicon-valley-ai-sdlc-gap-analysis.md`。

## 輸入與輸出

- 輸入：來源——`docs/` 裡的檔案（PDF／MD）、一個 URL、或一個要上網查的主題。
- 輸出：`docs/design/YYYY-MM-DD-<slug>-gap-analysis.md`，`<slug>` 是來源名稱的
  kebab-case（例：`uber-ureview`、`ai-native-sdlc-playbook`），節序照同目錄的
  `template.md`。`docs/` 是 gitignored；不 `git add -f`，除非被要求。終端只給摘要。
- 指令一律走 Bash tool（`tail`、`wc`、`od` 是 POSIX 語法）。

## 步驟

1. **釘基準。** `git rev-parse --short HEAD`、`plugins/cai/.claude-plugin/plugin.json`
   的 `version`、`python -m pytest --collect-only -q | tail -1`、
   `ls -1 .claude/track/done/ | wc -l`（一個子目錄一條）。全部寫進「比較基準」。
2. **先讀前幾份** `docs/design/*-gap-analysis.md`。沿用它們的 task ID 前綴與
   S／M／L／XL 規模；其中每一個「未做」都重新驗證一次——上次的未做可能已經做了。
   驗證結果填進 template 的「與前幾份的關係」表，一項一列，附證據。
3. **讀來源。** 給了檔案或 URL 就直接讀（URL 用 WebFetch），不另外搜；只有給
   「主題」才先 WebSearch 每家公司／每個主題，再 WebFetch 一手來源（工程 blog、
   changelog、官方報告）。新聞轉述的數字標「二手」。PDF 若是純影像：
   `pdftoppm -png -r 100` 轉圖再讀。
4. **拆機制。** 各一列：機制／誰在做、怎麼做／數字。拆的是機制，不是產品名；
   來源有幾個就列幾個——一整份 playbook 通常 5–8 個，一篇 blog 可能只有 2–3 個，
   不湊數。
5. **逐項找 cai 對應，先跑 program 層。** 從 `README.md` 的四層與三張表定位這個
   機制落在哪個 stage／tool／script；stage 的話沿 `plugins/cai/skills/track/stages.json`
   → 該 stage 的 `references/stage-*.md` → 它派的 `agents/*.md`。再用 Grep／Glob
   找步驟 4 那一列裡的概念字（例：來源講 review 就搜 `lens`、`REVIEW.md`、
   `security`）；零命中要寫出搜過的路徑。每個判定附 `file:line`。
6. **先寫定位差異。** 來源描述的是誰（組織？個人？）。每一項都要問一次
   「這個機制對一個出貨給個人安裝的 plugin 還成立嗎」，不成立就寫成「形狀不同」
   或「規模差異」，不列為缺口。
7. **也列領先處。** 前幾份列過的不重複，只寫這次對照才多出來的。
8. **寫文件。** 判定詞彙固定六個：對得上／領先／部分／缺／形狀不同／規模差異。
   task 各自帶：來源、現況、完成判準（機械可判）、風險（做錯會變成什麼——例：
   判準不機械就變成模型脫罪的出口；上 PR 就每個 PR 都花模型的錢）；相依關係
   畫進「建議順序」。
9. **每張 Mermaid 用 mmdc 驗。** `.mmd` 寫進 scratchpad，`mmdc -i x.mmd -o x.svg`，
   exit 0 才算過。classDef 只用 `template.md` 裡的：總覽圖 `ok`／`partial`／
   `missing`／`neutral`，順序圖 `now`／`next`／`later`。
10. **檢查無 BOM。** `head -c 3 <file> | od -c`，第一個 byte 必須是 `#`。
11. **終端摘要**依序：一句結論 → 對照表 → 真正該補的 2–3 項 → 自上一份以來變了什麼
    → 未證實的部分 → Sources。順手發現的過期敘述（例：README 說沒人跑過 track）
    只記在文件裡，不改。

## 踩過的坑

- Bash tool 會把非 ASCII argv 打成亂碼：中文一律用 Write／Edit 進檔，不走 echo。
- `grep.exe` 曾回空結果而看起來像「沒有」：用 Grep tool。
- 「沒有」的準確寫法是「在這些路徑下零命中」；來源說「沒人做」要寫成
  「查到的公開資料裡沒看到」。
- 子代理轉述的平台功能要在本機再驗一次（`<cmd> --help`），沒驗到的標未證實。
- 兩份來源重疊的項目要有一張「關係」表，說清是同一層還是不同層，避免重做。

## 交付前

- [ ] 每個判定有 `file:line` 或 URL
- [ ] 二手數字都標了
- [ ] 前幾份的未做項目逐一重驗過，狀態表在文件裡
- [ ] 每張 Mermaid 都 exit 0
- [ ] 建議順序說了先做哪一項、為什麼
