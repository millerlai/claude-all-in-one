# 安全與檢查

核對日期：2026-11-02。術語：守門腳本（guard）拒絕已知危險呼叫；事件掛鉤（hook）在平台事件發生時執行；命令殼層（shell）會解讀引號、展開與串接；參數陣列（argv）是傳給程式的逐項輸入；指紋（SHA-256）偵測位元組是否改變，本身不證明作者身分。

## 命令與寫入防護

[hooks.json](../plugins/cai/hooks/hooks.json) 將命令工具與寫入工具交給 [run-guard.cmd](../plugins/cai/hooks/run-guard.cmd)，再由 [bash_guard.py](../plugins/cai/scripts/bash_guard.py) 判斷。範圍包括危險版本控制操作、受保護分支、殼層展開、子代理寫入流程帳本，以及特定工具的命令限制。

防護依賴平台提供的工具名稱、代理身分與呼叫內容。它不是完整的作業系統隔離，也不能認證主工作階段寫入的核准一定來自真人；間接執行、未涵蓋的命令形狀與環境權限仍有邊界。沒有可工作的直譯器時，各入口的退路也不同，不能概稱全部拒絕或全部放行。現行降級判準見 [run-guard.cmd](../plugins/cai/hooks/run-guard.cmd)、[runner_guard.py](../plugins/cai/scripts/runner_guard.py) 與 [完整參考](../REFERENCE.md)。

命令中的引號與展開在不同殼層不相同；多行訊息使用檔案傳入，避免把內容當作程式執行。檔案放進暫存目錄不會自動取得網路、瀏覽器或受保護路徑的權限。防護與輸出遮蔽的回歸案例位於 [tests](../tests) 的 `test_bash_guard_*.py`、`test_long_run_hint.py`（放行時的背景提醒，以及它不改變任何判定）與 [validate.py](../scripts/validate.py)。

## 背景長跑提醒

2026-11-27 核對。[bash_guard.py](../plugins/cai/scripts/bash_guard.py) 在 Claude Code 上放行一個會啟動背景工作的呼叫時，會透過附加脈絡（additionalContext，hook 加進模型可見內容的一段文字）送出一句固定提醒，內容是 [epistemics.md](../plugins/cai/rules/epistemics.md) 的「Exploring and measuring: small first」規則；規則的來由（#499）見 [rule-provenance.md](rule-provenance.md)。判斷由 [long_run_hint.py](../plugins/cai/scripts/long_run_hint.py) 負責，算是背景工作的有三種：`run_in_background` 為真的 Bash 或 PowerShell 呼叫、帶指令的 Monitor 呼叫，以及指令自己把工作丟到背景（Bash 的單獨 `&`、`nohup`、`setsid`、`disown`、`start /b`；PowerShell 的 `Start-Process`、`Start-Job`、`Start-ThreadJob`、它們的別名，以及敘述中段或結尾的 `&`）。比對前會先遮蔽引號內容、註解、heredoc 內文與 `${…}`，讀的是原始指令，不是守門腳本合併續行後的文字。

這句提醒不擋任何事，理由有三：
- 一個指令會跑多久，從指令本身看不出來，只有讀過程式碼的模型知道。
- 若在每次背景啟動都跳出確認，開發伺服器與監看指令也會被問，守門腳本最後會被整個關掉。
- 提醒區塊位在所有拒絕與詢問判定之後，輸出只有附加脈絡、沒有權限決定，所以不會改變任何判定。

在 Codex 上（`CAI_CODEX_GUARD=1`），守門腳本不輸出這句提醒。

提醒文字是一個不超過 500 字元的固定 ASCII 常數，不含指令內容，避免命令裡的文字冒充平台訊息。措辭是條件式的事實陳述（「asks to start … If it runs」），因為它在 Claude Code 自己的權限檢查之前送出，被拒絕的呼叫也會收到；命令式的措辭則可能被模型當成可疑的注入。

邊界：
- 提醒隨工具結果送達，長跑當時已經開始，所以只能要求模型事後停掉。
- 模型仍可能忽略提醒，啟動前唯一起作用的是規則本身。
- WebSocket 監看、守門腳本退回降級檢查時，以及前景指令逾時後被平台移到背景時，都沒有提醒。
- 判斷過程中的任何例外都會被吞掉，守門腳本仍以 0 結束；寫入失敗時，標準輸出會改指向空裝置，避免結束時重試寫入失敗而回傳 120，被 [run-guard.cmd](../plugins/cai/hooks/run-guard.cmd) 當成封鎖。

對應測試在 [test_long_run_hint.py](../tests/test_long_run_hint.py)，其中 1 MB 的刻意構造指令驗證判斷維持線性時間。

## 設計階段的安全證據

[threat-modeling.md](../plugins/cai/skills/track/references/threat-modeling.md) 與 [security_design.py](../plugins/cai/scripts/security_design.py) 是現行契約：

1. 判定安全分析是否適用，保存理由與來源；未知不能當成不適用。
2. 適用時記錄資產、信任邊界、攻擊路徑、控制與驗收條件。需要承擔的風險必須取得對該風險的具體答案，一般設計核准不能代替。
3. 凍結設計、獨立需求及依賴的原始位元組，取得另一個唯讀架構分析代理（architect）的完整回覆；作者不能自行宣告獨立審查成功。
4. 主工作階段核對原始回覆、發現、假設、限制與影響；`ready` 檢查通過後才進人工核准。
5. 建置前以 `resume` 檢查核准與證據仍有效。允許修改的是核准範圍內的原實作；仍生效的限制與快照不能悄悄改寫。

紀錄位於 `.cai/design-security/`。原回覆、依賴快照或來源缺失時，保存原產物並恢復真實證據，不能補造歷史核准。舊設計豁免也需要真實的舊流程、核准與相同產物三項證明。此機制檢查證據的一致性與新鮮度，不認證惡意工作區管理者或模型所寫的身分聲明。對應 [test_security_design.py](../tests/test_security_design.py) 與 [test_track_archive.py](../tests/test_track_archive.py)。

## 四個檢查器的介面

命令列介面（CLI）的輸出、結束碼與錯誤處理由各支程式決定，不能用一個全域假設解析所有工具。

| 檢查器 | 用途 | 參數錯誤 | 檢查失敗 |
|---|---|---|---|
| [options_lint.py](../plugins/cai/scripts/options_lint.py) | 選項草稿的六欄形狀 | `2` | `2` |
| [design_probe.py](../plugins/cai/scripts/design_probe.py) | 依種類檢查設計形狀與引用 | `2` | `2` |
| [preflight.py](../plugins/cai/scripts/preflight.py) | 階段開工條件、核准與產物 | `1` | `2` |
| [provenance.py](../plugins/cai/scripts/provenance.py) | 硬性規則引文與重述 | `1` | `2` |

執行過檢查時，每項結果以 `PASS ` 或 `FAIL ` 開頭，所有項目通過為 `0`；但標籤可含換行，摘要也不是固定格式。`provenance.py` 遇到來源帳本缺席或沒有條目時可無輸出且回 `0`，不能據此聲稱已檢查引文。

`options_lint.py`、`preflight.py`、`provenance.py` 在入口固定標準輸出與錯誤的文字編碼為 UTF-8；`design_probe.py` 的編碼處理不同。維護時必須一起看 `preflight.py` 的 `probe_checks` 呼叫端，不從其他工具推論解碼行為。

同一主題的單份設計也支援決策草稿檢查。清理後識別碼相同的兩項第一層決策不能共用一份草稿；探針檢查的是形狀與引用，不證明語意或風險判斷正確。

## 規則來源

[rule-provenance.md](rule-provenance.md) 保存硬性規則背後的失敗，而非所有偏好。修改被引用的規則原句時，必須同時更新來源條目；不能只調整引文使檢查變綠。實際驗證由 [provenance.py](../plugins/cai/scripts/provenance.py) 與 [validate.py](../scripts/validate.py) 執行。
