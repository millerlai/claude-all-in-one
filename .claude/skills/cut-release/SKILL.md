---
name: cut-release
description: Use when asked to cut, publish or bump a release of this repo's plugins (for example "更新 release 版本", "發版", "出新版", "release 1.41.0", "cut a release"), or when `scripts/release.py` stopped with a FAIL partway through one. Maintainer-only; never shipped to users. Usage - /cut-release [X.Y.Z]
---

# cut-release

把 `main` 上已合併、但還沒發佈的變更發成一個新版本。Claude Code 和 Codex 共用同一個版號，兩邊都從 tag 安裝。`scripts/release.py` 四個子命令的用法，CONTRIBUTING.md 的 `## Releasing` 和該檔開頭的 docstring 已經寫過，這裡不再重抄，只放執行順序、要先問的地方和踩過的坑。

## 和 GitHub Actions 的關係

平常發版走 `cut-release` workflow（CONTRIBUTING.md `### Releasing with GitHub Actions`）：版號建議、用 Copilot CLI 起草並檢查 CHANGELOG、推 tag、發佈、把 `main` 快轉到 tag 都由它做，人只按 Run workflow 和兩次核准。本技能是 workflow 不能用時的備援，例如 Copilot 或 Actions 設定失效，或想自己寫 CHANGELOG。有兩種用法：

1. 全部在本機：照下面步驟 1–7 做。
2. 只在本機寫 CHANGELOG：做完步驟 1–4，推送候選 commit，以 `head` 輸入啟動 workflow，它會跳過 Copilot 起草，從檢查候選 commit 開始。

workflow 不會補升級軸樣本：不論走哪一條路，發佈之後都要做步驟 7。

## 名詞

- **tag**（版本標籤）：`vX.Y.Z`，釘在某個 commit 上的版本名。兩個 marketplace 檔都指向它；一推上 GitHub，這個號碼就不能再用。
- **發版 commit**：`chore(release): vX.Y.Z`，只改四樣：版號、marketplace 釘選、重新產生的 cai-codex、CHANGELOG。tag 就打在它上面。
- **快轉（fast-forward）`main`**：不開 PR，直接把 `main` 推到發版 commit。發版 commit 的上一個 commit 就是 `main`，所以一般的 `git push`（不加 `--force`）就能讓 `main` 前進；`main` 在這期間如果多了別的 commit，git 會拒絕，這個號碼就作廢（D3＝B，2026-10-09）。
- **SemVer 版號段**：MAJOR.MINOR.PATCH 三段。哪種改動升哪一段，看 README `## Compatibility` 的表。
- **本機 gate**（本機關卡）：`cut` 推 tag 之前自己跑的 `validate.py` 加完整 pytest。
- **升級軸樣本**：`tests/fixtures/releases/<tag>/` 裡的檔案，由那個 tag 自己的 script 寫出，合併之後不再修改。`tests/test_upgrade_axis.py` 用現在的程式去讀它，確認在 track 做到一半時更新 plugin 的人，手上的舊檔還讀得動。

## 輸入與輸出

- 輸入：版號 `X.Y.Z`，可以省略，省略時依步驟 2 決定。
- 輸出：
  - tag `vX.Y.Z`：已推上 GitHub，兩個平台都實際裝過；
  - GitHub Release `vX.Y.Z`：內容就是 CHANGELOG 的那一段；
  - `main` 快轉到 tag 的 commit，tag 在 `main` 的歷史裡；
  - `tests/fixtures/releases/vX.Y.Z/`：這一版的升級軸樣本，另開一個 PR。
- 要先問的有四處：刪遠端 branch（步驟 3）、推 tag（步驟 5）、`publish`（步驟 6，它會讓 `main` 前進）、樣本 PR 的 commit 與 push（步驟 7）。

## 步驟

1. **前置確認。**
   - 工作區要乾淨；不乾淨就停下來問。接著 `git switch main && git pull --ff-only && git fetch --tags`。以前的 release PR 被 squash 合併過時，那些 tag 不在 `main` 的歷史裡，光靠 pull 抓不到。
   - `main` 最新一次 push CI 要是綠的：`gh run list --branch main --limit 1 --json databaseId,headSha,conclusion`。還在跑，就在背景跑 `gh run watch <databaseId> --exit-status` 等它結束；紅的就停下來回報。
   - `git diff --stat <上一個 tag> origin/main -- plugins/` 如果是空的，代表使用者拿到的東西沒變，沒有東西要發。停下來說明。
2. **決定版號。**
   - 上一個 tag：`git tag --list 'v*' --sort=-v:refname | head -1`。
   - 變更清單：`git log --oneline <tag>..origin/main`。
   - 有沒有新增或移除 skill：`git diff --name-status <tag> origin/main -- 'plugins/cai/skills/*/SKILL.md'`，只看 `A`、`D`、`R` 開頭的列。
   - 依 README `## Compatibility` 的表判斷：
     - skill 被移除或改名、舊存檔讀不進來、平台下限提高 → MAJOR；
     - 新增 skill、track 格式改變（`state.md` 或 ledger 記錄的內容） → MINOR；
     - 只有腳本修 bug、規則改字 → PATCH。
   - 表裡沒列到，但有新的腳本或新行為（例如新的 `feat(cai)`）→ 取 MINOR，並在步驟 5 的確認裡寫出理由。
3. **`prepare`。** 執行 `PYTHONUTF8=1 python scripts/release.py prepare X.Y.Z`。exit 2 代表前置條件沒滿足，而且什麼都還沒寫。
   - 遇到 `FAIL a release is already in flight: origin/release/vA.B.C` 時，先查它是不是以前的 release PR 被 squash 合併後留下的：
     1. `gh pr view release/vA.B.C --json state` 的結果是 `MERGED`；
     2. `git rev-parse origin/release/vA.B.C` 等於 `git rev-parse "vA.B.C^{commit}"`。
   - 兩項都成立，就是誤判。先問過，再 `git push origin --delete release/vA.B.C`，然後用同一個 `X.Y.Z` 重跑 `prepare`。那個 commit 由 tag 保住，要還原就跑 `git push origin "vA.B.C^{commit}:refs/heads/release/vA.B.C"`。
   - 任一項不成立，或 `gh pr view` 查不到，都當成真的有 release 在進行中：停下來回報。
   - 其他 FAIL：照訊息把前置條件補齊，再跑一次。
4. **改寫 CHANGELOG 那一段。** `prepare` 起草的只是 commit 標題的清單，要改成使用者看得懂的版本，格式照上一版那段：
   - 開頭一句話說這版做了什麼，接著一行平台下限；沒變就寫明 unchanged。
   - `### What to do when you update`：Claude Code 和 Codex 的更新指令，照抄上一版；再加一條，說明更新對進行中的 track 有什麼影響。
   - 依使用者感受得到的區塊分節，例如 Track、Guard、Usage。每一條寫看得到的行為，並附上 `(#PR)`。內容從各個 PR 的說明讀：`gh pr view <n> --json title,body`。
   - 拿掉兩類項目：
     - 只和維護者有關的 PR，也就是只動到 `scripts/`、`tests/`、`docs/`、`CLAUDE.md`、`.github/` 的；
     - 上一版的 `chore(release)` commit。
   - `plugins/cai/skills/track/SKILL.md` 或 `plugins/cai/scripts/ledger.py` 只要有 diff，`prepare` 就會自動加上一句 "Finish any track in progress before updating..."。先查證：讀 `git diff <上一個 tag> origin/main -- plugins/cai/skills/track/SKILL.md plugins/cai/scripts/ledger.py`，看 `state.md` 的欄位或 ledger 每筆記錄的欄位有沒有增減、改名。沒有就刪掉這句，改成一句說明進行中的 track 更新後實際會怎樣；完全沒影響，就寫沒影響。
   - 標題 `## vX.Y.Z — <日期>` 保持原樣：`cut` 和 `publish` 都靠它找到這一段。
   - 只想自己寫 CHANGELOG、其餘交給 GitHub Actions 時（見開頭「和 GitHub Actions 的關係」的用法 2），做到這裡就依 CONTRIBUTING.md `### Releasing with GitHub Actions` 的備援段落推送候選 commit，以 `head` 輸入啟動 workflow；步驟 5–6 由 workflow 執行，推 tag 與快轉 `main` 改在受保護環境中核准。
5. **先確認，再 `cut`。**
   - 先用問題工具問一次，內容包括：版號和理由、CHANGELOG 各節的標題，並說明 tag 推出去之後，這個號碼就不能撤回。
   - 對方同意後，在背景跑 `PYTHONUTF8=1 python scripts/release.py cut X.Y.Z`，中途不要打斷。本機 gate 要先裝好 pytest-xdist，沒裝會在 pytest 那步直接失敗。
   - 一印出 `PASS vX.Y.Z pushed`，這個號碼就用掉了。之後的安裝驗證如果失敗：
     - 網路之類的暫時問題：跑 `python scripts/release.py verify X.Y.Z` 重試；
     - 其他原因：先修好，再用下一個號碼從步驟 3 整個重走（包括本步驟的確認），並在 CHANGELOG 註明跳過了哪個號碼。
6. **`publish`（先問）。** 它會建立 GitHub Release，再把 `main` 快轉到 tag 的 commit：一跑完，使用者更新就會拿到這一版。
   - 使用者已經明確說要發佈（例如「幫我 publish」），就算問過了，不必再問一次。
   - 執行 `PYTHONUTF8=1 python scripts/release.py publish X.Y.Z`。
   - 印出 `FAIL main advanced since vX.Y.Z was cut` 時，`main` 在這期間多了別的 commit，這個號碼作廢，也還沒建立 GitHub Release：從步驟 3 用下一個號碼重走，並在 CHANGELOG 註明跳過的號碼。
   - 跑完之後：
     - `gh release view vX.Y.Z --json isDraft,publishedAt,url` 確認它不是草稿；
     - `git switch main && git pull --ff-only`；
     - `main` 的 push CI 要通過：在背景跑 `gh run list --branch main --limit 1 --json databaseId,headSha,conclusion` 找到這次的 run，再 `gh run watch <databaseId> --exit-status`；
     - 確認 `git merge-base --is-ancestor vX.Y.Z origin/main` 成立。
7. **替剛發的版本補一份升級軸樣本（commit 與 push 先問）。** 指令和規則在 CONTRIBUTING.md 的 `### Upgrade-axis samples`，這裡不重抄。
   - 從同步後的 `main` 開 branch，照那一節的指令新增 `tests/fixtures/releases/vX.Y.Z/`。發版 commit 只能改四樣，所以樣本不放進去，另開一個只動 `tests/` 的 PR。
   - 樣本一定要用 `vX.Y.Z` 這個 tag 自己的 script 產生，不能拿現在的程式代寫，也不能照上一版的樣本改幾個字：那樣測不到兩版之間的差異。
   - `state.md` 和 `current` 沒有 script 會寫，是從上一版的樣本帶過來的。先讀 `git diff <上一個 tag> vX.Y.Z -- plugins/cai/skills/track/SKILL.md`，track 技能對這兩個檔的說法有變，才照新的說法手改。
   - 跑 `python -m pytest tests/test_upgrade_axis.py -n0`。紅了有兩種可能：新版讀不動舊版留下的檔，或樣本帶了 session id、token 用量或本機路徑。兩種都照 CONTRIBUTING 那一節處理，已合併的樣本不能改。

## 踩過的坑

- **以前的 release PR 被 squash 合併**（D3＝B 之前，現在已不開 release PR）：v1.39.0 的 #222、v1.40.0 的 #236、v1.45.1 的 #301 都是。留下的後果有兩個：
  - tag 所在的 commit 不在 `main` 的歷史裡，下一次 `prepare` 會把舊的 `release/v*` branch 當成仍在進行中（處理方式見步驟 3）；
  - `prepare` 用 `<上一個 tag>..HEAD` 起草 CHANGELOG，會把上一版的 `chore(release)` commit 也列進去。
- **`prepare` 起草的 CHANGELOG 不能直接用**：它會混進 test、docs 之類的維護者項目，track 警告也可能不實。v1.40.0 的草稿兩個問題都有。
- **Windows 上 stdout 的編碼**：Python 把 stdout 導到檔案時用的是 cp950，所以每個指令前面都加 `PYTHONUTF8=1`。

## 交付前

- [ ] 版號是依 Compatibility 表決定的，理由寫在確認問題裡
- [ ] CHANGELOG 那段是寫給使用者看的：沒有維護者項目，track 警告已查證
- [ ] `cut` 全部 PASS，兩個平台都印出 `installed and verified`
- [ ] `publish` 前問過；GitHub Release 不是草稿
- [ ] `main` 已快轉到 tag，tag 在 `main` 的歷史裡，`main` 的 push CI 通過
- [ ] 這一版的升級軸樣本已經開 PR，或已說明為什麼還沒開
