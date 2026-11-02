# 平台對應

核對日期：2026-11-02。術語：Anthropic 的程式代理平台為 Claude Code；OpenAI 的程式代理平台為 Codex；命令列工具（CLI）接收終端機指令；產生器（generator）從主要來源轉換對應套件；啟動器（launcher）尋找已安裝套件並呼叫腳本。

## 來源與產生

[gen-codex.py](../scripts/gen-codex.py) 從 `plugins/cai/` 產生 `plugins/cai-codex/`，套用 [codex-overrides.json](../scripts/codex-overrides.json)、[codex-models.json](../scripts/codex-models.json) 及模型映射。不逐檔維護兩份相同程序。

只有產生器 `HAND_WRITTEN` 明列的檔案可手動修改：安裝器、啟動器、設定／模型／檢視頁技能及其平台描述檔，以及對應套件說明。精確清單以程式常數為準；不要複製舊版清單或數量。

維護檢查：

```text
python scripts/gen-codex.py
python scripts/gen-codex.py --check
```

本專案以單一版本同時發布兩套外掛。版本來源、相容性與不可移動標籤規則見 [CONTRIBUTING.md](../CONTRIBUTING.md) 與 [README.md](../README.md#compatibility)，不沿用早期獨立版號方案。

## 安裝、更新與命令

| 項目 | Claude Code | Codex |
|---|---|---|
| 技能語法 | `/cai:<name>` | `$<name>` |
| 出貨位置 | `plugins/cai/` | `plugins/cai-codex/` |
| 個人規則入口 | 設定技能複製到 `~/.claude/rules/` | 安裝器寫入個人 `AGENTS.md` 的管理區塊 |
| 腳本定位 | 平台提供外掛根目錄 | 固定啟動器尋找平台快取 |
| 專案狀態 | 共用 `.cai/` 格式 | 共用 `.cai/` 格式 |

精確安裝與更新命令、最低版本、所需權限與平台限制，直接讀 [中文首頁](../README.zh-TW.md#安裝)、[Codex 說明](../plugins/cai-codex/README.md)，此處不重複固定會變動的版本數字。

Codex 的 [install_codex.py](../plugins/cai-codex/scripts/install_codex.py) 依序處理固定啟動器、代理設定、掛鉤、個人規則區塊，保留其不擁有的內容。寫入採同目錄暫存檔再替換，既有規則檔有備份；這不代表整組安裝是單一交易。

[launcher.py](../plugins/cai-codex/scripts/launcher.py) 在執行一般腳本前檢查已安裝代理與套件版號；不相符時要求重新設定。掛鉤與計時入口有自己的退路，不能把一般腳本的阻擋規則套到所有入口。安裝掛鉤後仍須由平台信任才能生效。

## 模型與推理投入

具體模型由平台設定、帳戶可用清單與個人選擇共同決定。模型名稱不是角色，也不增加工具權限；`chore`、`build`、`think` 分別代表機械工作、工程實作與設計取捨。

主要來源為 [models.json](../plugins/cai/models.json)、[model_choice.py](../plugins/cai/scripts/model_choice.py)、[Codex 模型設定](../scripts/codex-models.json) 及安裝器。個人映射與推理投入由設定／模型技能管理；不要手改產生的代理標頭。讀不到模型能力或個人設定損壞時，依實際入口回報，不能默默宣告模型已切換成功。

## 平台差異與界線

- 兩平台共用軌道格式不等於已證明跨平台途中接手的每種情境；目前限制仍見對應套件說明。
- 一般選單只使用當前模式可用的提問工具；無工具時列編號文字並等回答，不能用未答覆當核准。
- 用量報表依賴平台逐字紀錄的欄位。Codex 產生套件排除部分用量工具，精確範圍見產生器的 `EXCLUDE_FILES`；共用狀態不代表所有觀察能力等價。
- 工作區寫入權不涵蓋個人設定、網路或受保護版本控制資料。安裝與發布仍服從平台的實際核准機制。

對應測試： [test_gen_codex.py](../tests/test_gen_codex.py)、[test_codex_install.py](../tests/test_codex_install.py)、[test_codex_launcher.py](../tests/test_codex_launcher.py)、[test_codex_readme.py](../tests/test_codex_readme.py)。
