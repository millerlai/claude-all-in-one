---
name: cut-release
description: Use when asked to cut, publish or bump a release of this repo's plugins (for example "更新 release 版本", "發版", "出新版", "release 1.41.0", "cut a release"), or when `scripts/release.py` stopped with a FAIL partway through one. Maintainer-only; never shipped to users. Usage - /cut-release [X.Y.Z]
---

# cut-release

把 `main` 上已合併、但還沒發佈的變更發成一個新版本。Claude Code 和 Codex 共用同一個版號，兩邊都從 tag 安裝。`scripts/release.py` 四個子命令的用法，README 的 `### Releasing` 和該檔開頭的 docstring 已經寫過，這裡不再重抄，只放執行順序、要先問的地方和踩過的坑。

## 名詞

- **tag**（版本標籤）：`vX.Y.Z`，釘在某個 commit 上的版本名。兩個 marketplace 檔都指向它；一推上 GitHub，這個號碼就不能再用。
- **release PR**：`cut` 自動開的 PR，方向是 `release/vX.Y.Z` → `main`。內容只有四樣：版號、marketplace 釘選、重新產生的 cai-codex、CHANGELOG。
- **squash 合併 與 `--merge` 合併**：squash 把整個 branch 壓成一個新 commit 再放進 `main`；`--merge` 保留原本的 commit，另外加一個 merge commit。release PR 只能用後者，原因見「踩過的坑」。
- **SemVer 版號段**：MAJOR.MINOR.PATCH 三段。哪種改動升哪一段，看 README `## Compatibility` 的表。
- **本機 gate**（本機關卡）：`cut` 推 tag 之前自己跑的 `validate.py` 加完整 pytest。

## 輸入與輸出

- 輸入：版號 `X.Y.Z`，可以省略，省略時依步驟 2 決定。
- 輸出：
  - tag `vX.Y.Z`：已推上 GitHub，兩個平台都實際裝過；
  - GitHub Release `vX.Y.Z`：內容就是 CHANGELOG 的那一段；
  - release PR：以 `--merge` 合併。
- 要先問的有三處：刪遠端 branch（步驟 3）、推 tag（步驟 5）、合併 release PR（步驟 8）。

## 步驟

1. **前置確認。**
   - 工作區要乾淨；不乾淨就停下來問。接著 `git switch main && git pull --ff-only && git fetch --tags`。release PR 被 squash 合併過時，tag 不在 `main` 的歷史裡，光靠 pull 抓不到。
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
   - 遇到 `FAIL a release is already in flight: origin/release/vA.B.C` 時，先查它是不是上一次 release PR 被 squash 合併後留下的：
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
5. **先確認，再 `cut`。**
   - 先用問題工具問一次，內容包括：版號和理由、CHANGELOG 各節的標題，並說明 tag 推出去之後，這個號碼就不能撤回。
   - 對方同意後，在背景跑 `PYTHONUTF8=1 python scripts/release.py cut X.Y.Z`，中途不要打斷。本機 gate 要先裝好 pytest-xdist，沒裝會在 pytest 那步直接失敗。
   - 一印出 `PASS vX.Y.Z pushed`，這個號碼就用掉了。之後的安裝驗證如果失敗：
     - 網路之類的暫時問題：跑 `python scripts/release.py verify X.Y.Z` 重試；
     - 其他原因：先修好，再用下一個號碼從步驟 3 整個重走（包括本步驟的確認），並在 CHANGELOG 註明跳過了哪個號碼。
6. **盯 release PR 的 CI。** 在背景跑 `gh pr checks <n> --watch`，等結果出來。
7. **`publish`。** CI 綠了才跑 `PYTHONUTF8=1 python scripts/release.py publish X.Y.Z`。它會建立 GitHub Release，最後印出合併指令。跑完用 `gh release view vX.Y.Z --json isDraft,publishedAt,url` 確認它不是草稿。
8. **合併 release PR（先問）。**
   - 使用者已經明確說要合併（例如「幫我 merge」），就算問過了，不必再問一次。
   - 只用 `publish` 印出的那一行：`gh pr merge <n> --merge --match-head-commit <完整 40 字元 sha>`。不要請人到 GitHub 網頁上按合併：這個 repo 平常的 PR 都用 squash，網頁上的按鈕很容易停在 squash。
   - Claude Code 會跳出權限確認。這是 guard 的設計（#228），不是錯誤。
   - 合併之後：
     - `git switch main && git pull --ff-only`；
     - 確認 `main` 的 push CI 通過；
     - 確認 `git merge-base --is-ancestor vX.Y.Z origin/main` 成立。

## 踩過的坑

- **release PR 被 squash 合併**：v1.39.0 的 #222 和 v1.40.0 的 #236 都是。後果有兩個：
  - tag 所在的 commit 不在 `main` 的歷史裡，下一次 `prepare` 會把舊的 `release/v*` branch 當成仍在進行中（處理方式見步驟 3）；
  - `prepare` 用 `<上一個 tag>..HEAD` 起草 CHANGELOG，會把上一版的 `chore(release)` commit 也列進去。
- **`prepare` 起草的 CHANGELOG 不能直接用**：它會混進 test、docs 之類的維護者項目，track 警告也可能不實。v1.40.0 的草稿兩個問題都有。
- **Windows 上 stdout 的編碼**：Python 把 stdout 導到檔案時用的是 cp950，所以每個指令前面都加 `PYTHONUTF8=1`。
- **`--match-head-commit` 不接受縮寫的 sha**：要用 `gh pr view <n> --json headRefOid` 給的完整值。

## 交付前

- [ ] 版號是依 Compatibility 表決定的，理由寫在確認問題裡
- [ ] CHANGELOG 那段是寫給使用者看的：沒有維護者項目，track 警告已查證
- [ ] `cut` 全部 PASS，兩個平台都印出 `installed and verified`
- [ ] release PR 的 CI 綠了才 `publish`，而且 GitHub Release 不是草稿
- [ ] 合併用的是 `--merge`，tag 在 `main` 的歷史裡
