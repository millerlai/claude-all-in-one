# Glossary

This file is only a glossary — one or two sentences per term, no decisions
or specs, and only concepts specific to this project.

## Language

<!--
  Example: `**Term**: one or two sentences saying what it is.` A `_Avoid_`
  line naming synonyms not to use can go under a term by hand afterwards —
  build never writes one.
-->

**審查基準（benchmark）**: `tests/review-benchmark/` 下一組已知有缺陷的改動，搭配計分器和量測程序，用來量測審查 agent 抓不抓得到。
**case 目錄**: 審查基準裡的一個子目錄，只放 `diff.patch`（有缺陷的改動的 diff）和 `expected.json`（標註）。
**計分器**: 拿 finding 跟標註比對 lens、檔名、行號（容忍 ±3 行）的程式（`scripts/review_benchmark_score.py`）。
**審查基準量測程序（review-benchmark procedure）**: 把一筆 case 變成可計分紀錄的九個步驟（`scripts/review-benchmark-procedure.md`）。
**合規審查鏡（conformance lens）**: verify 階段四個審查 agent 之一，比對改動有沒有符合書面需求和慣例檔。
**慣例檔（convention file）**: `<top>/CLAUDE.md` 和 `<top>/.claude/CLAUDE.md` 當中實際存在的那些檔案。
**timed-out menu**: A menu result carrying the platform's own "away from your keyboard" sentence.
**unanswered**: The state of a stop whose menu timed out with no defined outcome for silence.
**執行中（背景）**: Agent Viewer 上 Claude 列的一種顯示：主 session 這一輪已結束，只剩背景子代理或 Workflow 在跑，確定度標推斷、不閃不響。
**存活確定度**: Agent Viewer 每一列「存活：確定／推斷」的依據強弱；Codex 列只憑鎖檔檔名判斷，一律標推斷。
**Mirror comment**: The one issue comment a track owns, found back by marker plus cached login and edited in place.
**Marker**: The first line of a mirror comment, `[cai track: <name>]`.
**Status line**: The mirror comment's second line, `status: in-progress` or `status: done`.
**Claim**: Any comment on the issue whose first line is a marker, whoever wrote it.
**Claim listing**: The `claims: <n>` line and its `<n>` claim lines that `read --ref` prints between title and body.
**Resumable claim**: A claim whose name has a directory under `.claude/track/` here, whose `ticket.json` caches the claim's author as login and points at this same issue number.
**Finished claim**: A claim meeting the same pointer test against `.claude/track/done/<name>/` instead.
**Claim menu**: The menu asked when the claim listing is non-empty, before the name menu.
**Claim projection**: The `ticket.py project` run right after intake's ticket read, which posts the claim.
**Final projection**: `ticket.py project --final`, run by `done` before the move.
**Close menu**: The menu `done` asks after the move: "Close #<number>" or "Leave it open".
**Pointer**: A track's `ticket.json`: backend, ref, cached login, last projection.
**Timeout table**: approval-gates' "what each stop does about a menu that closed on its own".
**產品版號**: 唯一手寫的版號，其他版號欄位都由它推出（I1）。
**公開介面**: 技能名稱、`/cai:setup` 寫入位置、model-choice 存檔格式、平台最低版本（D1＝B）。
**平台下限**: Claude Code 2.1.283（D12）、codex-cli 0.157.1（D11）。
**track 格式檔**: 改到它們時，發布頁要提醒「進行中的 track 先做完再更新」（D1＝B）。
**子目錄來源項目**: 市集檔裡 `source` 為 `{"source": "git-subdir", "url", "path", "ref"}` 的外掛項目。
**發版提交**: 標題 `chore(release): vX.Y.Z`、同時寫版號、ref、cai-codex 與 CHANGELOG 的那一個提交（D6）。
**release PR**: 從 release 分支到 main 的 PR，以合併提交合併（D3）。
**本機閘門**: `cut` 在提交前跑的 `validate.py` 與 `pytest`。
**遠端檢查**: `verify` 在隔離設定目錄裡讓兩個 CLI 從 GitHub 安裝新標籤。
**送出中的版本**: origin/main 的 Claude 市集檔 `ref` 所指的版本。
**標籤規則集**: GitHub repo 設定裡對 `v*` 禁止更新、刪除的規則集（D5）。
**stable 分支**: 退路：最後一個好標籤加一個「市集檔改回相對路徑」的提交（D4）。
**備份分支（backup branch）**: ship 在 squash 前建的本地分支 `backup/<來源>-<後綴>`，從不 push；來源的 PR 合併後，sweep 會把它列為可刪。
**來源分支（source branch）**: 備份分支當初備份的那條分支，sweep 從備份名對回某個已合併 PR 的 head 找出它。
**時間檢查**: sweep 判斷備份可刪的條件之一：備份最後一個 commit 不晚於來源 PR 的合併時間，用來擋住同名分支重複使用時的誤刪。
**代碼（note code）**: Agent Viewer 的 server 自己寫的備註改送的短字串，與語言無關，由頁面查字串表翻成所選語言，例如 `reason-unknown`。
**原文（raw text）**: Agent Viewer 列上平台或使用者寫的文字（`waitingFor`、提問、摘要、工具輸入、路徑），頁面照原樣顯示，不翻譯也不查表。
**解析器（resolver）**: 只讀的程式，輸入專案目錄，輸出這個專案的測試指令，或「多個／未知／宣告格式錯」。
**宣告（declaration）**: `.claude/cai.json` 裡 `test.commands` 這個非空字串清單。
**候選（candidate）**: 沒有宣告時，解析器從根目錄某個檔案推出的一條指令。
**入口（entry）**: 把測試包成一個名字的根目錄檔案：Makefile、justfile、Task 的檔案（Taskfile.yml、taskfile.yml、Taskfile.yaml、taskfile.yaml、Taskfile.dist.yml、taskfile.dist.yml、Taskfile.dist.yaml、taskfile.dist.yaml，取第一個存在的）、package.json、tox.ini、noxfile.py。
**彙總入口（aggregate entry）**: 入口推出、無法再帶路徑縮小的指令，如 `make test`。
**縮小方式（narrow）**: 一條指令能不能帶範圍：`paths`、`packages`、`none`。
**標記檔（marker file）**: 只說明語言或建置工具的根目錄檔案，如 `Cargo.toml`、`go.mod`；和上面的 **Marker**（mirror comment 的第一行）意思不同，兩者並存。
**Gate 2 前段選單（Gate 2 front）**: Gate 2 裡問「推送並開 PR／更新 PR」的那個選單，選項沿用 `Run them`、`Stop — hand me the commands`。
**合併選單（merge menu）**: Gate 2 後段，只問合併，選項 `Merge`、`Stop`，都不帶推薦標記。
**分流（triage）**: main session 把每則留言依 Blocker／Major／Minor 分級並寫理由。
**分流清單（triage list）**: 分流的結果，逐則編號，列在分流選單或合併選單上方。
**分流選單（triage menu）**: 清單上有 Blocker/Major 且輪數未滿時問「修不修」的一般停點。
**修正輪（fix round）**: 選「修」之後 verify 修、main session 提交、ship 重跑、再等再抓的一整圈。
**輪數上限（round cap）**: 修正輪最多 2 輪，第一次開 PR 不算。
**未檢查（unchecked）**: 某來源抓不到、某檢查 600 秒內沒跑完，或某檢查結束時沒有結果（逾時、被取消、沒啟動、需要動作、過期）；清單上明列原因，絕不當成 0 則。
