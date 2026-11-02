# 觀察與量測

核對日期：2026-11-02。術語：工作軌道（track）保存單項功能；僅追加帳本（append-only ledger）保存不可覆寫的嘗試；逐行資料格式（JSONL）以每行一筆結構化資料儲存；用量單位（token）計算模型輸入與輸出；逐字紀錄（transcript）是平台留下的事件來源。

## 帳本與資料可靠性

[ledger.py](../plugins/cai/scripts/ledger.py) 保存嘗試、時間、結果、產物原始位元組指紋與核准類型。`state.md` 只保留階段現況，不能代替歷次嘗試。

- 跨專案副本同步失敗不抹除本機記錄；同步狀態與錯誤有大小限制。
- 每筆記錄有位元組上限；縮減順序先處理備註、用量問題清單與逐模型明細，產物路徑最後才縮短。路徑用來重新找到核准產物，不能提早犧牲。
- 讀取逐行資料時只依換行字元（LF）切行，避免把字串中合法的 U+0085、U+2028、U+2029 拆成假壞行。
- 真正損壞的行保留診斷位置。目前帳本讀取端遇到檔案缺席或讀取錯誤都回傳空記錄；這是既有觀察限制，不能把空報表當成沒有歷史嘗試或花費的證據。

回歸依據：[test_ledger.py](../tests/test_ledger.py)、[test_ledger_usage.py](../tests/test_ledger_usage.py)、[test_ledger_central.py](../tests/test_ledger_central.py)、[test_preflight_build_gate.py](../tests/test_preflight_build_gate.py)。

## 用量與等值支出

[usage_collector.py](../plugins/cai/scripts/usage_collector.py) 從逐字紀錄取得主工作階段與子代理用量。相同請求只計一次，分段回覆取最大已觀察輸出；缺少請求識別或來源無法讀取時，明列問題而非填零。

[usage_report.py](../plugins/cai/scripts/usage_report.py) 提供單軌道、時間區間與階段指標報表。模型定價表與個人覆寫分開；未知模型維持未定價，不能當免費。快取讀取與不同存活時間的快取寫入分開計算。報表金額是等值程式介面支出（equivalent API spend），訂閱帳戶不代表按該金額實際計費。

資料起始日之前是「沒有資料」，不是零使用；不把未量測區間納入平均後宣稱變省。對應測試見 `test_usage_collector.py`、`test_prices.py`、`test_report.py` 及 `test_metrics.py`，均位於 [tests](../tests)。

## 四個流程指標

| 指標 | 定義與解讀 |
|---|---|
| 首次通過（first_pass） | 該階段第一次嘗試是否通過；跨軌道報表合計分子與分母 |
| 週期（cycle） | 從第一次階段記錄到最後通過的時間；整條軌道另列，不把階段時間直接相加 |
| 重工（rework） | 嘗試次數；連續且同指紋的通過記錄依程式規則合併 |
| 人工簽核占比（human_signed） | 帶人工關卡記錄的嘗試占比；不是整個系統已強制真人授權的證明 |

沒有嘗試的階段顯示未適用，不拉低平均。舊帳本保留六階段原始記錄，但現行報表會把退役的需求盤點與探索記錄併入設計，以四階段彙總；歷史原始輸出與現行彙總不能直接比較。歷史基線與限制見 [評估依據](evaluation.md)。

## 脈絡與執行時間

[context_peak.py](../plugins/cai/scripts/context_peak.py) 量測單次請求的脈絡占用峰值：輸入加快取讀取與快取寫入，不把新產生的輸出算成當下輸入。脈絡窗口預設值是工具參數，不是所有模型容量的保證；比占用率時須使用該模型實際窗口。

[timing.py](../plugins/cai/scripts/timing.py)、[timing_hook.py](../plugins/cai/scripts/timing_hook.py) 與 [timing_report.py](../plugins/cai/scripts/timing_report.py) 處理階段及工具事件時間。時間、用量與流程是否通過是不同訊號，不能互相代替。

## 代理工作檢視頁

[viewer.py](../plugins/cai/scripts/viewer.py) 提供本機工作檢視頁（Agent Viewer），預設位址為 `127.0.0.1:7788`。它顯示兩平台主工作階段、待回答／工作中／完成狀態、軌道進度與時間，支援英文、繁體中文及主題切換。頁面負責顯示，回答仍回原對話。

存活判斷會核對平台行程與紀錄，不能僅以行程數猜測工作階段數。背景代理未結束時也不能把主工作階段直接顯示成完成；Claude Code 的已知背景事件與結束狀態由封閉清單辨識，未知新欄位不自動算背景工作。Codex 與 Claude Code 的資料來源不同，顯示有觀察延遲，也不是排程或授權來源。

啟動與停止方式以 [viewer 技能](../plugins/cai/skills/viewer/SKILL.md) 為準。回歸測試包括 [test_viewer_codex.py](../tests/test_viewer_codex.py)、[test_viewer_liveness.py](../tests/test_viewer_liveness.py) 及 [test_viewer_page.py](../tests/test_viewer_page.py)。
