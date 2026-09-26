# Glossary

This file is only a glossary — one or two sentences per term, no decisions
or specs, and only concepts specific to this project.

## Language

<!--
  Example: `**Term**: one or two sentences saying what it is.` A `_Avoid_`
  line naming synonyms not to use can go under a term by hand afterwards —
  build never writes one.
-->

**審查基準（benchmark）**: `tests/review-benchmark/` 下一組已知有缺陷的改動，搭配計分器和量測程序，用來量測審查 agent 抓不抓得到。
**case 目錄**: 審查基準裡的一個子目錄，只放 `diff.patch`（有缺陷的改動的 diff）和 `expected.json`（標註）。
**計分器**: 拿 finding 跟標註比對 lens、檔名、行號（容忍 ±3 行）的程式（`scripts/review_benchmark_score.py`）。
**審查基準量測程序（review-benchmark procedure）**: 把一筆 case 變成可計分紀錄的九個步驟（`scripts/review-benchmark-procedure.md`）。
**合規審查鏡（conformance lens）**: verify 階段四個審查 agent 之一，比對改動有沒有符合書面需求和慣例檔。
**慣例檔（convention file）**: `<top>/CLAUDE.md` 和 `<top>/.claude/CLAUDE.md` 當中實際存在的那些檔案。
