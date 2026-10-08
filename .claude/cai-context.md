# Glossary

This file is only a glossary — one or two sentences per term, no decisions
or specs, and only concepts specific to this project.

## Domain

**審查基準（benchmark）**: `tests/review-benchmark/` 下一組已知有缺陷的改動，搭配計分器和量測程序，用來量測審查 agent 抓不抓得到。
**審查案例（case）**: 審查基準裡的一筆：一個已知有缺陷的改動，加上標出缺陷位置的標註。
**計分器**: 把審查 agent 的發現與審查案例的標註逐一比對、算出抓到多少缺陷的程式。
**慣例檔（convention file）**: `<top>/CLAUDE.md` 和 `<top>/.claude/CLAUDE.md` 當中實際存在的那些檔案。
**存活確定度**: Agent Viewer 每一列對「這個 agent 還在跑」有多少把握：有直接證據時是確定，只能從旁推斷時是推斷。
**Mirror comment**: The one comment on a ticket that a track owns and keeps up to date with the track's progress.
**Claim**: Any comment on a ticket that announces a cai track working on it, whoever wrote it.
**Resumable claim**: A claim whose track this checkout still holds, recorded under the claim's author and this same ticket, so the work can be picked up again.
**Finished claim**: A claim whose track this checkout holds among its finished tracks.
**產品版號**: cai 唯一由人手寫的版號，其他地方的版號都由它推出。
**公開介面**: 使用者直接依賴、改了就要另外告知的那些部分，例如技能名稱與設定的存檔格式。
**平台下限**: cai 支援的 Claude Code 與 Codex CLI 的最低版本。
**track 格式檔**: 進行中的 track 會讀寫的那些檔；改了它們的格式，尚未做完的 track 就會受影響。
**子目錄來源項目**: 市集檔裡指向某個 git repo 子目錄的外掛項目。
**發版提交**: 發布一個新版本時，同時更新版號、市集檔與更新紀錄的那一個提交。
**release PR**: 把發版提交帶進 main 的那個 PR。
**送出中的版本**: 使用者此刻從市集安裝會拿到的那個版本。
**標籤規則集**: GitHub 上保護版本標籤、不讓它被改動或刪除的設定。
**stable 分支**: 發布出問題時讓使用者退回去的分支，指向最後一個確認可用的版本。
**備份分支（backup branch）**: ship 改寫歷史之前留下的本地分支，保存改寫前的提交，從不推送。
**來源分支（source branch）**: 備份分支當初所備份的那條分支。
**代碼（note code）**: Agent Viewer 傳給頁面、與語言無關的備註代號，由頁面翻成使用者選的語言顯示。
**原文（raw text）**: Agent Viewer 上由平台或使用者寫的文字，頁面照原樣顯示、不翻譯。
**解析器（resolver）**: 替一個專案找出該跑哪一條測試指令的只讀程式。
**宣告（declaration）**: 專案自己在 cai 設定裡寫明的測試指令；有它時，解析器不再自行推測。
**候選（candidate）**: 沒有宣告時，解析器從專案根目錄的檔案推出的一條測試指令。
**入口（entry）**: 把整組測試包成一個名字的根目錄檔案，例如 make 或 npm 的設定檔；解析器從它推出候選。
**彙總入口（aggregate entry）**: 入口推出、無法再帶路徑縮小的指令，如 `make test`。
**標記檔（marker file）**: 只說明專案用什麼語言或建置工具、本身不包測試指令的根目錄檔案，例如 `Cargo.toml`。
**分流清單（triage list）**: 分流的結果：PR 上每則留言的等級與理由，逐則編號。
**分派器（dispatcher）**: hook 實際執行、CMD 與 sh 都能跑的那支腳本，由它決定一次工具呼叫放行還是擋下。
**啟動方式（launcher）**: 啟動 Python 的那條指令：一個絕對路徑，或 `py -3` 這類名稱。
**啟動方式紀錄（launcher record）**: 分派器記下的、上次確認能用的啟動方式，下次直接用它而不再找一遍。
**活動者（actor）**: 計時時把一段工作歸給誰的單位：主 session、某個子代理，或一次工具呼叫。
**活動紀錄（timing journal）**: track 自己逐筆追加的計時紀錄，記下每段工作的起訖、歸屬與缺漏。
**六階段摘要（six-stage timing summary）**: 合併各階段已證實工作區間後輸出的累積時間與資料完整性。
**計時完整性（timing completeness）**: 計時摘要對自己資料是否齊全的說明；不齊全時，摘要裡的時間只是下限。
**階段執行標記（stage-run token）**: 主 session 放進分派提示的一行識別字，讓計時 hook 知道一個子代理屬於哪一次階段執行。
**暫存觀測（spool）**: 子代理還沒綁定到某一次階段執行之前，先記下的計時觀測。
**綁定（binding）**: 一個子代理與它所屬那一次階段執行之間的對應，或明確記下它不屬於任何一次。
**模型段（model segment）**: 一個子代理從開始或一批工具全部結束，到它下一次呼叫工具或結束為止的區間；期間只有模型在產生回應（含平台對同一請求的自動重試）。
**層級（level）**: 一條驗收條件要靠什麼證明，例如自動測試、在本機實際跑一次，或由人手動確認。
**層級表（Verification levels table）**: intake 裡為每條驗收條件寫明層級與檢查方式的那張表。
**驗證計畫（verify plan）**: verify 開始前排出的表，寫明每條驗收條件要怎麼被證明，或為什麼證明不了。
**啟動宣告（start declaration）**: 專案在 cai 設定裡寫明、怎麼把它啟動起來並確認就緒的方式，供在本機實際跑檢查時使用。
**本機執行器（local runner）**: 依驗證計畫把專案啟動起來、跑完每項本機檢查、存下證據再收掉程序的程式。
**證據檔（evidence file）**: 一項本機檢查的完整輸出，存在 track 目錄裡供事後查看。
**本機執行紀錄（local-run record）**: 本機執行器每次執行後留下的紀錄，寫明每項檢查的結果與它的證據檔。
**彙整檔（synthesis）**: verify 階段對每條驗收條件的判斷彙整：對到哪些測試、掛了哪些發現。
**證據清單（evidence manifest）**: verify 結束時為每條驗收條件列出層級、結果與證據的清單，ledger 以它作為 verify 的成果。
**紅燈基準（red baseline）**: build 在一個單元改程式之前，先對它的本機檢查跑一次得到的失敗輸出，用來證明改動之後才轉為通過。

## Process

**審查基準量測程序（review-benchmark procedure）**: 把一筆審查案例交給審查 agent、收下它的發現、再交給計分器的固定步驟。
**合規審查鏡（conformance lens）**: verify 階段四個審查 agent 之一，比對改動有沒有符合書面需求和慣例檔。
**timed-out menu**: A menu result carrying the platform's own "away from your keyboard" sentence.
**Claim menu**: The menu that asks whether to resume a track already claimed on the ticket, asked before a new track is named.
**Claim projection**: Posting a track's claim on its ticket, done right after intake has read the ticket.
**Final projection**: The last update a track makes to its mirror comment, as the track is finished.
**Close menu**: The menu asked once a track is finished, offering to close its ticket or leave it open.
**本機閘門**: 發版前在本機跑的檢查，全部通過才做出發版提交。
**遠端檢查**: 發版後在乾淨的設定目錄裡，讓 Claude Code 與 Codex 從 GitHub 實際安裝新版本，確認裝得起來。
**Gate 2 前段選單（Gate 2 front）**: Gate 2 裡請本人同意推送並開 PR、或更新 PR 的那個選單。
**合併確認（merge confirmation）**: 合併 PR 前的那一次確認：不另開選單，由守門程式在合併指令執行前請本人同意。
**分流（triage）**: main session 把每則留言依 Blocker／Major／Minor 分級並寫理由。
**分流選單（triage menu）**: 問本人要不要修 PR 上那些 Blocker 與 Major 的選單。
**修正輪（fix round）**: 選「修」之後 verify 修、main session 提交、ship 重跑、再等再抓的一整圈。
**輪數上限（round cap）**: 一個 PR 能跑的修正輪次數上限，第一次開 PR 不算一輪。
**探測（probe）**: 分派器實際執行一個找到的 Python 直譯器、確認它能用的那個動作。
**精簡檢查（reduced check）**: 找不到能用的 Python 時，分派器改用的簡化攔截方式，只擋最危險的幾類指令。
**階段執行（stage run）**: track 一個階段的一次分派，從開始到交回為止。
**計時來源准入（source admission）**: 決定某個計時資料來源能不能被採信的那道檢查。
**詞彙檢查（glossary check）**: 隨 cai 出貨的檢查，判斷一條定義能不能寫進詞彙表；它擋下的定義不會被寫入。
