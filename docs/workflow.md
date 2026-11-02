# 工作流程

核對日期：2026-11-02。術語：工作軌道（track）是一項功能的持久紀錄；驗收條件（acceptance criteria，AC）是可觀察的完成標準；工作樹（worktree）是同一版本庫的獨立工作目錄；人工關卡（human gate）是本人對明確設計或動作的核准。

## 四階段與核准

| 階段 | 執行者與產物 | 現行程序 |
|---|---|---|
| 設計（design） | 主工作階段釐清問題、驗收條件及方案；依難以回復的訊號選短路線或完整設計 | [stage-design.md](../plugins/cai/skills/track/references/stage-design.md) |
| 建置（build） | 實作代理（implementer）依可獨立驗證的單元施工，進度與追溯寫入實作備註 | [stage-build.md](../plugins/cai/skills/track/references/stage-build.md) |
| 驗證（verify） | 主工作階段整合平台審查與獨立審查，修正嚴重發現並執行測試 | [stage-verify.md](../plugins/cai/skills/track/references/stage-verify.md) |
| 發布準備（ship） | 主工作階段準備分支、提交訊息與發布說明；不可逆操作前取得核准 | [stage-ship.md](../plugins/cai/skills/track/references/stage-ship.md) |

第一道核准在設計後、建置前。短路線核准需求文件 `intake.md`；長路線用單份 `docs/design/<date>-<topic>-design.md`，依序包含立場（Stance）、決策（Decisions）與細節（Detail）。本人閱讀與核准的範圍，以及整份建置文件的指紋，是不同概念，詳見 [approval-gates.md](../plugins/cai/skills/track/references/approval-gates.md)。不要把核准後的施工進度寫回設計文件。

第二道核准在合併、建立版本標籤及發布前。提交是否允許，依實際取得的答案與程序判定；沒有答覆、選單取消或逾時都不能自行推導為同意。建置子代理需要人的答案時，由主工作階段提問並保存原始答案，見 [pending-questions.md](../plugins/cai/skills/track/references/pending-questions.md)。

## 建立、恢復與記錄

軌道入口見 [track/SKILL.md](../plugins/cai/skills/track/SKILL.md)。新軌道先由 [track_start.py](../plugins/cai/scripts/track_start.py) 決定工作目錄；在 `main`／`master` 預設使用獨立工作樹，`--here` 改為目前工作目錄內開分支。已在功能分支時沿用目前目錄；平台沒有進入工作樹的工具時，程序也會明確回報並改為原地建立。

| 資料 | 含義與讀取方式 |
|---|---|
| `.cai/track/current` | 目前軌道名稱；恢復由 `track_state.py` 解析，不能靠對話記憶猜測 |
| `state.md` | 每個階段一列的現況；合法狀態為空白、`in-progress`、`done`、`skipped` |
| `ledger.jsonl` | 每次嘗試、結果、產物指紋與人工核准；由 `ledger.py` 追加 |
| `implementation-notes.md` | 建置排程、單元狀態、測試與偏差；不放入核准後的設計文件 |
| `pending.md`、`open-items.md` | 待回答決定與尚未解決的發現；依程序透過各自腳本管理 |

狀態表與帳本的結果詞彙分開，不能在狀態欄填入帳本的 `passed` 或 `failed`。舊軌道保留已退役階段的歷史記錄，現行讀取端容忍它們，但新軌道只建立四階段。

每次執行階段前先跑 [preflight.py](../plugins/cai/scripts/preflight.py)；檢查失敗先處理阻擋原因。階段記錄的順序與結果轉換依入口程序，不手工重建帳本。軌道完成或取消由 [track_archive.py](../plugins/cai/scripts/track_archive.py) 歸檔；安全設計證據也必須完整，不能在證據損壞時硬搬目錄。

## 驗證如何成立

邏輯正確性（correctness）優先採用平台內建審查；平台審查失敗或結果不明時，改派獨立審查代理。其餘三個視角為需求符合性（conformance）、測試涵蓋（coverage）、安全（security）。正常路徑是平台審查加三個子代理；退回路徑才有四個審查子代理。嚴重程度與處置見 [finding-severity.md](../plugins/cai/skills/track/references/finding-severity.md)。

測試命令由 [resolve_test_command.py](../plugins/cai/scripts/resolve_test_command.py) 讀取明確設定或專案檔案解析；有多個候選、找不到或設定損壞時依 [test-command.md](../plugins/cai/skills/track/references/test-command.md) 處理，不自己猜命令。只有通過測試並不代表所有驗收條件都完成：

| 驗收層級 | 證明方式 |
|---|---|
| `test`：自動測試 | 對應測試、實際命令與通過數 |
| `local-run`：本機執行 | 啟動已宣告程式、等候就緒、執行檢查並停止子行程 |
| `deployed`：部署後檢查 | 合併前明列需要確認的部署條件 |
| `manual`：人工檢查 | 合併前明列本人需要確認的行為 |

[verify_plan.py](../plugins/cai/scripts/verify_plan.py) 規劃驗收去向並檢查證據清單；[local_run.py](../plugins/cai/scripts/local_run.py) 保存實際執行證據。未執行、缺日誌或舊格式無法對應的條件，須明確列為未驗證，不能由審查文字補成成功。

## 工單與完成

[ticket.py](../plugins/cai/scripts/ticket.py) 將本機狀態投射成同一則遠端留言；本機記錄才是流程來源。留言認領是提醒，不能保證跨機器互斥。發布的提交與合併請求使用 `Refs #<number>`，避免合併時提前關閉工單。

只有 `/cai:track done` 歸檔後，才依本人明確答覆關閉工單；發布階段不關閉。投射或關閉失敗須回報實際狀態，不把外部工具的原始錯誤貼進跨專案帳本。完整順序見 [ticket-mirror.md](../plugins/cai/skills/track/references/ticket-mirror.md)。

分支清理另由 [branch_sweep.py](../plugins/cai/scripts/branch_sweep.py) 處理。遠端分支消失不等於內容已合併；有未推送提交的分支不能直接刪除，備份分支另有保守判準。

對應測試：`test_track_state_gate.py`、`test_merged_design_stage.py`、`test_preflight_build_gate.py`、`test_verify_platform_review_text.py`、`test_verify_plan.py`、`test_local_run.py` 與 `test_ticket_*.py`，均位於 [tests](../tests)。
