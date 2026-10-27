# codex-model-fallback — detail design

## 維護說明（2026-10-27）

本檔是歷史設計紀錄，保留決策、驗收依據與實作偏差；不是待執行計畫。原簽核狀態、版本、行號及未驗證標記描述撰寫當時，整併不代表重新簽核或重做實測。

名詞：設計立場（stance）說明取捨；決策紀錄（decisions）保存選擇理由；細部設計（detail）記錄建造規格；需求盤點（intake）保存驗收條件。下方英文標題與識別碼沿用原文，便於對照歷史。

模型偵測與儲存選擇仍在使用，見 [`plugins/cai-codex/scripts/install_codex.py:526`](../../plugins/cai-codex/scripts/install_codex.py#L526)。原模型名稱與預設值是當時快照。另併入 Claude Code 說明文件的歷史立場；其中「不提供角色切換」已不適用，現有角色設定見 [`plugins/cai/skills/models/SKILL.md:12`](../../plugins/cai/skills/models/SKILL.md#L12)；兩個平台的歷史假設不可互相套用。

已併入並移除的同主題文件：`2026-09-22-codex-model-fallback-decisions.md`、`2026-09-22-codex-model-fallback-stance.md`、`2026-09-22-model-fallback-readme-stance.md`。

補充段落保留原文與原決策編號，避免把不同時點同號的決策當成一項；重複的概覽圖、施工排程與階段交接文字不再複製。

## Reference

Stance doc: docs/design/2026-09-22-codex-model-fallback-detail.md
Decisions doc: docs/design/2026-09-22-codex-model-fallback-detail.md
Status: approved 2026-09-22

- Gate checked in the files on 2026-09-22: the stance's `## Status` reads `approved 2026-09-22` (`docs/design/2026-09-22-codex-model-fallback-detail.md:883`) and its `## Use cases / Issues` numbers UC1-UC5 and R1-R2 (`:49-55`). Every decisions `## Tier 1` entry has a `Decided:` line: D1 (`docs/design/2026-09-22-codex-model-fallback-detail.md:813`), D2 (`:132`), D3 (`:164`). G1 and G2 each carry a `**Chosen:**` note (`:61`, `:62`).
- Intake: `.claude/track/codex-model-fallback/intake.md`. AC1-AC9 are at `:66-93`.
- Decisions this document builds on, and does not re-open: D1=A, the installer reads `$CODEX_HOME/models_cache.json` and nothing else. D2=A, a run with no arguments installs everything and a second run happens only when an answer changes something. D3=A, answers travel in a JSON file. G1 keeps keep as the default and adds a mark. G2 puts the saved choice under `$CODEX_HOME`. D4-D15 stand as written.
- **Marked "chosen by the person 2026-09-22 (P1-P4)"** means a question this round handed up; the person answered each one as proposed (`.claude/track/codex-model-fallback/options-detail-P1.md` … `-P4.md`).

### Traceability

| From the high-level design | Satisfied by | Status |
|---|---|---|
| UC1 | Run 1 with no saved choice writes shipped bytes (`install_agents` with `contents` absent for unsaved roles), prints the mapping block and `ask: keep-or-switch`. Keep means no apply run. Tested by `test_cli_keep_with_nothing_saved_leaves_agents_byte_identical`. | covered |
| UC2 | `offer <role>:` lines hold only detected, listed slugs that pass the charset check, marked `in effect` and `cai default`. The apply run rewrites that role's TOMLs, and a role left at its default stays byte-identical (D6). | covered |
| UC3 | The saved choice lives in `$CODEX_HOME/cai-model-choice.json` (G2, M7), and run 1 applies it before printing. Tested against a copied `<cai-root>` with a new stamp. | covered |
| UC4 | `RolePlan.reask` and the `ask again <role>:` line. The default answer is the first entry of the `offer` order. | covered |
| UC5 | `Detection.reason` holds one of three reasons. `ask: nothing` means every role is saved; `ask: keep-or-type <roles>` means some are not. A typed name is checked only against the charset (AC7). | covered |
| R1 | Switching a role replaces the pinned slug in every TOML on that role. The G1 `not offered` line flags an unsaved role whose default is missing. | covered |
| R2 | The README gains a detection row with status `unverified` and a description of the saved-choice file (AC9). | covered |

## Requirement

On Codex, each cai role (chore, build, think) is pinned to one model slug in every shipped `agents/cai_*.toml` (`plugins/cai-codex/agents/cai_explorer.toml:4-5`). An account that cannot use a pinned slug cannot dispatch any agent on that role (R1). `$setup` must show each role's model and effort, ask keep or switch, and offer only slugs the account's model list shows. It saves the per-role choice where a plugin update cannot erase it and applies it on every later `$setup`. Every rule that decides what gets written sits in `install_codex.py`, with a `tests/test_codex_install.py` case (stance M6, `docs/design/2026-09-22-codex-model-fallback-detail.md:909`).

This is done when AC1-AC9 (`intake.md:66-93`) each have a passing test at the level `## Verification` names, and a live Codex `$setup` run shows the mapping and asks. No CI can check that live run (`.github/workflows/validate.yml:8`, `:16-18`).

## Glossary

| Term | Definition | Where it lives |
|---|---|---|
| role | One of `chore`, `build`, `think`: the key an agent is assigned under. | plugins/cai-codex/models.json:24 |
| role's agents | The `cai_<x>.toml` names whose source `agents/<x>.md` is assigned to that role in `<cai-root>/models.json`. | plugins/cai-codex/models.json:39 |
| cai default | For a role, the `model =` and `model_reasoning_effort =` values on lines 4-5 of the role's shipped TOMLs, as the generator writes them. | scripts/gen-codex.py:424 |
| role's own effort | The cai default's effort for that role. It is the starting point of the effort fallback. | plugins/cai-codex/agents/cai_explorer.toml:5 |
| `<cai-root>` | The installed cai-codex tree the installer runs from: the grandparent of its own file. | plugins/cai-codex/scripts/install_codex.py:46 |
| `$CODEX_HOME` | The `CODEX_HOME` environment variable if set, else `~/.codex`. | plugins/cai-codex/scripts/install_codex.py:60 |
| detection | One read of `$CODEX_HOME/models_cache.json`, which gives the offered slugs, their effort lists, and either success or a reason for failure. | new — plugins/cai-codex/scripts/install_codex.py (`detect`) |
| offered slug | A catalog slug whose `visibility` is `list` and which matches the slug pattern (D5, D7). | new — plugins/cai-codex/scripts/install_codex.py (`Detection.offered`) |
| slug pattern | `^[a-z0-9][a-z0-9.-]{0,63}$`. Every slug is matched against it before it is written or saved (D7, M4). | new — plugins/cai-codex/scripts/install_codex.py (`SLUG_RE`) |
| saved choice | The role → slug map in the saved-choice file. A role with no entry follows the cai default. | new — plugins/cai-codex/scripts/install_codex.py (`load_choice`) |
| saved-choice file | `$CODEX_HOME/cai-model-choice.json` (chosen by the person 2026-09-22 — P1). | new — `$CODEX_HOME/cai-model-choice.json` |
| answers file | `$CODEX_HOME/cai-model-answers.json` (chosen by the person 2026-09-22 — P1). `SKILL.md` writes it and the apply run consumes it. | new — `$CODEX_HOME/cai-model-answers.json` |
| slug in effect | For a role: its saved slug if one exists, else its cai default. | concept |
| re-ask | A role whose saved slug is not offered by a successful detection (AC4, D5). | new — plugins/cai-codex/scripts/install_codex.py (`RolePlan.reask`) |
| G1 mark | The `not offered <role>:` line printed for an unsaved role whose cai default is not offered by a successful detection. | new — plugins/cai-codex/scripts/install_codex.py (`render_mapping`) |
| offer order | A role's offered slugs in this order: the slug in effect if offered, then the cai default if offered, then the rest in catalog order. | new — plugins/cai-codex/scripts/install_codex.py (`RolePlan.offer`) |
| effort fallback | The rule that picks the effort written beside a chosen slug (D8, AC5). | new — plugins/cai-codex/scripts/install_codex.py (`fallback_effort`) |
| header region | The bytes of a TOML before its first line starting `developer_instructions = `. Lines 1-6 in every shipped TOML. | scripts/gen-codex.py:421 |
| stamp line | Line 1, `# cai-codex-version: <v>`, which the launcher compares with the plugin version. | plugins/cai-codex/scripts/launcher.py:29 |
| mapping block | The lines run 1 prints after its existing output: `models:`, `role`, `offer`, `ask again`, `not offered`, `ask:`, `answers file:`. | new — plugins/cai-codex/scripts/install_codex.py (`render_mapping`) |
| ask directive | The single `ask: ...` line, which tells `SKILL.md` which questions to ask. | new — plugins/cai-codex/scripts/install_codex.py (`ask_directive`) |
| run 1 | `install_codex.py` with no arguments: today's full install, the saved choice applied, the mapping block printed. | plugins/cai-codex/scripts/install_codex.py:288 |
| apply run | `install_codex.py --apply`: it validates the answers file, saves the choice, and rewrites the agents. | new — plugins/cai-codex/scripts/install_codex.py (`apply_answers`) |
| format version | The integer `format` key in both JSON files. It is `1` in this design (D10). | new — plugins/cai-codex/scripts/install_codex.py (`FORMAT`) |

## Budgets

| What | Number | Where it comes from |
|---|---|---|
| Roles | 3 | `plugins/cai-codex/models.json:24-36` |
| Installed agent TOMLs, total (chore / build / think) | 10 (3 / 5 / 2) | `plugins/cai-codex/models.json:40-58`; directory listing of `plugins/cai-codex/agents/`, 2026-09-22 |
| Catalog models, and how many are offered today | 7 models, 5 offered | decisions C1, `docs/design/2026-09-22-codex-model-fallback-detail.md:757` |
| Cache file size, read whole with `json.loads` | 232290 bytes | `os.path.getsize` on `C:/Users/millerlai/.codex/models_cache.json`, 2026-09-22 |
| Installer runs per `$setup` that exit 0 | at most 2 (retries across interpreters, `SKILL.md:43-46`, not counted) | D2, `decisions.md:126` |
| Subprocesses or network calls made by the installer | 0 | D1, `decisions.md:89` |
| Lines that may differ between a rewritten TOML and the shipped one | at most 2 | M3, `stance.md:28` |
| Header-region lines searched for the two anchors | 6 | `scripts/gen-codex.py:421-427` |
| Maximum slug length | 64 characters | D7, `decisions.md:182` |
| Effort levels ranked | 6 | C22, `decisions.md:43` |
| Format version of both JSON files | 1 | D10, `decisions.md:194` |
| Questions a keep answer costs, with no re-ask | 1 | AC1, `intake.md:66-67` |
| Questions a switch answer costs | 4 (1 + 3 roles) | AC2, `intake.md:69` |
| Options per role question today | 5 | the offered count above. UNVERIFIED: whether Codex's `request_user_input` renders 5 options. If it does not, `SKILL.md` falls back to numbered text, as step 3 already does (`plugins/cai-codex/skills/setup/SKILL.md:50-55`). |

## Design decisions

1. **Detection reads the cache file and nothing else** (D1=A; serves AC2, AC6). `detect` opens `codex_home() / "models_cache.json"` (`install_codex.py:60-62`). It never runs `codex`, so CI's Linux job with no `codex` binary exercises it through a fake file (C19, `decisions.md:40`). Whether the file follows `CODEX_HOME` is UNVERIFIED (C3, `decisions.md:24`). If it does not, detection reports `missing` under a custom home, and AC6's path applies. That is loud, never a wrong write (M1).
2. **Run 1 installs everything and applies the saved choice** (D2=A; serves AC1, AC3). The four existing steps keep their order (`install_codex.py:293-334`). Step 2 now writes rewritten bytes for saved roles. The mapping block prints last, after `guard:` (`:338`), so every line an existing test looks for is still printed (`tests/test_codex_install.py:247-248`).
3. **The apply run takes no path; it reads the fixed answers file** (narrows D3=A's `--apply <path>`, chosen by the person 2026-09-22 — P2; serves AC7 and "who is allowed to do what"). Two reasons. A path typed into a PowerShell line is the C15/C16 exposure D3 exists to avoid (`decisions.md:36-37`). And the apply run deletes the file it read, so accepting any path would let a mistyped argument delete an arbitrary file.
4. **Validate everything before writing anything; then write the saved file, then the agents, then delete the answers file** (serves M1 and "partial `--apply`"). An apply that fails partway leaves a saved file that the next run 1 converges every agent to. The answers file survives a failure, so re-running `--apply` repeats the same writes. The Implementation spec's apply diagram shows the order.
5. **Nothing is written before the saved file parses** (D10; C20 precedent `install_codex.py:216-223`, `:316-318`). Run 1 loads the saved choice and computes every agent's bytes before step 1 writes the launcher. That is stricter than `hooks.json`'s handling, which fails after the launcher and agents are already written (`:294-318`), because a bad saved file would otherwise decide what the agents get.
6. **Keep/switch comes first; re-asked roles after** (serves AC1 and AC4 together; low cost, only `SKILL.md`). On keep, `SKILL.md` asks only the `ask again` roles. On switch it asks all three roles (AC2), and a re-asked role's first option is its AC4 default answer, because the stale slug is not offered and the offer order puts the cai default, or else the first detected slug, first.
7. **The G1 mark is its own line, repeated verbatim in setup's report** (G1 veto, `decisions.md:61`). The sample is under the mapping-printer component. It is printed only for an unsaved role, because a saved role missing from detection already gets its `ask again` line.
8. **The rewrite is anchored in the header region and keeps line endings** (M3, D11; serves AC2). The two patterns run only on the bytes before `developer_instructions = `, so a line inside the instructions that happens to start with `model = ` cannot be matched (`scripts/gen-codex.py:427`). The line terminator is preserved, so a TOML that some checkout gave CRLF keeps CRLF. Whether Codex's plugin cache stores LF or CRLF is UNVERIFIED, and this decision makes that irrelevant.
9. **Defaults come from the shipped TOMLs, never from `scripts/codex-models.json`** (cross-project invariant, `stance.md:37`). A role's default is read from the first of its agents in sorted order. Every TOML on a role carries the same pair, because the generator writes one tier per role (`scripts/gen-codex.py:417`, `:424-425`).
10. **Only `visibility == "list"` is offered** (D5, `decisions.md:174`). A model with no `visibility` key is not offered. That is the strict reading, and it never offers something hidden.
11. **Unknown effort names are ignored when ranking** (D8). A `supported_reasoning_levels` entry outside the six names is dropped. If nothing is left, the list counts as missing, so the role's own effort is kept (`intake.md:80-83`).
12. **The README gets a fourth status value, `unverified`** (AC9 says "UNVERIFIED today", `intake.md:92-93`; chosen by the person 2026-09-22 — P3). Today's legend allows three values (`plugins/cai-codex/README.md:70-73`) and a test enforces them (`tests/test_codex_readme.py:15`, `:47-53`). No existing value fits: the cache is not documented (C2), so it is not "documented, not tested".
13. **A leftover answers file is removed at the start of run 1** (serves M1). An abandoned setup can leave one behind. Removing it keeps a later `--apply` from applying answers the user gave in an earlier session.
14. **Released as 0.2.0** (AC8; chosen by the person 2026-09-22 — P4). `main` publishes 0.1.1 (`scripts/codex-release.json:2`), and `--release` refuses a version at or below it (`scripts/gen-codex.py:584-591`). This change adds a CLI flag and a user-facing question, which is why the proposal is a minor bump rather than 0.1.2.

## Diagrams

### Architecture

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart LR
  U["User"]:::existing
  subgraph CODEX["Codex session"]
    S["setup SKILL.md (model reads it): asks, writes answers file"]:::modified
  end
  subgraph ROOT["cai-root (plugin cache, read-only here)"]
    MJ["models.json assignments"]:::existing
    TS["agents/cai_*.toml shipped"]:::existing
    I["scripts/install_codex.py: detect, plan, validate, save, rewrite"]:::modified
  end
  subgraph CH["CODEX_HOME"]
    MC["models_cache.json (Codex writes it)"]:::existing
    SC["cai-model-choice.json"]:::added
    AF["cai-model-answers.json"]:::added
    AG["agents/cai_*.toml installed"]:::modified
    HK["hooks.json, AGENTS.md"]:::existing
  end
  L["HOME/.codex/cai/launcher.py: reads line 1 stamp"]:::existing
  U -- "answers" --> S
  S -- "run 1, then --apply" --> I
  I -- "mapping block on stdout" --> S
  S -- "file-edit tool" --> AF
  MJ --> I
  TS --> I
  MC -- "read only" --> I
  AF -- "read, then deleted" --> I
  I -- "read, write" --> SC
  I -- "write" --> AG
  I -- "write, unchanged logic" --> HK
  I -- "write, unchanged" --> L
  L -- "stamp check" --> AG
  classDef added fill:#d4edda,stroke:#28a745,color:#155724
  classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404
  classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057
```

What to look at: the two green files are both inside `CODEX_HOME`, and both are separate from the four files the installer writes wholesale. That placement is M7 plus G2. The only arrow from `SKILL.md` into a file points at the answers file. Every other write comes from `install_codex.py` (M6).

### Component

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TD
  M["main(argv): run 1 or --apply"]:::modified
  D["detect(chome) -> Detection"]:::added
  LC["load_choice(chome) -> dict"]:::added
  RA["role_agents(root), shipped_defaults(root, agents)"]:::added
  P["plan_roles(...) -> dict of RolePlan, ask_directive(...) -> str"]:::added
  RD["read_answers(chome, roles, detection) -> dict"]:::added
  MG["merge_answers(saved, answers, defaults) -> dict"]:::added
  AB["agent_bytes(root, plans, detection) -> dict of bytes"]:::added
  RW["rewrite_model_lines(toml, model, effort) -> bytes"]:::added
  FE["fallback_effort(own, levels) -> str"]:::added
  SV["save_choice(chome, roles) -> Path"]:::added
  IA["install_agents(root, home, contents=None)"]:::modified
  RM["render_mapping(plans, detection, chome, full) -> list of str"]:::added
  EX["install_launcher, install_hooks, install_agents_md"]:::existing
  M --> D
  M --> LC
  M --> RA
  M --> RD
  RD --> MG
  M --> P
  P --> AB
  AB --> RW
  AB --> FE
  M --> SV
  M --> IA
  M --> EX
  M --> RM
  classDef added fill:#d4edda,stroke:#28a745,color:#155724
  classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404
  classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057
```

What to look at: every green box except `save_choice` is a pure function, taking values and returning values. So the rules M1-M4, AC4 and AC5 are unit-testable without a file system. Only `main`, `save_choice` and `install_agents` write. `install_agents` is amber because it gains one optional parameter and keeps its existing two-argument call (`tests/test_codex_install.py:90`).

### Flow

```mermaid
---
config:
  flowchart:
    defaultRenderer: "elk"
---
flowchart TD
  A["SKILL step 2: run installer, no arguments"]:::modified
  B{"saved file parses and every anchor found?"}:::added
  X["exit 1, nothing written, SKILL quotes it"]:::added
  C["install launcher, agents with saved slugs, hooks, AGENTS.md"]:::modified
  E["print mapping block"]:::added
  F{"ask directive"}:::added
  G["ask keep or switch"]:::added
  H["switch: ask chore, build, think from offer lines"]:::added
  K["keep: ask only the ask-again roles"]:::added
  T["ask keep or type, per listed role, with warning"]:::added
  N["nothing to ask, saved choice reused"]:::added
  Q{"any role answered with a slug?"}:::added
  W["write answers file at printed path"]:::added
  AP["run installer --apply"]:::added
  V{"answers valid against a fresh detection?"}:::added
  R["exit 1, names the role and reason, answers file kept"]:::added
  SV["save choice, rewrite agents, delete answers file"]:::added
  Z["SKILL report: models line, not-offered lines, re-run sentence"]:::modified
  A --> B
  B -- "no" --> X
  B -- "yes" --> C --> E --> F
  F -- "keep-or-switch" --> G
  G -- "switch" --> H --> Q
  G -- "keep" --> K --> Q
  F -- "keep-or-type" --> T --> Q
  F -- "nothing" --> N --> Z
  Q -- "no" --> Z
  Q -- "yes" --> W --> AP --> V
  V -- "no" --> R
  V -- "yes" --> SV --> Z
  classDef added fill:#d4edda,stroke:#28a745,color:#155724
  classDef modified fill:#fff3cd,stroke:#ffc107,color:#856404
  classDef existing fill:#e9ecef,stroke:#adb5bd,color:#495057
```

What to look at: the four-way branch at `ask directive` is computed by the installer, not by `SKILL.md`. The prose only follows the line it was handed (D4). `Q` is the reason D2=A keeps a plain keep to one run. It asks only whether a slug was given, never whether the slug differs, so the comparison stays in the installer. The two red-path exits, `X` and `R`, both leave a consistent install behind.

### Sequence — UC1

```mermaid
sequenceDiagram
  actor User
  participant S as setup SKILL.md
  participant I as install_codex.py
  participant H as CODEX_HOME
  S->>I: run 1, no arguments
  I->>H: read models_cache.json (5 offered)
  I->>H: read cai-model-choice.json (absent, nothing saved)
  I->>H: write launcher, agents as shipped bytes, hooks.json, AGENTS.md
  I-->>S: role lines marked cai default, offer lines, ask keep-or-switch
  S->>User: show mapping, ask keep or switch, keep first
  User->>S: keep
  S-->>User: report, no apply run
```

What to look at: nothing is written after the user answers. With nothing saved, "keep" is a single installer run whose agent bytes equal the shipped ones (AC1, M2).

### Sequence — UC2

```mermaid
sequenceDiagram
  actor User
  participant S as setup SKILL.md
  participant I as install_codex.py
  participant H as CODEX_HOME
  S->>I: run 1
  I-->>S: mapping block, ask keep-or-switch
  S->>User: keep or switch
  User->>S: switch
  S->>User: chore, from offer chore line
  User->>S: gpt-5.6-luna (cai default)
  S->>User: build, from offer build line
  User->>S: gpt-5.6-sol
  S->>User: think, from offer think line
  User->>S: gpt-5.6-terra (cai default)
  S->>H: write cai-model-answers.json, roles chore, build, think
  S->>I: --apply
  I->>H: read cache, saved file, answers file
  I->>I: every slug offered and matches the pattern, every anchor found once
  I->>H: write cai-model-choice.json with build only
  I->>H: write agents, build TOMLs name gpt-5.6-sol, others shipped bytes
  I->>H: delete cai-model-answers.json
  I-->>S: role lines, applied
```

What to look at: choosing the cai default for chore and think saves nothing for them (D6). Only `build` lands in the saved file, and only build's five TOMLs differ from the shipped ones.

### Sequence — UC3

```mermaid
sequenceDiagram
  actor User
  participant S as setup SKILL.md
  participant I as install_codex.py (new cai-root)
  participant H as CODEX_HOME
  Note over H: a plugin update left agents stamped with the old version, and the launcher exits 3 (existing)
  S->>I: run 1
  I->>H: read cai-model-choice.json, build gpt-5.6-sol
  I->>H: write agents from the new cai-root, new stamp on line 1, build lines 4-5 rewritten
  I-->>S: role build gpt-5.6-sol (saved, cai default gpt-5.6-terra), ask keep-or-switch
  S->>User: keep or switch
  User->>S: keep
  S-->>User: report, no apply run
```

What to look at: the saved choice is applied by run 1 itself, so keep after an update needs no apply run. And line 1 now carries the new stamp, so the launcher stops exiting 3 (M3, `plugins/cai-codex/scripts/launcher.py:204-210`).

### Sequence — UC4

```mermaid
sequenceDiagram
  actor User
  participant S as setup SKILL.md
  participant I as install_codex.py
  participant H as CODEX_HOME
  S->>I: run 1
  I->>H: read cache (gpt-reserve now hidden), saved build gpt-reserve
  I->>H: write agents, build keeps gpt-reserve until answered
  I-->>S: ask again build, default answer gpt-5.6-terra, then ask keep-or-switch
  S->>User: keep or switch
  User->>S: keep
  S->>User: build again, gpt-5.6-terra first
  User->>S: gpt-5.6-terra
  S->>H: write answers file, build gpt-5.6-terra
  S->>I: --apply
  I->>H: remove build from saved file, build TOMLs back to shipped bytes
  I-->>S: role lines, applied
```

What to look at: between run 1 and the apply run, the build TOMLs still name the stale slug the user once chose (D2=A, M1 holds). Answering with the cai default removes the saved entry, so the TOMLs go back to byte-identical.

### Sequence — UC5

```mermaid
sequenceDiagram
  actor User
  participant S as setup SKILL.md
  participant I as install_codex.py
  participant H as CODEX_HOME
  S->>I: run 1
  I->>H: read models_cache.json, missing
  I->>H: read saved file, think saved, chore and build not
  I->>H: write agents, think saved slug, others shipped bytes
  I-->>S: models detection failed with reason, ask keep-or-type chore build
  S->>User: chore, keep or type a name, warning it cannot be checked
  User->>S: keep
  S->>User: build, keep or type a name
  User->>S: types gpt-5.6-sol
  S->>H: write answers file, build gpt-5.6-sol
  S->>I: --apply
  I->>I: detection still failed, so the pattern check only, effort stays medium
  I->>H: save build, rewrite build TOMLs
  I-->>S: role lines, applied
```

What to look at: think is never asked, because a saved choice is reused without asking when detection fails (AC6). The typed name is checked only against the pattern, never against a list, and its effort is the role's own (AC5, AC7).

## Implementation spec

Shared constraints for every block below. Standard library only. `from __future__ import annotations` goes at the top, so the builtin-generic hints below are never evaluated on an older Python 3. The minimum Python version a user's `$setup` runs is UNVERIFIED (`plugins/cai-codex/README.md:10-14` says only "Python 3"). Records use `typing.NamedTuple`, as `scripts/gen-codex.py:35` does. Every file write goes through `_atomic_write_bytes` (`install_codex.py:65-75`). New module constants:

```python
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max", "ultra")
MODELS_CACHE_NAME = "models_cache.json"
CHOICE_NAME = "cai-model-choice.json"      # chosen by the person 2026-09-22 (P1)
ANSWERS_NAME = "cai-model-answers.json"    # chosen by the person 2026-09-22 (P1)
FORMAT = 1
```

### Detection — `detect`

- **Responsibility:** turn `$CODEX_HOME/models_cache.json` into the offered slugs and their effort lists, or a failure reason.
- **Interface:**
  ```python
  class Detection(NamedTuple):
      ok: bool
      reason: str                       # "" when ok
      source: Path
      offered: tuple[str, ...]          # catalog order
      levels: dict[str, tuple[str, ...]]  # offered slug -> known efforts, catalog order
      total: int                        # catalog entries with a str slug
      ignored: int                      # listed slugs dropped by SLUG_RE
      fetched_at: str | None
  def detect(chome: Path) -> Detection
  ```
- **Data in:** the cache as C1 describes it (`decisions.md:22`): a top-level object with `models`, a list of objects each with `slug` (str), `visibility` (str), and `supported_reasoning_levels` (a list of objects with `effort`, a str). `fetched_at` is an optional str.
- **Errors:** never raises for cache content. `reason` is exactly one of three strings. `"<path> is missing"` when the file does not exist. `"<path> cannot be parsed: <why>"` for `OSError`, `UnicodeDecodeError` or `json.JSONDecodeError`, for a top level that is not an object, for `models` that is not a list, or for an entry that is not an object. `"<path> lists no offered models"` when `offered` is empty after filtering (D14). An entry whose `slug` is not a str is skipped, not fatal. It is counted in neither `total` nor `offered`.
- **Concurrency:** read-only. Codex may rewrite the file at any moment. `json.loads` of a whole read is then either the old or the new content, or a parse failure, which counts as a failure reason. The apply run re-detects rather than trusting run 1's result (decision 4).
- **Observability:** none by itself. `render_mapping` prints its result.
- **Where it lives:** `plugins/cai-codex/scripts/install_codex.py`, new function. The file exists today.
- **What it reuses:** `codex_home()` (`install_codex.py:60-62`); `json` (`:40`).

### Saved choice — `load_choice`, `save_choice`

- **Responsibility:** read and write the role → slug map that survives plugin updates.
- **Interface:**
  ```python
  class ChoiceParseError(Exception): ...   # file exists but is not a valid saved choice
  def load_choice(chome: Path) -> dict[str, str]      # {} when the file is absent
  def save_choice(chome: Path, roles: dict[str, str]) -> Path
  ```
- **Data:** `$CODEX_HOME/cai-model-choice.json`, UTF-8, no BOM, LF. It is written as `json.dumps(obj, indent=2, sort_keys=True) + "\n"`, the same way `install_hooks` writes (`install_codex.py:236-237`). Sample, one role saved:
  ```json
  {
    "format": 1,
    "roles": {
      "build": "gpt-5.6-sol"
    }
  }
  ```
  `save_choice` with an empty map writes `"roles": {}`. It never deletes the file.
- **Errors:** `load_choice` raises `ChoiceParseError(f"{path}: {why}")` for any of these: unreadable or undecodable, invalid JSON, top level not an object, `format` not the integer `1`, `roles` not an object, a value not a str, or a value failing `SLUG_RE`. The caller exits 1 with `invalid saved model choice, not overwritten: <message>` before any write (decision 5). `save_choice` lets `OSError` propagate.
- **Concurrency:** single writer per `$CODEX_HOME` is assumed. Two concurrent `$setup` runs on one home end with whichever apply run wrote last. Each write is atomic (`os.replace`), so the file is never torn. There is no lock, because no requirement names concurrent setups.
- **Observability:** the apply run prints `saved <path>`.
- **Where it lives:** `install_codex.py`, new.
- **What it reuses:** `_atomic_write_bytes` (`install_codex.py:65-75`); the refuse-to-overwrite precedent of `HooksParseError` (`:52-53`, `:216-223`).

### Role map — `role_agents`, `shipped_defaults`

- **Responsibility:** name each role's installed agents, and read each role's cai default from the shipped TOMLs.
- **Interface:**
  ```python
  def role_agents(root: Path) -> dict[str, list[str]]
      # {"chore": ["cai_explorer.toml", "cai_shipper.toml", "cai_test-runner.toml"], ...}
  def shipped_defaults(root: Path, agents: dict[str, list[str]]) -> dict[str, tuple[str, str]]
      # {"chore": ("gpt-5.6-luna", "low"), ...}
  ```
- **Data:** `role_agents` reads `root/models.json`. Its role order is the key order of `roles` (`plugins/cai-codex/models.json:24-36`). Each `assignments` key of the form `agents/<x>.md` maps to `cai_<x>.toml` (`:39-60`, C12), and only files that exist under `root/agents/` are kept, in sorted order. Keys under `skills/` are ignored. `shipped_defaults` reads the first sorted TOML of each role and extracts the two values with the same header-region patterns `rewrite_model_lines` uses.
- **Errors:** a missing or unparsable `root/models.json` raises. The caller exits 1 with `cannot read <path>: <why>`. That cannot happen in a generated tree (`scripts/gen-codex.py:435-440`), but it is cheap to report. An anchor miss raises `AnchorError`, below.
- **Concurrency:** reads the plugin cache only.
- **Observability:** none.
- **Where it lives:** `install_codex.py`, new.
- **What it reuses:** the `assignments` → `cai_` naming of `scripts/gen-codex.py:422`, `:476-480`. Nothing from `scripts/codex-models.json`, which is not shipped (`stance.md:37`).

### Planner — `plan_roles`, `ask_directive`

- **Responsibility:** decide, per role, the slug in effect, whether it is re-asked, whether it gets the G1 mark, and its offer order, and decide which questions `SKILL.md` asks.
- **Interface:**
  ```python
  class RolePlan(NamedTuple):
      role: str
      agents: tuple[str, ...]
      default_model: str
      default_effort: str
      in_effect: str          # saved slug, else default_model
      saved: bool
      effort: str             # fallback_effort(default_effort, levels.get(in_effect))
      reask: bool             # detection.ok and saved and in_effect not in offered
      unlisted_default: bool  # detection.ok and not saved and default_model not in offered
      offer: tuple[str, ...]  # () when not detection.ok
  def plan_roles(agents: dict[str, list[str]], defaults: dict[str, tuple[str, str]],
                 detection: Detection, saved: dict[str, str]) -> dict[str, RolePlan]
  def ask_directive(plans: dict[str, RolePlan], detection: Detection) -> str
  ```
- **Data:** `offer` = `[in_effect]` if offered, then `default_model` if offered and different, then the remaining offered slugs in catalog order. So `offer[0]` is AC4's default answer for a re-asked role (`intake.md:76-79`). A saved role name that is not in `agents` is dropped from the plan. `main` prints one `ignored saved role <name>: cai-codex has no such role` line for it (D13). `ask_directive` returns exactly one of these strings: `"ask: keep-or-switch"` when `detection.ok`; `"ask: keep-or-type <r1> <r2> ..."` when detection failed, listing the unsaved roles in role order; `"ask: nothing"` when detection failed and every role is saved.
- **Errors:** none. Pure.
- **Concurrency:** pure.
- **Observability:** through `render_mapping`.
- **Where it lives:** `install_codex.py`, new.
- **What it reuses:** `fallback_effort`, below.

### Line rewriter — `rewrite_model_lines`, `fallback_effort`

- **Responsibility:** produce a TOML whose only differences from the shipped one are the `model =` and `model_reasoning_effort =` values.
- **Interface:**
  ```python
  class AnchorError(Exception): ...   # an anchor missing or repeated in the header region
  def rewrite_model_lines(toml: bytes, model: str, effort: str) -> bytes
  def fallback_effort(own: str, levels: tuple[str, ...] | None) -> str
  ```
- **Data:** `rewrite_model_lines` splits `toml` at the first match of `rb"^developer_instructions = "` (multiline). If that line is absent, the whole file is the header. In the header it finds `rb'^model = "[^"\r\n]*"(?=\r?$)'` and `rb'^model_reasoning_effort = "[^"\r\n]*"(?=\r?$)'` (multiline), and each must match exactly once. It replaces each match with `model = "<model>"` or `model_reasoning_effort = "<effort>"`. Any `\r` stays outside the replaced span, so line endings survive. Before writing, `model` must match `SLUG_RE` and `effort` must be in `EFFORT_ORDER`; neither contains `"` or `\`, so no escaping is needed (C14, `decisions.md:35`). Line 1 is never inside a match. `fallback_effort` works on `known = [l for l in levels if l in EFFORT_ORDER]`. It returns `own` if `levels` is None or `known` is empty (a typed name or an unlisted slug), else `own` if `own in known`, else the highest-ranked entry of `known` that ranks below `own`, else the lowest-ranked entry of `known` (D8).
- **Errors:** `AnchorError(f"{name}: {which} found {n} times")`. `ValueError` for a model or effort that fails its check. That cannot happen from validated inputs, but it is kept so M4 does not rest on callers alone. The caller exits 1 with `cannot rewrite <path>: <message>` before any write.
- **Concurrency:** pure.
- **Observability:** none.
- **Where it lives:** `install_codex.py`, new.
- **What it reuses:** the line shape of `scripts/gen-codex.py:424-425`. It does not import `_toml_string` (`:406-407`), because `gen-codex.py` is Ours and not shipped.

### Agent bytes and `install_agents`

- **Responsibility:** compute every installed TOML's bytes, then write them.
- **Interface:**
  ```python
  def agent_bytes(root: Path, plans: dict[str, RolePlan]) -> dict[str, bytes]
      # every shipped cai_*.toml name -> bytes; unsaved roles' files are the shipped bytes
  def install_agents(root: Path, home: Path, contents: dict[str, bytes] | None = None)
      # unchanged return: (written paths, removed paths)
  ```
- **Data:** a saved role's files become `rewrite_model_lines(shipped, plan.in_effect, plan.effort)`. Every other file is `p.read_bytes()`, unchanged. In `install_agents`, `contents=None` keeps today's behaviour exactly (`install_codex.py:93-114`). With a map, it writes `contents[p.name]` in place of `p.read_bytes()`, and removes stale files as today.
- **Errors:** `AnchorError` from `agent_bytes` happens before any write. `OSError` during writing propagates as today (`:304-308`).
- **Concurrency:** idempotent. The same inputs give the same bytes.
- **Observability:** `wrote <path>` and `removed <path>` per file, as today (`:309-312`).
- **Where it lives:** `install_codex.py`. `agent_bytes` is new; `install_agents` is modified.
- **What it reuses:** `install_agents` itself.

### Mapping printer — `render_mapping`

- **Responsibility:** print the roles and the questions in a form both a person and `SKILL.md` can read line by line.
- **Interface:**
  ```python
  def render_mapping(plans: dict[str, RolePlan], detection: Detection, chome: Path,
                     full: bool) -> list[str]   # full=True for run 1, False for the apply run
  ```
- **Data:** the lines, in this order (the prefixes are chosen by the person 2026-09-22 — P1):
  1. `models: detected <len(offered)> of <total> from <source> (fetched <fetched_at>)`, or `models: detection failed: <reason>`. The `(fetched ...)` part is omitted when `fetched_at` is None.
  2. `models: ignored <n> slug(s) outside [a-z0-9.-]`, only when `ignored > 0`.
  3. One line per role: `role <role>: <in_effect> / <effort> (<tag>) -- <agent names without .toml, comma-separated>`. `<tag>` is `cai default`, or `saved; cai default <default_model>`.
  4. When `full` and `detection.ok`, one line per role: `offer <role>: <slug>[ (<marks>)], ...`, in offer order. `<marks>` is `in effect`, `cai default`, or `in effect, cai default`.
  5. One line per re-asked role: `ask again <role>: saved <in_effect> is not offered by this detection; default answer <offer[0]>`.
  6. One line per G1 role: `not offered <role>: <in_effect> is in effect but this detection does not list it`.
  7. When `full`: `ask_directive(...)`, then `answers file: <chome / ANSWERS_NAME>`.
  8. When not `full`: `applied: <n> role(s) saved`.

  Sample: run 1 against the real 2026-09-22 cache, build saved as `gpt-reserve` (now hidden), everything else default. The paths are elided.
  ```
  models: detected 5 of 7 from ...\.codex\models_cache.json (fetched 2026-09-22T08:13:21.014621200Z)
  role chore: gpt-5.6-luna / low (cai default) -- cai_explorer, cai_shipper, cai_test-runner
  role build: gpt-reserve / medium (saved; cai default gpt-5.6-terra) -- cai_implementer, cai_refactoring-detector, cai_reviewer, cai_security-reviewer, cai_verifier
  role think: gpt-5.6-terra / high (cai default) -- cai_architect, cai_designer
  offer chore: gpt-5.6-luna (in effect, cai default), gpt-5.6-sol, gpt-6-astra, gpt-5.6-terra, gpt-5.5
  offer build: gpt-5.6-terra (cai default), gpt-5.6-sol, gpt-6-astra, gpt-5.6-luna, gpt-5.5
  offer think: gpt-5.6-terra (in effect, cai default), gpt-5.6-sol, gpt-6-astra, gpt-5.6-luna, gpt-5.5
  ask again build: saved gpt-reserve is not offered by this detection; default answer gpt-5.6-terra
  ask: keep-or-switch
  answers file: ...\.codex\cai-model-answers.json
  ```
  A G1 line, for an account whose cache lacks terra and with nothing saved: `not offered think: gpt-5.6-terra is in effect but this detection does not list it`.
- **Errors:** none. Every slug printed has passed `SLUG_RE`, or came from the shipped TOML or the validated saved file, so no printed line can carry a newline or a quote (D7).
- **Concurrency:** pure.
- **Observability:** this is the observability, and `SKILL.md` quotes it in the report.
- **Where it lives:** `install_codex.py`, new.
- **What it reuses:** the `<verb> <path>` line style of `main` (`install_codex.py:298-338`).

### Answers reader — `read_answers`, `merge_answers`

- **Responsibility:** validate what `SKILL.md` wrote, and fold it into the saved choice.
- **Interface:**
  ```python
  class AnswersError(Exception): ...
  def read_answers(chome: Path, roles: tuple[str, ...], detection: Detection) -> dict[str, str]
  def merge_answers(saved: dict[str, str], answers: dict[str, str],
                    defaults: dict[str, tuple[str, str]]) -> dict[str, str]
  ```
- **Data in:** `$CODEX_HOME/cai-model-answers.json`. Same shape as the saved file, listing only the roles the user answered:
  ```json
  {"format": 1, "roles": {"build": "gpt-5.6-sol"}}
  ```
  `merge_answers` starts from `saved`, then for each answered role: if the slug equals that role's `default_model`, the entry is removed (D6); otherwise the entry is set.
- **Errors:** `AnswersError` carries a message the caller prints after `answers not applied: `, and the process exits 1. The file is kept and nothing is written. The messages, one per failing check: `<path> is missing`; `<path> cannot be parsed: <why>` (invalid JSON, not an object, `format` not `1`, `roles` not an object); `unknown role <repr(name)>`; `rejected <role>: <repr(value)> is not a model name (allowed: ^[a-z0-9][a-z0-9.-]{0,63}$)` (AC7; `repr` so that a newline prints as `\n`); `rejected <role>: <slug> is not offered by this detection; re-run $setup`, when `detection.ok` and the slug is not offered. Checks run in the order listed, so a slug reaches the offered check only after passing the pattern, and every printed slug is pattern-clean. When detection failed, a slug that matches the pattern is accepted as typed (AC6).
- **Concurrency:** if the cache changed between run 1 and the apply run, a slug the user picked may now be rejected. That is the last message above, and it is intended (M1).
- **Observability:** the `AnswersError` line on failure; `removed <path>` once the file is deleted on success.
- **Where it lives:** `install_codex.py`, new.
- **What it reuses:** `SLUG_RE`; `json` (`:40`).

### Entry point — `main`, `apply_answers`

- **Responsibility:** run the install run or the apply run, in an order where a failure leaves a state the next run converges from.
- **Interface:**
  ```python
  def main(argv: list[str] | None = None) -> int   # argparse; "--apply" store_true
  def apply_answers(root: Path, chome: Path) -> int
  ```
  An unknown argument exits 2 through argparse. The existing docstring's exit-code line (`install_codex.py:29-30`) gains `2 bad arguments`.
- **Run 1 order:** (a) `detect`, `load_choice`, `role_agents`, `shipped_defaults`, `plan_roles`, `agent_bytes`. Any error here exits 1 before anything is written. (b) If an answers file exists, delete it and print `removed stale <path>` (decision 13). (c) The existing steps 1-4 (`:293-334`), with `install_agents(root, chome, contents)`. (d) The existing `rules:` and `guard:` lines. (e) The `ignored saved role` lines, then `render_mapping(..., full=True)`.
- **Apply order:**

  ```mermaid
  ---
  config:
    flowchart:
      defaultRenderer: "elk"
  ---
  flowchart LR
    V["validate: detect, load_choice, read_answers, merge, agent_bytes"]:::added
    E1["exit 1, nothing written"]:::added
    S1["write cai-model-choice.json"]:::added
    S2["write every cai_*.toml"]:::added
    E2["exit 1: re-run $setup to finish, answers file kept"]:::added
    S3["delete cai-model-answers.json"]:::added
    P["print role lines, applied"]:::added
    V -- "any error" --> E1
    V -- "ok" --> S1
    S1 -- "OSError" --> E2
    S1 --> S2
    S2 -- "OSError" --> E2
    S2 --> S3 --> P
    classDef added fill:#d4edda,stroke:#28a745,color:#155724
  ```

  What to look at: the saved file is written before any agent. So after a failure at `S2`, the saved file holds the user's new choice. The next run 1, or a repeat of `--apply` since the answers file was kept, rewrites every agent from it. A failure deleting the answers file at `S3` is reported (`could not remove <path>: <why>`) but the exit code is still 0, because run 1 removes a leftover answers file anyway (decision 13).
- **Errors:** `write failed: <path>: <why>` followed by `re-run $setup to finish`, exit 1. `apply_answers` does not touch the launcher, `hooks.json` or `AGENTS.md`, so setup step 3's language edit (`plugins/cai-codex/skills/setup/SKILL.md:57-69`) is never overwritten.
- **Concurrency:** re-running `--apply` after any failure is safe. Every write is a full-file atomic replace computed from the same inputs. A Codex dispatch that starts while the apply run is writing agents may see some of a role's TOMLs already switched and others not. Each file is whole, and the next dispatch sees them all, so there is no lock.
- **Observability:** `saved <path>`, the `wrote <path>` lines, `removed <path>`, the role and `not offered` lines, and `applied: <n> role(s) saved`.
- **Where it lives:** `install_codex.py`. `main` is modified; `apply_answers` is new.
- **What it reuses:** `main`'s per-step `try/except OSError` shape (`:293-334`).

### `skills/setup/SKILL.md` — step 2 and step 5

- **Responsibility:** ask exactly what the ask directive says, and hand the answers to the installer. It holds no rule about what gets written (M5, M6).
- **Interface (the behaviours the prose must carry):**
  1. Step 2 runs the installer exactly as today (`SKILL.md:16-46`), then reads the mapping block from its output.
  2. It shows the `role` lines to the user as the current mapping. Every `ask again` and `not offered` line is shown on its own line.
  3. It follows the `ask:` line. For `keep-or-switch`: one question, keep (first, the default) or switch. On switch, one question per role in the order chore, build, think, whose options are that role's `offer` line in order, first option first. On keep, one question per `ask again` role, options from its `offer` line. For `keep-or-type <roles>`: one question per listed role, keep (first, the default) or type a model name, with the sentence "setup cannot check a typed name against your account". For `nothing`: no question, and the report says the saved choice was reused and why.
  4. Menus follow the rule step 3 already states: use a menu tool if one is available, else numbered text (`SKILL.md:50-55`).
  5. If no role was answered with a slug (every answer was keep, or nothing was asked), it runs nothing more. It does not compare answers with the slug in effect; whether an answer changes anything is the installer's call (`merge_answers`). Otherwise it writes the answers file at the path on the `answers file:` line, with the file-edit tool, as `{"format": 1, "roles": {<role>: <slug>, ...}}`, with one entry for every role asked a question this run and answered with a slug; a role answered "keep" gets no entry. It then runs the installer again with `--apply` placed right after the script path, and on Windows inside the pipeline, before `2>&1` (`SKILL.md:38`), using the interpreter that just succeeded. A non-zero exit from `--apply` is quoted to the user and not retried with another interpreter, because the answers, not the interpreter, are what failed.
  6. Step 5, the report, adds: the `models:` line; every `not offered` line, verbatim (G1); which roles were saved; and this sentence (chosen by the person 2026-09-22 — P1): "If a cai agent later fails to start with a model error, re-run `$setup` and switch that role."
- **Errors:** the installer's own messages are quoted. The prose never decides whether a slug is acceptable.
- **Concurrency:** not applicable, because one Codex session runs one `$setup`.
- **Observability:** the report.
- **Where it lives:** `plugins/cai-codex/skills/setup/SKILL.md`, which exists. It is hand-written (`scripts/gen-codex.py:80`).
- **What it reuses:** step 2's interpreter loop and Windows pipeline (`SKILL.md:22-46`); step 3's menu rule (`:50-55`).

### `README.md` — AC9

- **Responsibility:** tell users what detection rests on and where their choice is saved.
- **Changes (all chosen by the person 2026-09-22 — P1, P3):**
  - The status legend (`plugins/cai-codex/README.md:70-73`) gains: "`unverified` (what cai relies on here is neither described in Codex's documentation nor guaranteed to stay as observed; it may change with a Codex update)".
  - A new mapping row after the per-agent model pin row (`:78`):
    `| Choosing a model per role (chore/build/think) | `$setup` reads the model list Codex keeps for your account in `$CODEX_HOME/models_cache.json`, offers only the models it lists, and saves your per-role choice in `$CODEX_HOME/cai-model-choice.json`, which every later `$setup` re-applies | unverified | observed with codex-cli 0.155.1 on Windows 11, 2026-09-22: the file lists each model's slug, whether it is shown or hidden, and its supported reasoning efforts. It is not described in Codex's documentation, so a Codex update may move or reshape it; setup then says it could not read the list and offers to keep the current models or type a name, rather than guessing. Whether the list leaves out models a restricted account cannot use was not checked. |`
  - A Usage paragraph after "After every plugin update" (`:52-54`): "**Choosing models.** `$setup` shows which model each cai role runs on and asks whether to keep or switch, offering only models your account's model list shows. It checks that list only while it runs: if a cai agent later fails to start with a model error, re-run `$setup` and switch that role."
  - An Uninstall bullet (`:103-111`): "- `$CODEX_HOME/cai-model-choice.json` — your saved per-role model choice."
- **Where it lives:** `plugins/cai-codex/README.md`, which exists and is hand-written (`scripts/gen-codex.py:82`).
- **What it reuses:** the row format and evidence voice of `:78`.

## Naming

| Name | What it is | Chosen by |
|---|---|---|
| `$CODEX_HOME/cai-model-choice.json` | the saved-choice file | directory: the person, 2026-09-22 (G2, `decisions.md:62`); file name: chosen by the person 2026-09-22 (P1) |
| `$CODEX_HOME/cai-model-answers.json` | the answers file | directory follows G2; file name: chosen by the person 2026-09-22 (P1) |
| `--apply` (takes no value) | the apply run's flag | flag name follows D2/D3's own wording (`decisions.md:110`, `:157`); dropping the path argument is chosen by the person 2026-09-22 (P2) |
| `format` (integer, value `1`), `roles` (object) | the two top-level keys of both JSON files | chosen by the person 2026-09-22 (P1); D10 asks for "a format-version key and a role→slug map" (`decisions.md:194`) |
| `models:`, `role <r>:`, `offer <r>:`, `ask again <r>:`, `not offered <r>:`, `ask: keep-or-switch`, `ask: keep-or-type <roles>`, `ask: nothing`, `answers file:`, `applied:` | mapping-block line prefixes and ask-directive values | chosen by the person 2026-09-22 (P1) |
| `in effect`, `cai default`, `saved; cai default <slug>` | marks and tags inside mapping lines | `in effect` and "cai's default" follow AC2's wording (`intake.md:70-71`); exact spelling chosen by the person 2026-09-22 (P1) |
| `unverified` | the fourth README status value | AC9's "UNVERIFIED today" (`intake.md:92-93`); spelling in lower case follows the existing values (`plugins/cai-codex/README.md:70-73`); adding it is chosen by the person 2026-09-22 (P3) |
| `0.2.0` | the cai-codex release version | must be greater than `main`'s 0.1.1 (`scripts/codex-release.json:2`, `scripts/gen-codex.py:584-591`); the value is chosen by the person 2026-09-22 (P4) |
| `SLUG_RE`, `EFFORT_ORDER`, `MODELS_CACHE_NAME`, `CHOICE_NAME`, `ANSWERS_NAME`, `FORMAT` | module constants | follows the upper-case constant style of `install_codex.py:46-49` |
| `Detection`, `RolePlan`, `ChoiceParseError`, `AnswersError`, `AnchorError` | records and exceptions | follows `HooksParseError`/`MarkerError` (`install_codex.py:52-57`) and `NamedTuple` use in `scripts/gen-codex.py:35` |
| `detect`, `load_choice`, `save_choice`, `role_agents`, `shipped_defaults`, `plan_roles`, `ask_directive`, `rewrite_model_lines`, `fallback_effort`, `agent_bytes`, `render_mapping`, `read_answers`, `merge_answers`, `apply_answers` | new functions | follows the `install_<thing>` verb-first snake_case style of `install_codex.py:82`, `:93`, `:216` |
| test function names in `## Verification` | new pytest cases | builder's, following `test_<unit>_<behaviour>` in `tests/test_codex_install.py:65`, `:80`, `:225` |

## Change points

| Path | Change | Exists today |
|---|---|---|
| `plugins/cai-codex/scripts/install_codex.py` | New constants, records and functions as above; `install_agents` gains `contents`; `main` gains argparse, `--apply`, pre-write validation and the mapping block; docstring updated (usage, step 2, exit codes). Hand-written (`scripts/gen-codex.py:79`). | yes |
| `plugins/cai-codex/skills/setup/SKILL.md` | Step 2 gains the mapping, the questions and the apply run; step 5 gains the models line, the G1 lines, and the re-run sentence. Hand-written (`scripts/gen-codex.py:80`). | yes |
| `plugins/cai-codex/README.md` | Legend value, mapping row, Usage paragraph, Uninstall bullet. Hand-written (`scripts/gen-codex.py:82`). | yes |
| `tests/test_codex_install.py` | New unit and CLI cases (`## Verification`); a fake-cache helper beside `fake_env` (`:44-53`). | yes |
| `tests/test_codex_readme.py` | `STATUSES` gains `"unverified"` (`:15`). The launcher-path check narrows from `"$CODEX_HOME/cai"` to `"$CODEX_HOME/cai/"` (`:127`), because `$CODEX_HOME/cai-model-choice.json` contains the shorter string while the test means the launcher directory (docstring `:123-124`). One new test pins the detection row's status. | yes |
| `scripts/codex-release.json`, `plugins/cai-codex/agents/cai_*.toml` (line 1), `plugins/cai-codex/.codex-plugin/plugin.json` | Rewritten by `python scripts/gen-codex.py --release 0.2.0` (`scripts/gen-codex.py:647-651`, `:695-702`). | yes |
| `plugins/cai/`, `scripts/gen-codex.py`, `plugins/cai-codex/scripts/launcher.py` | unchanged (AC8, stance cross-project I1) | yes |

No new dependency: `re`, `json`, `argparse`, `typing` and `pathlib` are all in the standard library.

## Failure modes

| Situation | What happens | What the caller sees |
|---|---|---|
| Cache file missing (including a custom `CODEX_HOME` the cache does not follow, C3) | detection fails; saved roles reused; unsaved roles offered keep or type | `models: detection failed: <path> is missing`, then `ask: keep-or-type ...` or `ask: nothing` |
| Cache unparsable or reshaped by a Codex update (C2) | same as missing | `models: detection failed: <path> cannot be parsed: <why>` |
| Cache lists only hidden models | same as missing (D14) | `... lists no offered models` |
| A catalog slug outside the pattern | dropped from `offered` | `models: ignored 1 slug(s) outside [a-z0-9.-]` |
| Saved file unparsable, wrong format, or a bad slug | exit 1 before any write; file kept | `invalid saved model choice, not overwritten: <path>: <why>`; `SKILL.md` quotes it and stops (`SKILL.md:43-46`) |
| Saved role that no longer exists | ignored | `ignored saved role <name>: cai-codex has no such role` |
| Saved slug no longer offered | applied until answered; role re-asked | `ask again <role>: ...` |
| Unsaved role whose default is not offered | installed as shipped; marked | `not offered <role>: ...`, repeated in setup's report |
| Anchor missing or repeated in a shipped TOML | exit 1 before any write | `cannot rewrite <path>: model found 0 times` |
| Answers file missing when `--apply` runs (file-edit tool could not write there, C17) | exit 1, nothing written | `answers not applied: <path> is missing` |
| Answers file malformed, unknown role, bad or unoffered slug | exit 1, nothing written, file kept | `answers not applied: rejected build: 'x"y' is not a model name (...)` |
| Cache refreshed between run 1 and the apply run, so an answered slug disappears | exit 1, nothing written | `answers not applied: rejected build: gpt-x is not offered by this detection; re-run $setup` |
| Write fails after the saved file, while agents are being written | saved file already holds the new choice; some agents rewritten | `write failed: <path>: <why>` then `re-run $setup to finish`, exit 1 |
| Answers file cannot be deleted after success | choice applied; file left for run 1 to remove | `could not remove <path>: <why>`, exit 0 |
| An account can use fewer models than the cache lists (C9) | offered anyway; the user finds out at dispatch | the README row says this was not checked; the report's re-run sentence says what to do |
| User abandons after run 1 | install consistent; a re-asked role keeps its stale saved slug | nothing further; next `$setup` asks again |

## Rollout

- **In pieces?** The build lands in units (`## Work breakdown`), but ships as one release. `SKILL.md` and the installer must agree on the mapping grammar and `--apply`, and both reach users together in one plugin version. There is no flag: a user with nothing saved, pressing keep, gets exactly today's agents (M2).
- **Existing data:** none to migrate. Before this change there is no saved-choice file, so every existing install is in the "nothing saved" state. The format version (`1`) exists so that a later format change has something to branch on (D10).
- **In flight:** users on 0.1.1 who update get the existing exit-3 refusal until they re-run `$setup` (`plugins/cai-codex/scripts/launcher.py:204-210`, `README.md:52-54`). That run is the new one. A user who downgrades to 0.1.1 gets the old installer, which never reads the saved file: agents go back to shipped bytes and the file is left unused. That is harmless and listed under Uninstall.
- **Release step (AC8):** the last unit runs `python scripts/gen-codex.py --release 0.2.0` (0.2.0 proposed, P4), then `python scripts/gen-codex.py --check` (exit 0), `python scripts/validate.py` (no `FAIL`), and `python -m pytest`. Before recording the release, `git ls-files --eol plugins/cai-codex` must show no `w/crlf`. The fingerprint hashes the on-disk bytes of the hand-written files (`scripts/gen-codex.py:662-669`), and this machine checks out CRLF for any extension `.gitattributes` does not pin. This change adds no new extension: `.py`, `.md`, `.json` and `.toml` are pinned at `.gitattributes:5-10`.
- **Rollback:** revert the commit and release a greater version, say 0.2.1, because `--release` refuses anything at or below the published one (`scripts/gen-codex.py:584-591`). Saved-choice files already on users' machines stay behind, ignored by the old installer. Nothing else was written outside the four files the installer already owns.

## Verification

Seams: every unit-level test calls functions directly on synthetic trees and a fake cache. Every CLI test runs the real script as a subprocess, with `HOME`, `USERPROFILE` and `CODEX_HOME` under `tmp_path` (`tests/test_codex_install.py:44-58`), against the real `plugins/cai-codex` tree or a copy of it. Nothing mocks `SKILL.md`; its behaviour is checked only by the live run in the last row. The fake cache helper writes `{"fetched_at": "...", "models": [{"slug", "visibility", "supported_reasoning_levels": [{"effort"}]}]}`, the C1 shape (`decisions.md:22`), into `tmp_path/.codex/models_cache.json`.

| Criterion | Level | What it needs | Green before |
|---|---|---|---|
| M3 / D9: a rewritten TOML differs from the shipped one only on lines 4-5; line 1 unchanged; CRLF input keeps CRLF | unit | every real shipped TOML under `plugins/cai-codex/agents/`, plus one CRLF copy | unit 1 merges |
| M4 / AC7 / D7: `SLUG_RE` rejects a quote, a newline, `$(`, an upper-case letter, and 65 characters; `rewrite_model_lines` raises `ValueError` on each | unit | literal strings | unit 1 merges |
| D11: an anchor found 0 or 2 times raises `AnchorError`; a `model = ` line inside `developer_instructions` is not matched | unit | synthetic TOML bytes | unit 1 merges |
| AC5 / D8: `fallback_effort` for own in the list; own missing with a lower one; no lower one; `None`; only unknown names | unit | literal tuples | unit 1 merges |
| AC6 / D14: `detect` gives each of the three reasons; a non-str slug is skipped; `ignored` counts a bad slug | unit | fake cache files in `tmp_path` | unit 2 merges |
| D5: a `hide` model and a model with no `visibility` are not offered | unit | fake cache | unit 2 merges |
| D10: `load_choice` raises on invalid JSON, `format: 2`, a non-str value, and a bad slug; `save_choice` writes LF with no BOM, and the sample shape | unit | `tmp_path` | unit 2 merges |
| AC4: `plan_roles` sets `reask` for a saved slug that is missing or hidden; `offer[0]` is the cai default when offered, else the first offered; a role whose saved slug is still offered has `reask` False | unit | fake `Detection` values | unit 2 merges |
| G1: `unlisted_default` is set only for an unsaved role on a successful detection | unit | fake `Detection` | unit 2 merges |
| D13: a saved role not in `models.json` is dropped from the plan | unit | fake saved map | unit 2 merges |
| `ask_directive`: each of the three values | unit | fake plans | unit 2 merges |
| AC1 / UC1 / M2: run 1 with a fake cache and nothing saved leaves every installed TOML byte-identical to the shipped one, and prints `ask: keep-or-switch` | integration (CLI) | `fake_env`, fake cache | unit 3 merges |
| AC3 / UC3: with build saved, run 1 from a copied `<cai-root>` whose TOMLs carry a different line-1 stamp writes that stamp and build's saved slug, and the mapping shows `saved; cai default` | integration (CLI) | `shutil.copytree` of `plugins/cai-codex` into `tmp_path`, stamps edited, the copy's `install_codex.py` run | unit 3 merges |
| AC6 / UC5: no cache and build saved gives build's slug installed and `ask: keep-or-type chore think`; every role saved gives `ask: nothing` | integration (CLI) | `fake_env`, no cache | unit 3 merges |
| Decision 5: an invalid saved file exits 1 and writes neither the launcher nor any agent | integration (CLI) | `fake_env` | unit 3 merges |
| Decision 13: a leftover answers file is removed by run 1 | integration (CLI) | `fake_env` | unit 3 merges |
| Existing behaviour: the CLI tests at `tests/test_codex_install.py:225-310` and `:601-609` pass unchanged | integration (CLI) | as today | unit 3 merges |
| AC2 / UC2 / D6: `--apply` with build = an offered slug and chore = its default gives build's five TOMLs naming it, chore's byte-identical, the saved file holding build only, and the answers file deleted | integration (CLI) | `fake_env`, fake cache, a written answers file | unit 4 merges |
| AC7: `--apply` rejects `'x"y'`, `"a\nmodel = \"z\""` and `$(touch <marker>)`; exits 1; nothing written; the marker never created | integration (CLI) | `fake_env` | unit 4 merges |
| M1: `--apply` rejects an unoffered slug on a successful detection; accepts a pattern-valid typed slug on a failed one, with the role's own effort kept | integration (CLI) | `fake_env`, with and without cache | unit 4 merges |
| Partial apply: with `agents/` unwritable, `--apply` writes the saved file, then exits 1 with `re-run $setup to finish`; the answers file is kept; after restoring the mode, a second `--apply` exits 0 and every build TOML names the chosen slug | integration (CLI) | `chmod 0o555` on `tmp_path/.codex/agents` after run 1, so `tempfile.mkstemp` there fails while the saved file at the home root still writes. POSIX only, skipped on Windows and when `os.geteuid() == 0`, since root ignores the mode | unit 4 merges |
| Unknown argument exits 2 | integration (CLI) | `fake_env` | unit 4 merges |
| AC9 / R2: the detection row has status `unverified` and names `cai-model-choice.json`; the legend lists `unverified`; the tightened launcher check still passes; no design id and no repo path | unit | the real README (`tests/test_codex_readme.py`) | unit 6 merges |
| AC8: `gen-codex.py --check` exits 0; `validate.py` shows no `FAIL`; the full `pytest` passes, including `tests/test_gen_codex.py:370-391`; `plugins/cai/` has no diff against `main` | end-to-end (repo) | the regenerated tree | unit 7 merges |
| AC1, AC2 in prose: a live Codex `$setup` shows the mapping, asks keep/switch, and a switch writes the answers file and runs `--apply` | end-to-end (manual, not CI) | a Codex session on Windows, codex-cli 0.155.x, the person present | ship (not a build unit gate) |

## Work breakdown

The per-unit verify command is scoped: `python -m pytest tests/test_codex_install.py` for units 1-4, and `python -m pytest tests/test_codex_readme.py` for unit 6. The full suite is not the gate before unit 7, and that is expected, not a regression. Every unit changes a hand-written file, which changes the release fingerprint, so `tests/test_gen_codex.py::test_check_on_a_freshly_generated_tree_exits_0` (`tests/test_gen_codex.py:370-391`) and `validate.py`'s `gen-codex.py --check` line both fail until `--release` runs in unit 7. Deviations during the build are logged in the format of `stage-build.md` Step 5.

| Unit | Depends on | Can run alongside | Done when |
|---|---|---|---|
| 1 Line rewriter: `SLUG_RE`, `EFFORT_ORDER`, `AnchorError`, `rewrite_model_lines`, `fallback_effort`, and their unit tests. Riskiest, because a wrong rewrite breaks the launcher's stamp check or injects a key. | nothing | 6 | the M3, M4, D11 and AC5 rows pass in `tests/test_codex_install.py`; the existing tests are unchanged and pass |
| 2 Detection, saved choice, role map, planner: `Detection`, `detect`, `ChoiceParseError`, `load_choice`, `save_choice`, `role_agents`, `shipped_defaults`, `RolePlan`, `plan_roles`, `ask_directive`, plus unit tests | 1 | 6 | the AC4, AC6, D5, D10, D13, D14, G1 and `ask_directive` rows pass |
| 3 Run 1: `agent_bytes`, `install_agents(contents=...)`, `render_mapping`, `main` with argparse and the run 1 order, stale answers removal, docstring | 2 | 6 | the AC1, AC3, AC6, decision 5 and decision 13 CLI rows pass, and every existing CLI test passes unchanged |
| 4 Apply run: `AnswersError`, `read_answers`, `merge_answers`, `apply_answers`, `--apply` | 3 | 5, 6 | the AC2, AC7, M1, partial-apply and exit-2 rows pass |
| 5 `SKILL.md` step 2 and step 5, per its component block | 3 (the mapping grammar), 4 (`--apply`) | 6 | each of the six behaviours in its component block maps to a sentence in the new text, checked by a `reviewer` pass that walks the UC1-UC5 sequences against it and names the sentence for each arrow from `setup SKILL.md` |
| 6 README legend, row, Usage paragraph, Uninstall bullet; `tests/test_codex_readme.py` changes | nothing (names follow P1/P3) | 1-5 | the AC9 row passes in `tests/test_codex_readme.py` |
| 7 Release: `python scripts/gen-codex.py --release 0.2.0`, the eol check, then `--check`, `validate.py`, full `pytest` | 1-6 | nothing | the AC8 row passes |

### Upstream blockers

| What | Owned by | Needed before |
|---|---|---|
| Answers to P1-P4 (names, `--apply` without a path, the `unverified` status, the version). Answered 2026-09-22, each as proposed (`.claude/track/codex-model-fallback/options-detail-P1.md` … `-P4.md`). | the person | unit 3 (P1 names in output), unit 4 (P2), unit 6 (P1, P3), unit 7 (P4) |
| A live Codex check that the file-edit tool can write under `$CODEX_HOME` during `$setup` (C17, UNVERIFIED) and that the cache follows `CODEX_HOME` (C3, UNVERIFIED). If the first fails, D3=A's channel does not work and the question goes back to decisions. | the person, in a Codex session | ship (not a build unit) |


## 整併補充：codex-model-fallback-decisions

來源為原 `2026-09-22-codex-model-fallback-decisions.md`；以下僅保留上游背景或實作補充，現況以本檔維護說明為準。

#### Feasibility

"Observed" means read on 2026-09-22 with `python -c "json.load(...)"` on the file named, codex-cli 0.155.1, `CODEX_HOME` unset. `<sp>` is this session's scratchpad.

| Id | Capability | Verdict | Evidence |
|---|---|---|---|
| C1 | The cache's shape. Top-level keys are `fetched_at`, `etag`, `client_version`, `identity` and `models`. Each model has `slug`, a `visibility` of `list` or `hide`, and `supported_reasoning_levels[].effort`. Listed: `gpt-5.6-sol`, `gpt-6-astra`, `gpt-5.6-terra`, `gpt-5.6-luna` and `gpt-5.5`. Hidden: `gpt-reserve` and `codex-auto-review`. | verified | observed at key paths `models[].slug`, `models[].visibility` and `models[].supported_reasoning_levels[].effort`. Line numbers are from the 2026-09-22 fetch and move on every refresh: `C:/Users/millerlai/.codex/models_cache.json:2` (`fetched_at`); `:8`, `:106`, `:325`, `:420` and `:511` (listed slugs); `:234` and `:261` (`gpt-reserve`, `hide`); `:591` and `:618` (`codex-auto-review`, `hide`). The stance's F2 line numbers are from the 2026-09-19 fetch. |
| C2 | `models_cache.json` is a documented interface. | UNVERIFIED | not found at https://learn.chatgpt.com/docs/config-file/environment-variables, config-basic or config-reference (stance F1, 2026-09-22); also not found at config-advanced or https://learn.chatgpt.com/docs/models (this run) |
| C3 | The cache lives under `$CODEX_HOME` when that variable is set. | UNVERIFIED | inferred only from https://learn.chatgpt.com/docs/config-file/environment-variables "Sets the root for Codex state, including config, auth, logs, sessions, skills, and standalone package metadata." |
| C4 | Codex refreshes the cache on its own often enough that it is current when `$setup` runs. | UNVERIFIED | The 2026-09-19 fetch was still in place on 2026-09-22 and was replaced only by the debug run, and `models_cache.json:2` now carries that run's time (observed by the main session). No refresh policy was found in the docs. |
| C5 | `codex debug models` is documented, and it prints `{"models": [...]}` with the cache's own per-model keys. | verified | https://learn.chatgpt.com/docs/developer-commands?surface=cli "Print the raw model catalog Codex sees, including an option to inspect only the bundled catalog."; observed `<sp>/codex-debug-models.json:1` (single-line JSON): its top-level keys are `models` only, and its slugs are the cache's slugs |
| C6 | Without `--bundled`, the command refreshes from the network and rewrites the user's cache. | verified | https://learn.chatgpt.com/docs/developer-commands?surface=cli "Use `--bundled` when you want to inspect only the catalog bundled with the current binary, without refreshing from the remote models endpoint."; the rewrite of `fetched_at` was observed (Reference) |
| C7 | The bundled catalog differs from the account's refreshed one. | verified | observed `<sp>/codex-debug-models-bundled.json:1` `models[].slug`: it adds `gpt-5.4`, `gpt-daybreak-blue-latest` and `gpt-daybreak-red-latest`, and lacks `gpt-reserve` |
| C8 | `install_codex.py`, run from `$setup` inside Codex, can start `codex` as a subprocess and reach the network. Also unknown: what the command prints when it is offline. | UNVERIFIED | never run. `SKILL.md:18-20` runs the installer outside the sandbox, but whether that grants network was not observed. How a `codex` npm shim resolves from Python on Windows was not checked. |
| C9 | The refreshed list is filtered per account or policy, so it omits models the account cannot use. | UNVERIFIED | only one account was seen, and the stance records this as an assumption (`docs/design/2026-09-22-codex-model-fallback-detail.md:897`). It affects every D1 option equally. |
| C10 | A user's `model_catalog_json` setting replaces the catalog Codex loads. Unknown: whether the cache file reflects that setting. | UNVERIFIED | https://learn.chatgpt.com/docs/config-file/config-reference "Optional path to a JSON model catalog loaded on startup." (fetched 2026-09-22); how it relates to `models_cache.json` is not documented |
| C11 | The launcher is written under the real home and never under `$CODEX_HOME`. Agents are written under `$CODEX_HOME`. | verified | `plugins/cai-codex/scripts/install_codex.py:83`, `:98`, `:290-291`, `:305` |
| C12 | A role's installed agents can be found without `scripts/codex-models.json`, by mapping each `agents/<x>.md` role in `<cai-root>/models.json` to `cai_<x>.toml`. | verified | `plugins/cai-codex/models.json:39-60`; `scripts/gen-codex.py:422` (`name = "cai_{short}"`) |
| C13 | In every shipped TOML, `model` and `model_reasoning_effort` are lines 4 and 5, each a basic string. Line 1 carries the stamp that the launcher reads. | verified | `scripts/gen-codex.py:421-425`; `plugins/cai-codex/agents/cai_explorer.toml:1-5`; `plugins/cai-codex/scripts/launcher.py:29`, `:95-100` |
| C14 | The generator's TOML string escapes only `\` and `"`. | verified | `scripts/gen-codex.py:406-407` |
| C15 | A double-quoted PowerShell or `sh` string expands `$(...)`, so a value placed in one can run as code. | verified | `plugins/cai-codex/scripts/install_codex.py:129-151`; `tests/test_codex_install.py:399`, `:416` exercise it through real shells |
| C16 | `SKILL.md` has the model compose the installer's command line, and on Windows that line is a PowerShell string. | verified | `plugins/cai-codex/skills/setup/SKILL.md:31-41`; the Codex shell is PowerShell 5.1 (parent C18, `docs/design/2026-09-18-codex-support-detail.md:635`) |
| C17 | The model's file-edit tool can write a file under `$CODEX_HOME` during `$setup`. | UNVERIFIED | `SKILL.md:57-69` already requires such an edit (the language line); no recorded run shows it succeeding |
| C18 | Tests fake `HOME`, `USERPROFILE` and `CODEX_HOME` and run the installer CLI as a subprocess with no arguments. | verified | `tests/test_codex_install.py:44-57`, `:225`, `:251`, `:285`, `:300` |
| C19 | CI is Linux with only `pytest` installed. There is no `codex` binary. | verified | `.github/workflows/validate.yml:8`, `:16`, `:18` |
| C20 | Precedent: the installer refuses to overwrite a file it cannot parse, and exits 1 naming the file. | verified | `install_codex.py:52-53`, `:216-223`, `:316-318` |
| C21 | Every slug seen in either catalog fits `[a-z0-9.-]`. | verified | observed `models[].slug` in the cache (`models_cache.json:8`, `:591` in the 2026-09-22 fetch) and in `<sp>/codex-debug-models-bundled.json:1` |
| C22 | Effort names are `low`, `medium`, `high`, `xhigh`, `max` and `ultra`, listed low to high. Luna and `gpt-reserve` stop at `max`, and `gpt-5.5` stops at `xhigh`. | verified | observed `models[].supported_reasoning_levels[].effort` in the cache (`models_cache.json:12`, `:424` and `:515` in the 2026-09-22 fetch) and in both snapshots |
| C23 | The launcher refuses every stage with exit 3 when an installed agent's stamp is not the plugin's version. | verified | `launcher.py:16-19`, `:82-103` |
| C24 | PowerShell's `>` writes a BOM by default here. | verified | `CLAUDE.md:145-146` |

#### Ruled out

| Option | Invariant it violates | Evidence |
|---|---|---|
| `SKILL.md` parses the catalog and builds each role's list of offered slugs | M6: the offered set is a rule about what may be written | stance `:31` |
| `SKILL.md` writes the saved-choice file itself | M6 and the rejected stance "Prose owns the choice" | stance `:31`, `:42` |
| The installer asks keep/switch on its own stdin | M5 | stance `:30`, `:43` |
| Any rewrite that re-emits the whole TOML, or touches line 1 | M3; also C13, whose stamp line the launcher reads | stance `:28`; C13 |
| Saving the choice under `<cai-root>`, or in `hooks.json` or `AGENTS.md` | M7 | stance `:32`; C11 |

#### Requirement gaps

| # | The behavioural assumption | Veto condition, or verification path | Deletes |
|---|---|---|---|
| G1 | When a successful detection lacks a role's shipped default, the user reads the mapping, notices, and answers "switch". Keep is still the default answer (AC1), so a user who presses Enter keeps a slug the account may not have. That is R1, unfixed. | Veto: "when a successful detection does not list the slug in effect for a role, setup marks that role on its own line of the mapping and repeats it in the report". A stronger form the person may choose instead: "for such a role, keep is not the default answer". That form reopens AC1. **Chosen:** the first veto; keep stays the default — the person answered "A. 保留預設，醒目標出 (Recommended)" on 2026-09-22 (`.claude/track/codex-model-fallback/options-G1.md`). | A mapping that prints the slug in effect with no availability mark |
| G2 | Each user runs a single `$CODEX_HOME`, so it does not matter whether the saved choice is shared across homes. The opposite assumption, that a user expects one choice to follow them across homes, is just as unevidenced. C11 already puts agents (and C3 presumably the cache) under `$CODEX_HOME` and the launcher under the real home. | Veto: "a saved choice applies only to the `$CODEX_HOME` whose agents it rewrites and whose detection validated it". With `CODEX_HOME` unset, both locations are `~/.codex/...`, so only multi-home users see a difference. Verification path otherwise: the person says whether a shared choice is wanted. **Chosen:** the veto; the saved choice lives under `$CODEX_HOME`, replacing intake c's "beside the launcher" — the person answered "A. 每個 CODEX_HOME 各一份 (Recommended)" on 2026-09-22 (`.claude/track/codex-model-fallback/options-G2.md`). | Intake c's default, "beside the launcher" (shared by every home), unless the person picks a shared scope |

#### Tier 1

##### D1 — Which source does the installer read to detect the account's models?


| Option | Rests on | What it costs | Fails when |
|---|---|---|---|
| A — The installer reads `$CODEX_HOME/models_cache.json` and nothing else. (recommended) | C1, C2, C3, C4, C9, C10, C18, C19 | One file read. Tests put a fake cache in a temporary `CODEX_HOME`, and CI can run them. The source is an undocumented file. | Codex moves or reshapes the file, which falls into AC6's failure path and is reported. Or the cache is days old (C4), so the offered list trails the account. Or `model_catalog_json` is not reflected in it (C10). |
| B — The installer runs `codex debug models` as a subprocess and falls back to A when that fails. | C5, C6, C7, C8, C9, C19 | Two code paths. CI tests need a fake `codex` on `PATH` (C19). Every `$setup` rewrites the user's cache and needs network (C6). | The subprocess cannot run or cannot reach the network inside Codex (C8), which quietly lands on A every time. Or, offline, the command prints the bundled list, which offers slugs the account never had (C7; that offline output is UNVERIFIED). |
| C — `SKILL.md` runs `codex debug models`, redirects the output to a file, and passes the path. The installer parses it. | C5, C6, C8, C16, C24 | One command in prose. It is not a rule about what gets written, so M6 still holds. The installer must decode the UTF-16 or BOM output PowerShell writes (C24). A path for the file is needed. | The model skips or mistypes the command, so there is no file and AC6 applies. Or it has the same network and subprocess unknowns as B (C8), with the failure now in untested prose. |

- **Blast radius:** the installer, `SKILL.md` step 2 under B and C, the AC9 README row, and the tests.
- **Found out when:** after release, on an account whose catalog differs (C9) or after a Codex update that moves the cache. The failure path stays loud (AC6), never a wrong write (M1).
- **Undo cost:** change the installer and the README row, then `--release`. No user data has to migrate.
- **Decided:** A — the person answered "A. 只讀快取檔 (Recommended)" on 2026-09-22 (`.claude/track/codex-model-fallback/options-D1.md`).

##### D2 — Does the first installer run write anything before the user has answered?


| Option | Rests on | What it costs | Fails when |
|---|---|---|---|
| A — Install, then amend. A run with no arguments does today's full install: it applies the saved choice (or the shipped defaults) and prints the mapping and the detection result. A second `--apply` run happens only when the user switched or a role was re-asked (AC4, AC6). (recommended) | C18, C23 | Keep needs one run. The existing CLI tests (C18) stay valid with no saved file. A role AC4 re-asks carries its stale saved slug, which the user did choose (M1 holds), until the apply run. | The user abandons after run 1. The install is still consistent, and only the re-asked role keeps its stale slug, as it had before setup. |
| B — Detect, then apply. `--detect` reads and writes nothing. `--apply` always follows, keep included, and does the full install. | C18, C23 | Two runs on every setup. The CLI contract with no arguments changes, so the four CLI tests (C18) are rewritten. | Run 2 never happens, because the user abandons or the model skips it. After a plugin update the agents keep the old stamp, and every stage exits 3 (C23) until setup is finished. That is loud, but it blocks all work. |

- **Blast radius:** `SKILL.md` step 2, the installer's CLI, and the existing CLI tests. That is more than one component.
- **Found out when:** the next test run for the mechanics. What an abandoned setup leaves behind shows up only after release.
- **Undo cost:** both files ship together, so change them and run `--release`. No user data is involved.
- **Decided:** A — the person answered "A. 先裝好，要換再改 (Recommended)" on 2026-09-22 (`.claude/track/codex-model-fallback/options-D2.md`).

##### D3 — How do `SKILL.md`'s answers reach the installer?


| Option | Rests on | What it costs | Fails when |
|---|---|---|---|
| A — An answers file. The model writes a small JSON file with its file-edit tool, at the path run 1 printed. `--apply <path>` validates it, saves the choice, and deletes the file. (recommended) | C15, C16, C17 | One JSON format to specify and test. It is a write outside the workspace, the same kind step 3 already needs (C17). | The edit tool cannot write there (C17), so apply never starts; that is loud. A malformed file exits 1 and names the problem (C20 precedent). |
| B — Command-line flags, for example `--apply --role chore=<slug>`, with typed names included. | C15, C16 | No file. But a typed name (AC6, AC7) sits in a shell line that the model composes (C16) before M4 can check it. | A typed name contains `$(...)` or a quote and the model double-quotes it (C15). The code runs on the user's machine before any check, which falls under "who is allowed to do what". |
| C — Flags carry detected slugs, which run 1 has already validated. A file carries typed names only. | C15, C16, C17, C21 | Two channels and two test sets. | Typed names fail the same ways as A. Detected slugs are safe only while the charset check (D7) runs before the slug is printed. |

- **Blast radius:** `SKILL.md`, the installer, and what can run on the user's machine (high by default).
- **Found out when:** a security review, or never until someone exploits it. That is after release.
- **Undo cost:** change both files and run `--release`. No user data is involved.
- **Decided:** A — the person answered "A. 一律用答案檔 (Recommended)" on 2026-09-22 (`.claude/track/codex-model-fallback/options-D3.md`). Narrowed during Detail: `--apply` takes no path and reads the fixed answers file — the person answered "A. 不帶路徑 (Recommended)" on 2026-09-22 (`.claude/track/codex-model-fallback/options-detail-P2.md`).

#### Tier 2

##### D4 — What does the installer's detect step decide, and what is left to `SKILL.md`?

The installer decides everything that decides a write, and `SKILL.md` only shows it and asks. It computes each role's offered slugs, the slug in effect and the default marks, the AC4 re-ask set and its default answer, and the AC6 failure reason. This follows stance M6 (`docs/design/2026-09-22-codex-model-fallback-detail.md:909`) and uses C12 to name each role's agents. **Found out when:** the next test run.

##### D5 — Are `visibility: hide` models offered?

No. A saved slug that has become hidden is re-asked like a missing one (AC4). The grounds are intake item b's default (`.claude/track/codex-model-fallback/intake.md:109`) and AC2's "only slugs from a successful detection" (`intake.md:69-70`); C1 shows that `visibility` is set per model. **Found out when:** a user reports a model they wanted but could not pick, after release.

##### D6 — Does picking cai's default for a role save it?

No. Picking the default removes that role's saved entry, so the role follows future cai defaults. A saved slug that differs from a re-tiered default is shown next to that default. The grounds are AC2's "a role left at its default stays byte-identical" (`intake.md:71-72`), intake d (`intake.md:113-114`) and M2 (stance `:27`). **Found out when:** the first cai re-tier after release.

##### D7 — Which character set may a slug have before it is written?

`^[a-z0-9][a-z0-9.-]{0,63}$`, applied to every slug before a write, detected ones included, because the catalog is only a file on disk. Every observed slug fits (C21), and the generator's escaping would not stop a newline or a quote pair from injecting a key (C14, `scripts/gen-codex.py:406-407`). **Found out when:** the next test run, with injection cases for a quote, a newline and `$(`.

##### D8 — How is AC5's effort fallback ordered, and what happens when no lower level exists?

Levels rank in a fixed order, `low` < `medium` < `high` < `xhigh` < `max` < `ultra` (C22). The installer uses the highest supported level at or below the role's own. When none is lower, it uses the lowest supported level. When the list is missing or the name was typed, the role's own level stays (`intake.md:80-83`). **Found out when:** the next test run for the rule. Whether this is the right rule shows up only on a bill, after release.

##### D9 — Does M3 get its own test?

Yes, because stance M6 lists M1-M4 as needing `tests/test_codex_install.py` cases (stance `:31`). A rewritten TOML may differ from the shipped one only on lines 4-5, and line 1 must be unchanged so that the launcher's stamp check still passes (C13, C23, `plugins/cai-codex/scripts/launcher.py:97-100`). **Found out when:** the next test run.

##### D10 — What format does the saved choice use, and what happens when it is unreadable?

JSON with a format-version key and a role→slug map, read with the `json` module the installer already imports (`install_codex.py:40`). When the file is unparsable the installer exits 1, names the file and never overwrites it, the same way it treats `hooks.json` (C20). The version key is there because a saved file accumulates on users' machines. **Found out when:** the next test run. A later format change would need a migration.

#### Tier 3

| Decision | Chose | Instead of | Found out when |
|---|---|---|---|
| D11 How the two lines are rewritten | Replace exactly the lines anchored `^model = ` and `^model_reasoning_effort = `, and fail if either is not found exactly once (C13) | Parsing and re-emitting the TOML, which the stdlib cannot write and M3 rules out | The next test run |
| D12 How a role's agents are found | `<cai-root>/models.json` `assignments` mapped with the `cai_` prefix (C12) | Grouping the shipped TOMLs by their model and effort lines, which would break once two roles share both | The next test run |
| D13 A saved role that no longer exists in `models.json` | Ignored, with one line naming it (intake d) | Exit 1 | The next test run |
| D14 AC6's "lists no slugs" | Counted after hidden models are filtered out (D5), so a catalog of only hidden models is a failure | Counted before filtering | The next test run |
| D15 Is effort stored in the saved choice? | No. Effort follows the role (AC5) | Storing a per-role effort, which no AC asks for | The next test run |


## 整併補充：codex-model-fallback-stance

來源為原 `2026-09-22-codex-model-fallback-stance.md`；以下僅保留上游背景或實作補充，現況以本檔維護說明為準。

#### Optimises for

Every model a cai agent runs on is one the user chose or the shipped default, and that is enforced by a tested program: `install_codex.py` detects, validates, saves and rewrites; `$setup`'s prose only asks and passes the answers on. Success is checkable: every rule in AC1-AC7 about what gets written or saved is a `tests/test_codex_install.py` case that CI runs on Linux (`CLAUDE.md`, "Platform coverage"). That setup actually shows the mapping and asks (AC1, AC2) stays in prose, checked only by a live Codex run.

#### Sacrifices

- **The parent stance's "lowest hand-written cost"** (`2026-09-18-codex-support-detail.md:791`): the hand-written installer grows from copying TOMLs byte for byte (`install_codex.py:93-106`) to a detect / apply contract with its own input format.
- **A zero-touch setup.** Every `$setup` stops for a keep/switch answer, even when nothing changed (intake AC1).
- **cai's cost tiering as a guarantee.** A user may put `chore` on the most expensive model; cai shows its default and does not refuse.
- **Byte-identity of installed agents.** A switched role's installed `cai_*.toml` differs from the shipped one, where today every installed file is a copy (`install_codex.py:105`).
- **Assumption, not tested: the detection source is right.** `models_cache.json` is not a documented interface (F1 below). A restricted account's cache was never seen, so whether it omits a model the account cannot use is UNVERIFIED; if it lists one anyway, the user is offered it and finds out at dispatch.
- **Assumption, not asked: effort follows the role** (AC5 was a default). On a model whose `supported_reasoning_levels` lacks the role's level, the lower level is used without asking. Every listed model in this cache supports low, medium and high (`C:/Users/millerlai/.codex/models_cache.json:452-464` for luna), so today this path is reached only by a future model.

#### Invariants

**This system's:**

- M1 — No installed `cai_*.toml` names a slug nobody chose: its `model =` is the shipped one, or one the user picked from a detection or typed in a `$setup` run (AC2, AC6).
- M2 — A role with no saved choice leaves its installed TOMLs byte-identical to the shipped ones (AC1, AC2).
- M3 — Only the `model =` and `model_reasoning_effort =` lines may differ from the shipped file. Line 1's `# cai-codex-version:` stamp is never touched, because the launcher's pre-dispatch check reads exactly that line (`plugins/cai-codex/scripts/launcher.py:29`, `:97-100`).
- M4 — A typed slug reaches a TOML only after passing a fixed character set, and is rejected otherwise (AC7).
- M5 — The installer never prompts. Every question is asked by `skills/setup/SKILL.md`; the installer takes the answers as input and is deterministic given them and the detection source (intake, open item e).
- M6 — Every rule that decides what gets written (M1-M4, AC4's re-ask set, AC5's effort fallback) lives in `install_codex.py` and has a `tests/test_codex_install.py` case. None lives only in `SKILL.md` prose.
- M7 — The saved choice lives outside `<cai-root>` and outside every file the installer rewrites wholesale, so a plugin update cannot erase it (AC3).

**Cross-project:**

- The parent stance's I1 (`plugins/cai/` unchanged), I2 (hand-written files listed, `scripts/gen-codex.py:77-83`), I4 (no Codex claim beyond its verified status) and I8 (subagents never ask) — `2026-09-18-codex-support-detail.md:805-812`.
- `CLAUDE.md`, "Who a file is for": `install_codex.py` is Theirs, so it may not read `scripts/codex-models.json` (Ours, not shipped); cai's defaults are the shipped TOMLs' own `model =` lines (`plugins/cai-codex/agents/cai_explorer.toml:4`).
- The user's rule files as imported by `CLAUDE.md`; CI observes only Linux `validate.py` and `pytest`; no BOM in any written file; an output change ships with `gen-codex.py --release` (`CLAUDE.md`, "Who a file is for"; AC8).

#### Rejected stances

- **Prose owns the choice (lowest hand-written cost).** `SKILL.md` reads the cache, builds the menus and writes the saved file; the installer only applies it. This keeps the parent stance's optimisation, but M1, M4 and AC4 would live in model-read prose that no test runs, so a silent miss surfaces only on a user's machine. It loses on "enforced by a tested program" — offered as option B and not chosen (`options-design-2.md`).
- **The installer asks on its own stdin.** It would keep every rule in one program, but whether Codex's command tool feeds stdin to a running script is UNVERIFIED, and it would bypass `request_user_input`, the one menu path observed working (`plugins/cai-codex/README.md:77`). It breaks M5.
- **Leave installed TOMLs untouched and override the model somewhere else.** No other per-agent model lever is verified; the TOML's `model` is the only one observed to apply (`README.md:78`).
- **Pick for the user when the default is missing.** Superseded by the person's redirect (intake, "Decisions taken by the person": switching is only the user's own choice).

#### Out of scope

- Claude Code's `/cai:setup` (follow-up issue, intake "Follow-up issue").
- Left to Decisions, not this stance: the answers format between `SKILL.md` and the installer; the saved file's path and format; `visibility: hide` handling (intake b); re-tiered defaults (intake d); the typed-name character set.
- For Decisions to weigh, found while reading intake item c: `~/.codex/cai/` is fixed under the real home and never follows `CODEX_HOME` (`install_codex.py:12-13`, `:83`, `:290`), while agents are written under `CODEX_HOME` (`:98`, `:291`, `:305`). A choice saved beside the launcher is therefore shared by every `CODEX_HOME` on the machine — including one per account — while the agents it rewrites are not.
- Checking, between setups, that an installed slug is still offered: a slug that disappears is noticed only at the next `$setup`. Accepted by the person ("A. 寫進說明 (Recommended)", `.claude/track/codex-model-fallback/options-design-3.md`): the README and setup's report say to re-run `$setup` when an agent fails to dispatch on a model error. It rests on Codex failing loudly on an unavailable model (UNVERIFIED); veto: evidence that it fails silently or falls back to another model moves the check into the launcher's pre-dispatch step, as G3 did for version drift (`2026-09-18-codex-support-detail.md:657`).
- `docs/` is git-ignored; this file needs `git add -f` at ship.


## 整併補充：model-fallback-readme-stance

來源為原 `2026-09-22-model-fallback-readme-stance.md`；以下僅保留上游背景或實作補充，現況以本檔維護說明為準。

#### Optimises for

A cai user whose account cannot run a tier's model learns from the root `README.md` what Claude Code already does about it and how to close the one gap left, without cai shipping any new code. Success: the Model tiers section (`README.md:389-418`) carries that paragraph, every claim in it traceable to a doc sentence, and `plugins/cai/` is byte-identical to `main`.

#### Sacrifices

- **No per-role model switching in cai.** A user who wants `think` on something other than `opus` still has no cai command for it.
- **The remedy is the user's own step.** Nothing sets `fallbackModel` for them; a user who never reads the README keeps E1's failure (`discover/raw/exp1/log.json:29`, `model_not_found, HTTP 404`).
- **A global remedy for a cai problem.** `fallbackModel` applies to every Claude Code session, not only cai's agents (MC:450, "To persist a chain across sessions, set `fallbackModel` in settings").
- **Assumption, not tested: an account lacking a model is rejected like a retired ID.** E1-E3 used a retired ID. Fallback "never" triggers on "Authentication, billing, rate-limit ... errors, and a denial by your organization's policy check" (MC:440); if entitlement rejections land there, the README's remedy does not cover the case #117 was filed for. UNVERIFIED.
- **Assumption, not tested: organisation restriction and non-Anthropic providers.** Whether subagent frontmatter is substituted under an Enterprise restriction is not stated (SA:370 names only `availableModels`); Bedrock, Vertex and Foundry were not run. UNVERIFIED.

#### Invariants

**This system's:**

- N1 — Nothing under `plugins/` changes: setup keeps `model: haiku` (`plugins/cai/skills/setup/SKILL.md:4`), `plugins/cai/models.json` keeps its tiers (`:26,30,34`) and setup's assignment (`:43`), version stays `1.28.0` (`plugins/cai/.claude-plugin/plugin.json:3`), no `gen-codex.py --release`. `plugins/cai-codex/README.md` is out of reach too (findings, landmine 6).
- N2 — The README states only what a doc sentence guarantees, each with its link. Allowed: a subagent alias blocked by `availableModels` moves to the newest permitted version or to the main model (SA:372-373); a blocked skill model is ignored for the session model (MC:248); Haiku cannot be disabled by an organisation (MC:359) — scoped to the Anthropic API and LLM gateway, the only places organisation restrictions reach (MC:362).
- N3 — The remedy is described by what the docs say it covers: "overloaded, unavailable, or ... another non-retryable server error" (MC:440). The README never says fallback rescues an account without access (findings, landmine 4).
- N4 — The README names the minimum Claude Code version, v2.1.247 ("Before v2.1.247, a failure the chain covers ended the subagent instead", MC:467), which also satisfies v2.1.222 (SA:372).
- N5 — `fallbackModel`'s scope is stated with it: every session, only on a failed request, for the current turn only (MC:442), and invisible in `/status` (MC:460).
- N6 — Only the root `README.md` is edited. It is Ours: `.claude-plugin/marketplace.json:11` ships `./plugins/cai` alone.

**Cross-project:**

- `CLAUDE.md`, "Who a file is for" and "Before pushing" (`validate.py` and `pytest` green, no BOM), and the rule files it imports.
- The Codex sibling's stance, `docs/design/2026-09-22-codex-model-fallback-detail.md`, is not reopened by this one.

#### Rejected stances

- **A / 丙 — cai rewrites the installed copy per role.** Feasible (E1: full IDs apply, edits are not reverted), but a pinned full ID that retires becomes E1's 404, a failure alias-only never had; it also rests on the undocumented `~/.claude/cache/model-catalog/` (findings D11). Loses on "no new cai code" and adds a failure — offered as 丙, not chosen.
- **乙 — README plus `/cai:setup` offering to write `fallbackModel`.** Reaches users who skip the README, but ships a script, a version bump and a global-settings write from a cai command. Breaks N1 — offered, not chosen.
- **B — remap aliases with `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL`.** Rejected by the person at intake Q1; MC:61 names these variables as the way "to pin to a specific version", which reintroduces pinning for every session.

#### Out of scope

- The Codex README and `$setup` (handled by #115's stance).
- Closing #117: asked at ship's Gate 2 (AC5).
- Veto on this stance: evidence that an account-entitlement rejection is an auth or policy-class error fallback skips (MC:440) means R2's remedy does not reach #117's case; that reopens the trade toward 乙 or 丙 rather than being patched in wording.
- Left to build: the paragraph's wording, placement and `fallbackModel` example values (entries accept an alias, MC:458).
- `docs/` is git-ignored; this file needs `git add -f` at ship.


## 原始詞彙與來源補充：model-fallback-readme-stance

以下來源日期與縮寫沿用原紀錄，補足合併段落的閱讀依據；不代表重新查證外部文件。

Inputs: `.claude/track/setup-role-model-switch/intake.md` (issue #117) and `discover/findings.md`, whose AC1-AC5 supersede intake's AC1-AC8. The trade below was chosen by the person on 2026-09-22 — "甲 只寫文件 (Recommended)" (`options-discover-2.md`); rejected list holds what it was weighed against. Doc quotes are from snapshots fetched 2026-09-22 under `discover/raw/docs/`, each the markdown of `https://code.claude.com/docs/en/<name>.md`; `MC` = model-config, `SA` = sub-agents.
