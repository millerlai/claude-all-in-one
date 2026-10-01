---
name: cut-release
description: Cut, publish, or bump a release of this repository's cai and cai-codex plugins, or resume a failed scripts/release.py run. Maintainer-only workflow for this repository; not a shipped plugin skill.
---

# cut-release

在本專案使用 `$cut-release [X.Y.Z]` 發版。省略版號時，依共用流程判斷。

先完整讀取[共用發版流程](../../../.claude/skills/cut-release/SKILL.md)，再依其步驟執行；所有相對於專案的指令都在儲存庫根目錄執行。版號判斷、更新紀錄（CHANGELOG）改寫、失敗復原與交付檢查都沿用該流程，不另維護副本。此入口只供本專案維護者使用，不加入 `plugins/cai-codex/` 或全域技能安裝。

## Codex 執行差異

- 原流程的 `/cut-release` 在 Codex 中改用 `$cut-release`。
- Windows 的 PowerShell 不使用 `PYTHONUTF8=1 python ...` 語法。每個發版腳本指令改為以下形式，保留原本的子命令與版號：

  ```powershell
  $env:PYTHONUTF8 = '1'
  & 'C:\Python313\python.exe' scripts/release.py prepare X.Y.Z
  ```

  `cut`、`verify`、`publish` 同樣替換。這是專案自己的腳本，直接執行，不經 cai-codex 的腳本啟動器。
- 不支援 `&&` 的 PowerShell 版本，逐一執行原流程的 Git 指令，每次檢查 `$LASTEXITCODE`，成功才執行下一個。`head -1` 改為 `Select-Object -First 1`。
- 發版確認沿用共用流程；已有明確授權就不重複詢問。需要確認時使用當前可用的問題工具；若工具不支援權限確認或沒有問題工具，直接向使用者確認並等候回答。探索到技能本身不代表已授權發版。
- 共用流程提及的 Claude Code 權限視窗只適用於 Claude Code；Codex 依當前執行權限申請必要核准，不依賴 Claude 的攔截檢查（guard）。
- 耗時的腳本或持續整合（CI）監看，用執行工具的背景工作與輪詢處理；保持狀態回報，不中斷 `cut`。
