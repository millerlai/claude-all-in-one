# 檢查器命令列介面契約

2026-10-27 對照目前程式更新。命令列介面（CLI）指腳本接收參數、輸出結果及結束碼的方式；標準輸出（stdout）供呼叫端讀取，標準錯誤（stderr）放使用錯誤等訊息；探針（probe）是一項回傳通過與否及標籤的檢查。

本文件供維護者使用，只描述下列四支腳本，不替其他檢查器訂規則。原先引用的設計行號與已不存在的設計文件已移除；要改此契約時，先對照腳本的 `main` 與實際呼叫端。

## 共同部分

- 執行檢查後，每項結果以 `PASS ` 或 `FAIL ` 開頭，後面接標籤；標籤可能含換行，不能假定一行就是一項。
- 所有探針通過時結束碼為 `0`，至少一項失敗時為 `2`。
- 結束碼 `2` 不保證執行過檢查：其中兩支也用它表示參數錯誤。
- 不存在或未使用的輸入是否算錯，依腳本而異。

## D1 — 參數錯誤與檢查失敗

| 腳本 | 參數錯誤 | 檢查失敗 | 實作依據 |
|---|---|---|---|
| `options_lint.py` | `2` | `2` | [main](../../plugins/cai/scripts/options_lint.py)，使用標準 `argparse.ArgumentParser` |
| `design_probe.py` | `2` | `2` | [main](../../plugins/cai/scripts/design_probe.py)，使用標準 `argparse.ArgumentParser` |
| `preflight.py` | `1` | `2` | [ArgParser、main](../../plugins/cai/scripts/preflight.py)，也以 `1` 回報未知階段 |
| `provenance.py` | `1` | `2` | [ArgParser、main](../../plugins/cai/scripts/provenance.py) |

`argparse` 是 Python 的參數解析程式庫；後兩支自訂錯誤處理，因此結束碼不同。呼叫端要區分錯誤原因，不能只讀結束碼。

## D2 — 輸出編碼

`options_lint.py`、`preflight.py`、`provenance.py` 在 `main` 將標準輸出與標準錯誤設為 UTF-8，也就是可保存中文等字元的文字編碼。`design_probe.py` 只設定無法編碼字元的替代行為，沒有固定輸出編碼。

`preflight.py` 的 `probe_checks` 仍以 `subprocess.run(..., text=True)` 呼叫 `design_probe.py`，未指定輸出解碼方式，兩端依執行環境處理。修改其中一邊時必須同時檢查呼叫端，不能從其他三支推論它的行為。

## D3 — 摘要不是固定格式

檢查完成時通常印出 `-- <種類>: N probe(s) failed`。`provenance.py` 可能在後面加上修正提示。讀取探針結果時應辨識 `PASS `／`FAIL ` 前綴，不能把摘要當成固定長度的資料列。

## D4 — 標籤可能含多行

`preflight.py` 的 `ledger_attempts` 會在標籤中帶入嘗試記錄的備註，備註可能含換行。要將結果再加工時，應優先使用腳本內回傳的布林值與標籤；逐行解析輸出無法保證保留完整標籤。

## D5 — 輸入不存在

| 腳本 | 未找到輸入時的行為 | 實作依據 |
|---|---|---|
| `options_lint.py` | 輸出 `FAIL draft not readable`，結束碼 `2` | `main` 捕捉讀取或解碼錯誤 |
| `design_probe.py` | 輸出 `FAIL document not found`，結束碼 `2` | `main` 的檔案存在檢查 |
| `provenance.py` | 缺少、無法讀取或沒有條目的來源紀錄視為未使用；沒有輸出，結束碼 `0` | `main` 的提早返回 |
| `preflight.py` | 由階段與探針決定；合法缺席可通過，必要產物缺失則阻擋 | 各階段函式與 `main` |

## 誰呼叫哪一支

| 情境 | 檢查器 | 現行呼叫位置 |
|---|---|---|
| 工作流程某階段能否開始 | `preflight.py` | [工作流程技能](../../plugins/cai/skills/track/SKILL.md) 的階段開工程序；`preflight.py` 的 `STAGES` 選擇檢查 |
| 設計文件形狀 | `design_probe.py` | `preflight.py` 的 `probe_checks`，以及 [設計程序](../../plugins/cai/skills/track/references/stage-design.md) |
| 選項草稿是否有六欄 | `options_lint.py` | `preflight.py` 的 `options_drafts` 在同一行程呼叫 `probes`；[待答問題程序](../../plugins/cai/skills/track/references/pending-questions.md) 亦直接呼叫腳本 |
| 規則的引文與重述是否仍成立 | `provenance.py` | [審查程序](../../plugins/cai/skills/track/references/stage-verify.md) Step 0.5，以及 `scripts/validate.py` |

## 選項草稿的路徑約定

`preflight.py` 的 `options_drafts` 為每項第一層待決事項（Tier 1）尋找 `<track-dir>/options-<id>.md`。`<track-dir>` 是該工作流程目錄，`<id>` 由標題第一個詞保留英數字與 `_`、`.`、`-` 後取得；沒有可用字元時退回項目位置。清理後識別碼相同的兩項會失敗，不能共用一份草稿冒充兩份。

它也支援單份 `-design.md` 內的 `Decisions` 章節；舊 `-detail.md` 的上游草稿由 `tier1_drafts` 尋找。早於本次工作流程的已決事項可依記錄日期沿用。完整判斷以 [options_drafts 與 tier1_drafts](../../plugins/cai/scripts/preflight.py) 為準。
