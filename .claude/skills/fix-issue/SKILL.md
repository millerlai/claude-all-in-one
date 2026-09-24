---
name: fix-issue
description: Use when asked to fix, resolve or work through a GitHub issue of this repo (for example "fix issue 142", "修 issue 142", "依序從 issue N 開始", or an issue URL) and the result should be a tested fix on a branch plus a PR that closes it. Covers reproducing on main, test-first, the cai-codex regenerate and release step, validate.py and the full pytest, the PR and its CI. Usage - /fix-issue <issue number or URL>
---

# fix-issue

把這個 repo 的一個 issue，從「在 `main` 上重現」一路做到「PR 的 CI 綠了」。步驟裡用到的都是這個 repo 自己的腳本，所以這份 skill 只在這裡用。`CLAUDE.md` 已經寫過的規則（validate、pytest、codex 的產生與 release），這裡不再重抄，只放執行順序和踩過的坑。

## 輸入與輸出

- 輸入：issue 編號或 URL。一次要處理好幾個 issue 時，一個一個來，照 issue 裡的順序表走，例如 #138 的「Task order」。
- 輸出：
  - `fix/<N>-<slug>` branch 上的修正和測試；
  - 一個帶 `Closes #N` 的 PR；
  - 那個 PR 的 CI 結果。
- commit、push、合併，每一步都要先問過。

## 步驟

1. **讀 issue。** 跑 `gh issue view <N>`，讀出驗收條件、`Decision needed` 和順序。遇到待決點時：
   - 如果便宜又可逆，就採用 issue 的建議，並在回報裡說明；
   - 否則先問一個問題，得到答案再動手。
2. **開 branch。** 確認工作區乾淨，接著 `git switch main && git pull --ff-only`，再 `git switch -c fix/<N>-<slug>`。這個 issue 如果已經有 branch，先問哪一個才算數。
3. **先在 `main` 上重現。**
   - scratch 腳本放在 scratchpad，不要放進 repo。
   - 隔離方式和 `tests/conftest.py` 一樣：拿掉 `CLAUDE_CODE_SESSION_ID`，並把 `CAI_USAGE_LEDGER` 指到 scratch 路徑。
   - CLI 要照 skill 實際的跑法去跑，例如 `track_state.py status` 要從專案根目錄執行。
   - 重現不出來，就停下來回報。
4. **先寫會失敗的測試。**
   - 每個驗收條件寫一個測試，放在 issue 點名的測試檔裡，沿用那個檔案的 helper。
   - 先跑一次，讀失敗訊息：它必須是因為 issue 描述的原因而失敗，不能是 import error。
   - 修之前就會通過的守門測試可以保留，但回報裡要點名是哪幾個。
5. **修。**
   - 做讓測試轉綠的最小改動。註解寫「為什麼」，並附上 issue 編號。
   - 再用懷疑的眼光檢查一次：找出可能打破新規則的輸入，例如模板占位字、legacy 文件、CRLF、相對路徑和絕對路徑。真的找到就補一個測試。
6. **bump 版本、release codex。**
   - 改到 `plugins/cai/`，就 bump `plugins/cai/.claude-plugin/plugin.json`；修 bug 只升 patch 版本。
   - 改到會被產生進 `plugins/cai-codex/` 的檔案，就跑 `python scripts/gen-codex.py`。全部改完之後再跑 `--release <main 上的版本升一個 patch>`。
   - 同一個 branch 上可以重跑同一個版本號，因為它只和 `main` 上的版本比較。
   - `usage_report.py` 這類不會被產生過去的檔案，不需要 release。
7. **驗證。**
   - `python scripts/validate.py` 要 exit 0，而且沒有任何 FAIL。
   - 完整的 `python -m pytest` 放背景跑，中途不要打斷。
   - 程式碼一改就要重跑一次完整測試；跑到一半才改動的那一輪，結果不能拿來當證據。
8. **對照驗收條件。** 每個驗收條件都要指到對應的 `file:line`。凡是做法和 issue 寫的不一樣，或是自己決定了某個待決點，都逐條列出來。
9. **commit 並開 PR（先問）。**
   - `git add` 時逐一列出檔名。
   - commit 訊息先寫進檔案，再用 `git commit -F`。內文要帶 `Closes #N` 和 attribution。
   - `git push -u origin <branch>`。
   - `gh pr create --base main --body-file <檔案>`，內文分成 Summary、Behaviour changes、Test plan 三節。
   - 用 `gh pr view <n> --json closingIssuesReferences` 確認列出了這個 issue。
10. **盯 CI。**
    - 在背景跑 `gh pr checks <n> --watch`，結果出來再回報。
    - 被要求合併時，跑 `gh pr merge <n> --squash --match-head-commit <完整 40 字元的 headRefOid>`。
    - 合併之後同步 `main`，並確認 `main` 的 push CI 也通過。

## 踩過的坑

- `--match-head-commit` 不接受縮寫的 SHA，要用 `gh pr view <n> --json headRefOid` 給的完整值。
- 這個 repo 合併後不會刪掉 branch，所以疊在別的 PR 上的 PR 不會自動改 base。做法是：
  1. 一開始就開成 draft；
  2. base 合併之後，手動 `gh pr edit <n> --base main`；
  3. 然後才合併它。
- 中斷 pytest 會留下 `plugins/cai/evals/_breach_test_fake_secret.md`。pytest 跑到一半時，validate hook 也可能報出假的 FAIL：等 pytest 跑完、重跑一次 validate 再下判斷。
- Windows 本機全部通過、Linux CI 卻失敗：測試裡預期的路徑要用 pathlib 組，不要直接寫反斜線。
- `main` 前進之後，發生衝突的 PR 不會跑 CI。處理方式：
  - 把 `origin/main` merge 進來；
  - 產生出來的檔案一律取 theirs，再重新產生；
  - release 的版本號用 `main` 上的版本加一。
- Windows 上，Python 重導出去的 stdout 會用 cp950 編碼：腳本前面加 `PYTHONUTF8=1`，中文內容則用 Write／Edit 寫進檔案。

## 交付前

- [ ] 修之前重現過問題；修之後，同一個 repro 給出 issue 要的答案
- [ ] 每個新測試都親眼看過它失敗（守門測試除外，並已點名）
- [ ] validate exit 0；完整的 pytest 是在最終狀態跑的
- [ ] 每個驗收條件都指到 `file:line`，所有偏離都列出來了
- [ ] 版本已 bump；需要時 codex 也已 release
