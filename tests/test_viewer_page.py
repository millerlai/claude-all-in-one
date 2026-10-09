"""viewer.py's ### page component: PAGE_HTML, the JS embedded in it.

Static checks only -- an actual browser XSS check ("does an escaped string
really render as text") is explicitly left for the verify stage per the
design's Verification table; this file owns the static regex scan that
every `${...}` JS template-literal interpolation is either wrapped in
esc() or on an explicit, precisely-inventoried allowlist of non-string
(numeric/boolean/class-name/prebuilt-safe-HTML) expressions.
"""
import json
import re
import shutil
import subprocess

import pytest

import viewer


def test_stage_timing_display_and_safe_reasons():
    # Synthetic API summaries exercise presentation, not platform source coverage.
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to execute the embedded display functions")
    script = _script_body(viewer.PAGE_HTML)
    snippets = []
    for name in ("STRINGS_EN", "STRINGS_ZH_HANT"):
        snippets.append(re.search(r"const " + name + r" = \{.*?\n\};", script, re.S).group())
    snippets += ["const STRINGS = {'en':STRINGS_EN,'zh-Hant':STRINGS_ZH_HANT};",
                 "let langPref = 'zh-Hant';", "const pad = n => String(n).padStart(2, '0');"]
    for name in ("tr", "coverageOnly", "stageTimingLabel", "stageTimingReasons"):
        match = re.search(r"function " + name + r"\([^\n]*\)\{.*?\n\}", script, re.S)
        assert match, name
        snippets.append(match.group())
    summaries = [{"elapsed_ms": 70000, "timing_status": "complete"},
                 {"elapsed_ms": 70000, "timing_status": "incomplete"},
                 {"elapsed_ms": None, "timing_status": "incomplete"}, {},
                 {"elapsed_ms": 0, "timing_status": "complete"}]
    snippets.append("console.log(JSON.stringify(" + json.dumps(summaries) + ".map(stageTimingLabel)));")
    snippets.append("console.log(JSON.stringify(stageTimingReasons({timing_reasons:['source-unverified','<script>secret</script>']})));")
    snippets.append("langPref = 'en'; console.log(stageTimingLabel({}));")
    snippets.append(re.search(r"const esc = .*", script).group())
    snippets += ["const STAGES = ['build']; const GATED = new Set();",
                 re.search(r"function stepperHTML\([^\n]*\)\{.*?\n\}", script, re.S).group()]
    snippets.append("console.log(stepperHTML({track:{name:'<script>track</script>',stages:[{id:'build',status:'failed',elapsed_ms:70000,timing_status:'incomplete',timing_reasons:['<script>secret</script>']}]}}));")
    snippets.append("console.log(stageTimingReasons({timing_reasons:['event-missing','run-closed']}));")
    snippets.append("langPref = 'zh-Hant'; console.log(stageTimingReasons({timing_reasons:['event-missing','run-closed']}));")
    result = subprocess.run([node, "-e", "\n".join(snippets)], capture_output=True,
                            encoding="utf-8", check=True)
    lines = result.stdout.splitlines()
    assert json.loads(lines[0]) == ["1:10", "至少 1:10 · 資料不完整", "資料不完整", "無資料", "0:00"]
    assert json.loads(lines[1]) == "來源未驗證、原因未知"
    assert lines[2] == "No data"
    assert "At least 1:10 · Incomplete data" in lines[3]
    assert "&lt;script&gt;track&lt;/script&gt;" in lines[3]
    assert "secret" not in lines[3] and "<script>" not in lines[3]
    # unit 4: the two gap reasons the hook source writes have their own text, not "reason unknown"
    assert lines[4] == "Events missing, Run already closed"
    assert lines[5] == "事件缺漏、執行已關閉"
    assert "esc(stageTimingLabel(stage))" in script
    assert "esc(stageTimingReasons(stage))" in script

# Every `${...}` in PAGE_HTML's <script> that is NOT wrapped in esc(...) --
# inventoried by hand against the actual template literals in PAGE_HTML.
# None of these interpolate a raw row string field (project/cwd/branch/
# sessionId/model/question text/permission input/notes/summary/...); each
# is either a numeric timestamp, a value from a small fixed-literal domain
# (our own META/state-label output, not file content), or a variable that
# was itself built by concatenating only esc()-wrapped pieces and/or
# hard-coded literal strings before being interpolated here.
SAFE_INTERPOLATIONS = frozenset({
    # clockFmt(): pure arithmetic on a number.
    "h", "pad(m)", "pad(s % 60)",
    # stepperHTML(): items is a string built entirely from esc()-wrapped
    # pieces and literal HTML joined with plain '+' (no template literal).
    "items",
    # nowHTML(): recentHTML/subsHTML are prebuilt from esc()-wrapped pieces
    # the same way as items above. `since` used to be listed here as "a
    # numeric timestamp", but it is Claude's raw, untyped `statusUpdatedAt`
    # registry field on the claude_rows() path (viewer.py's `_read_registry_file`
    # never validates its type, unlike `_parse_state`'s `isinstance` checks
    # for the state file) -- so it must be esc()-wrapped like any other
    # file-derived string, not allowlisted.
    "recentHTML", "subsHTML",
    # activityHTML(): optsHTML is prebuilt from esc()-wrapped <span> pieces.
    "optsHTML",
    # rowHTML(): m.cls/mode/row.platform/platLabel are drawn from our own
    # fixed-domain constants (META, the 'wait'/'run'/'ago' enum, the
    # 'claude'/'codex' platform string this server itself sets, 'CODEX'/
    # 'CLAUDE'); alertCls/ackedCls are '' or a fixed literal; kindHTML/
    # branchHTML/sinceNote/ackBtn are prebuilt HTML strings whose only
    # variable piece (row.branch) was already esc()-wrapped when they were
    # built; activityHTML(row) is a function whose own template literals
    # are separately scanned by this same test. row.since used to be
    # listed here too -- see the comment on nowHTML's `since` above for why
    # that was wrong; it must go through esc() like every other row field.
    "m.cls", "alertCls", "ackedCls", "mode", "row.platform",
    "platLabel", "kindHTML", "branchHTML", "sinceNote", "ackBtn",
    # trackTimingHTML wraps the fully esc()-escaped total label in fixed markup.
    "trackTimingHTML",
    "activityHTML(row)",
    # summary(): hotCls is '' or 'hot', doneCls/workCls '' or 'lit';
    # pad(...) numeric.
    "hotCls", "doneCls", "workCls", "pad(waiting)", "pad(done)", "pad(work)",
    # rowHTML() (D2 rule 2's restored 「經過」): tl is prebuilt the same way
    # as recentHTML/subsHTML above -- esc()-wrapped pieces only, joined with
    # plain '+'. expandBtn is prebuilt from a fixed two-literal ternary
    # ('▴ 收起'/'▾ 經過') plus the same literal <button> markup as ackBtn.
    "tl", "expandBtn",
})


def _script_body(html):
    match = re.search(r"<script>(.*)</script>\s*</body>", html, re.DOTALL)
    assert match, "PAGE_HTML must contain the main <script> block"
    return match.group(1)


def _all_interpolations(js_text):
    # No nested backticks are used inside any ${...} span in this file (by
    # construction -- every conditional HTML fragment is built with plain
    # string concatenation first, then interpolated as a single bare name),
    # so a non-nested-brace regex is sufficient here.
    return re.findall(r"\$\{([^{}]*)\}", js_text)


def _track_page_eval(expression, language="en"):
    # Execute the shipped helpers and card renderer, without browser side effects.
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to execute the embedded display functions")
    script = _script_body(viewer.PAGE_HTML)
    snippets = []
    for name in ("STRINGS_EN", "STRINGS_ZH_HANT", "META"):
        snippets.append(re.search(r"const " + name + r" = \{.*?\n\};", script, re.S).group())
    for name in ("STRINGS", "STAGES", "GATED", "esc", "pad"):
        snippets.append(re.search(r"const " + name + r" = .*", script).group())
    snippets += ["let langPref = " + json.dumps(language) + ";",
                 "const acks = new Set(); const expanded = new Set();"]
    for name in ("tr", "trackClockFmt", "coverageOnly", "trackTimingLabel", "stateLabel", "clock",
                 "stageTimingLabel", "stageTimingReasons", "stepperHTML", "nowHTML",
                 "activityHTML", "rowHTML"):
        match = re.search(r"function " + name + r"\([^\n]*\)\{.*?\n\}", script, re.S)
        assert match, name
        snippets.append(match.group())
    snippets.append("console.log(JSON.stringify(" + expression + "));")
    result = subprocess.run([node, "-e", "\n".join(snippets)], capture_output=True,
                            encoding="utf-8", check=True)
    return json.loads(result.stdout)


def _complete_track(values, name="example"):
    return {"name": name, "stages": [
        {"id": stage, "timing_status": "complete", "elapsed_ms": ms}
        for stage, ms in zip(("intake", "discover", "design", "build", "verify", "ship"), values)
    ]}


def test_track_total_sums_canonical_stages_before_rounding():
    track = _complete_track([600000, 660000, 720000, 780000, 840000, 1620000])
    track["stages"].reverse()
    track["stages"].append({"id": "extra", "timing_status": "complete", "elapsed_ms": 9000000})
    before = json.dumps(track)
    assert _track_page_eval("trackTimingLabel(" + before + ")") == \
        "Total Time: 01:27:00 of the track - example"
    assert _track_page_eval("(() => {const t = " + before +
                            "; trackTimingLabel(t); return t;})()") == track
    tracks = [_complete_track([0] * 6), _complete_track([600, 0, 0, 0, 0, 0]),
              _complete_track([600, 600, 0, 0, 0, 0])]
    labels = _track_page_eval(json.dumps(tracks) + ".map(trackTimingLabel)")
    assert labels == ["Total Time: " + time + " of the track - example"
                      for time in ("00:00:00", "00:00:00", "00:00:01")]


def test_track_clock_boundaries_and_safe_integer_limit():
    values = [0, 59000, 3600000, 5220000, 90000000, 360000000, 9007199254740991]
    assert _track_page_eval(json.dumps(values) + ".map(trackClockFmt)") == [
        "00:00:00", "00:00:59", "01:00:00", "01:27:00", "25:00:00", "100:00:00",
        "2501999792:59:00"]
    track = _complete_track([9007199254740991, 0, 0, 0, 0, 0])
    assert "2501999792:59:00" in _track_page_eval("trackTimingLabel(" + json.dumps(track) + ")")
    track["stages"][1]["elapsed_ms"] = 1
    assert _track_page_eval("trackTimingLabel(" + json.dumps(track) + ")") == \
        "Total Time: Incomplete data of the track - example"


@pytest.mark.parametrize("language,outer,lower,no_data,incomplete,at_least", [
    ("en", "Total Time: {} of the track - example", "At least {} · Incomplete data", "No data", "Incomplete data",
     "At least {}"),
    ("zh-Hant", "總時間：{}，追蹤：example", "至少 {} · 資料不完整", "無資料", "資料不完整", "至少 {}"),
])
def test_track_total_reliability_and_languages(language, outer, lower, no_data, incomplete, at_least):
    stages = _complete_track([0] * 6)["stages"]
    cases = [[], [{"id": "intake"}],
             [{"id": "intake", "timing_status": "no-data", "elapsed_ms": None}],
             [{"id": "intake", "timing_status": "incomplete"}], stages,
             stages[:1], [{"id": "intake", "timing_status": "incomplete", "elapsed_ms": 70000}],
             [{"id": "intake", "timing_status": "complete", "elapsed_ms": 70000},
              {"id": "build", "timing_status": "incomplete"}]]
    tracks = [{"name": "example", "stages": case} for case in cases]
    # Stages not run yet make the sum a lower bound, not incomplete data (#348).
    assert _track_page_eval(json.dumps(tracks) + ".map(trackTimingLabel)", language) == [
        outer.format(value) for value in (no_data, no_data, no_data, incomplete,
                                         "00:00:00", at_least.format("00:00:00"),
                                         lower.format("00:01:10"), lower.format("00:01:10"))]


@pytest.mark.parametrize("language,outer,at_least,lower,reason", [
    ("en", "Total Time: {} of the track - example", "At least {}", "At least {} · Incomplete data",
     "Missing source coverage"),
    ("zh-Hant", "總時間：{}，追蹤：example", "至少 {}", "至少 {} · 資料不完整", "缺少來源涵蓋證據"),
])
def test_coverage_only_stage_is_a_lower_bound_not_incomplete_data(language, outer, at_least, lower, reason):
    # #348: no shipped source writes a coverage proof, so every measured stage
    # carries coverage-missing; that alone says "lower bound", not "broken data".
    coverage = {"id": "intake", "elapsed_ms": 70000, "timing_status": "incomplete",
                "timing_reasons": ["coverage-missing"]}
    gap = {"id": "build", "elapsed_ms": 5000, "timing_status": "incomplete",
           "timing_reasons": ["coverage-missing", "event-missing"]}
    no_reasons = {"id": "build", "elapsed_ms": 5000, "timing_status": "incomplete"}
    odd = [dict(coverage, timing_reasons=value) for value in ([], "coverage-missing", None)]
    assert _track_page_eval(json.dumps([coverage, gap, no_reasons] + odd) + ".map(stageTimingLabel)",
                            language) == [at_least.format("1:10"), lower.format("0:05"),
                                          lower.format("0:05")] + [lower.format("1:10")] * 3
    tracks = [{"name": "example", "stages": stages}
              for stages in ([coverage], [coverage, gap], [coverage, no_reasons])]
    assert _track_page_eval(json.dumps(tracks) + ".map(trackTimingLabel)", language) == [
        outer.format(at_least.format("00:01:10")), outer.format(lower.format("00:01:15")),
        outer.format(lower.format("00:01:15"))]
    assert _track_page_eval("stageTimingReasons(" + json.dumps(coverage) + ")", language) == reason
    assert _track_page_eval("stageTimingReasons({timing_reasons:['atLeast']})", language) == \
        _track_page_eval("tr('note.reason-unknown')", language)


@pytest.mark.parametrize("bad_stage", [
    {"elapsed_ms": -1}, {"elapsed_ms": 0.5}, {"elapsed_ms": "1000"},
    {"elapsed_ms": True}, {"elapsed_ms": None}, {"elapsed_ms": 9007199254740992},
    {"timing_status": "unknown", "elapsed_ms": 1000},
    {"timing_status": "no-data", "elapsed_ms": 0}, {"timing_status": "unknown"},
    {"timing_status": None, "elapsed_ms": 1000},
])
def test_track_total_rejects_invalid_measurements(bad_stage):
    invalid = {"id": "intake", "timing_status": "complete", **bad_stage}
    track = {"name": "example", "stages": [invalid]}
    assert _track_page_eval("trackTimingLabel(" + json.dumps(track) + ")") == \
        "Total Time: Incomplete data of the track - example"
    track["stages"].append({"id": "build", "timing_status": "complete", "elapsed_ms": 2000})
    assert _track_page_eval("trackTimingLabel(" + json.dumps(track) + ")") == \
        "Total Time: At least 00:00:02 · Incomplete data of the track - example"


def test_track_total_nonfinite_values_and_duplicate_stage_order():
    assert _track_page_eval("[NaN, Infinity, -Infinity].map(ms => trackTimingLabel("
                            "{name:'example',stages:[{id:'intake',timing_status:'complete',elapsed_ms:ms}]}))") == [
        "Total Time: Incomplete data of the track - example"] * 3
    track = _complete_track([1000, 2000, 0, 0, 0, 0])
    track["stages"].append({"id": "intake", "timing_status": "complete", "elapsed_ms": 5000})
    expected = "Total Time: At least 00:00:02 · Incomplete data of the track - example"
    assert _track_page_eval("trackTimingLabel(" + json.dumps(track) + ")") == expected
    track["stages"].reverse()
    assert _track_page_eval("trackTimingLabel(" + json.dumps(track) + ")") == expected
    track["stages"] = [stage for stage in track["stages"] if stage["id"] == "intake"]
    assert _track_page_eval("trackTimingLabel(" + json.dumps(track) + ")") == \
        "Total Time: Incomplete data of the track - example"
    assert _track_page_eval("stageTimingReasons({timing_reasons:['trackTotal']})") == "Reason unknown"


@pytest.mark.parametrize("language,prefix", [("en", "Total Time:"), ("zh-Hant", "總時間：")])
def test_track_total_in_actual_card_identity_and_safe_name(language, prefix):
    name = '<img src=x onerror="bad()"> & \' {time} {name}'
    track = _complete_track([600000, 660000, 720000, 780000, 840000, 1620000], name)
    rows = [{"key": key, "state": "unknown", "project": "p", "platform": "codex",
             "since": 0, "sessionId": key, "aliveCertainty": "inferred", "track": t}
            for key, t in (("first", track), ("second", track), ("none", None))]
    cards = _track_page_eval(json.dumps(rows) + ".map(rowHTML)", language)
    labels = []
    for card in cards[:2]:
        ident = card.split('<div class="ident">', 1)[1].split('<div class="activity">', 1)[0]
        label = re.search(r'<div class="meta">(' + prefix + r'.*?)</div>', ident).group(1)
        labels.append(label)
        assert "01:27:00" in label
        assert '&lt;img src=x onerror=&quot;bad()&quot;&gt; &amp; &#39; {time} {name}' in label
        assert ident.index("SID ") < ident.index(prefix) < ident.index("Alive: inferred" if language == "en" else "存活：推斷")
        assert '<img' not in card
        assert 'class="stage-timing"' in card
    assert labels[0] == labels[1]
    assert prefix not in cards[2]
    assert "trackTimingHTML" not in cards[2]


def test_every_interpolation_is_escaped_or_allowlisted():
    js_text = _script_body(viewer.PAGE_HTML)
    interpolations = _all_interpolations(js_text)
    assert interpolations, "expected to find at least one ${...} interpolation"
    bad = [expr for expr in interpolations
          if not expr.strip().startswith("esc(") and expr.strip() not in SAFE_INTERPOLATIONS]
    assert bad == [], "unescaped, non-allowlisted interpolation(s): %r" % bad


def test_safe_interpolations_contains_no_row_string_field():
    forbidden = {"project", "cwd", "row.project", "row.cwd", "row.branch",
                "row.sessionId", "row.model", "row.question", "row.permission",
                "row.notes", "row.summary", "row.current", "row.track.name"}
    assert not (SAFE_INTERPOLATIONS & forbidden)


def test_page_html_contains_port_placeholder():
    assert "__PORT__" in viewer.PAGE_HTML


def test_page_html_never_names_a_cai_slash_command_or_plugin_root():
    assert "/cai:" not in viewer.PAGE_HTML
    assert "${CLAUDE_PLUGIN_ROOT}" not in viewer.PAGE_HTML
    assert "~/.claude/" not in viewer.PAGE_HTML
    assert "CLAUDE_CODE_" not in viewer.PAGE_HTML


def test_meta_has_exactly_the_six_real_state_keys():
    match = re.search(r"const META = \{(.*?)\n\};", viewer.PAGE_HTML, re.DOTALL)
    assert match, "expected a `const META = {...};` object literal"
    body = match.group(1)
    keys = re.findall(r"^\s*(\w+):\s*\{", body, re.MULTILINE)
    assert set(keys) == {"question", "permission", "attention", "done", "working", "unknown"}
    for old_key in ("ask", "perm", "work", "ended", "gate"):
        assert old_key not in keys


def test_page_html_has_no_html_placeholder_leftover():
    assert "PAGE_HTML_PLACEHOLDER" not in viewer.PAGE_HTML


def test_activity_html_question_text_falls_back_when_missing():
    """Some Codex question rows still carry no "text" (e.g. an
    unparseable `arguments` string -- viewer.py's classify_codex, D2 rule
    4) -- so `row.question.text` can be JS `undefined`, and `esc(undefined)`
    renders the literal string "undefined" in the page's question box unless
    activityHTML() falls back to '' the same way it already does for
    `row.question.options` (`(row.question && row.question.options) || []`,
    the line just above)."""
    js_text = _script_body(viewer.PAGE_HTML)
    match = re.search(r"const text = (.+?);", js_text)
    assert match, "expected activityHTML's `const text = ...;` line"
    assert match.group(1) == "row.question ? (row.question.text || '') : ''"


# ============================= D2 rule 2: the restored 「經過」 expand ====

def test_expand_button_toggles_between_expand_and_collapse_labels():
    js_text = _script_body(viewer.PAGE_HTML)
    assert "▾ 經過" in js_text
    assert "▴ 收起" in js_text
    assert "data-act=\"expand\"" in js_text


def test_expand_click_handler_toggles_the_expanded_set():
    js_text = _script_body(viewer.PAGE_HTML)
    assert "expanded.has(row.key)" in js_text
    assert "expanded.delete(row.key)" in js_text
    assert "expanded.add(row.key)" in js_text


def test_render_signature_includes_expanded_state():
    """Without `expanded.has(row.key)` in the keyed-update signature,
    toggling 經過 would not trigger a re-render -- render()'s `sig` must
    include it the same way it already includes `acks.has(row.key)`."""
    js_text = _script_body(viewer.PAGE_HTML)
    match = re.search(r"const sig = JSON\.stringify\((.+?)\);", js_text)
    assert match, "expected render()'s `const sig = ...;` line"
    assert "expanded.has(row.key)" in match.group(1)


def test_timeline_css_is_restored():
    assert ".timeline{" in viewer.PAGE_HTML or ".timeline {" in viewer.PAGE_HTML


# =============================== AC4/AC5: Codex lock note, 執行中（背景） ====

def test_footer_has_the_codex_lock_note_hidden_by_default():
    match = re.search(r'<span id="codexLockNote" hidden>(.*?)</span>', viewer.PAGE_HTML)
    assert match, "expected a hidden #codexLockNote span in the footer"
    assert 'data-i18n="footer.codexLock"' in match.group(1)
    js_text = _script_body(viewer.PAGE_HTML)
    en_match = re.search(r"const STRINGS_EN = (\{.*?\n\});", js_text, re.S)
    assert en_match, "expected a `const STRINGS_EN = {...};` object literal"
    strings_en = json.loads(en_match.group(1))
    assert "thread-writer-locks" in strings_en["footer.codexLock"]


def test_poll_toggles_the_codex_lock_note():
    js_text = _script_body(viewer.PAGE_HTML)
    assert ("document.getElementById('codexLockNote').hidden = "
           "data.codexLockDirMissing !== true;") in js_text


def test_state_label_shows_background_working():
    js_text = _script_body(viewer.PAGE_HTML)
    assert "執行中（背景）" in js_text
    match = re.search(r"if \(row\.state === 'working'\) return (\{.*?\});", js_text)
    assert match, "expected stateLabel()'s working-state return"
    assert "row.background === true" in match.group(1)


def test_timeline_lives_inside_the_row_article():
    """The mockup's own `${tl}` placement is a sibling *after* `</article>`,
    which the render() DOM-parse (`tmp.firstElementChild`) then silently
    drops -- the mockup's 「經過」 timeline never actually renders. viewer.py
    must not reproduce that: the timeline goes inside the article, before
    its closing tag."""
    js_text = _script_body(viewer.PAGE_HTML)
    match = re.search(r"return `<article(.*)`;\s*\}", js_text, re.DOTALL)
    assert match, "expected rowHTML()'s `return \\`<article...\\`;` template"
    body = match.group(1)
    assert re.search(r"\$\{tl\}\s*</article>", body), \
        "the timeline interpolation must appear before </article>, not after"


# ============================ language switch (en / zh-Hant) ==============

_CJK_RANGES = [
    (0x2E80, 0x2FDF), (0x3000, 0x303F), (0x3040, 0x30FF), (0x3100, 0x31BF),
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF),
]


def _strings_en():
    js_text = _script_body(viewer.PAGE_HTML)
    match = re.search(r"const STRINGS_EN = (\{.*?\n\});", js_text, re.S)
    assert match, "expected a `const STRINGS_EN = {...};` object literal"
    return json.loads(match.group(1))


def test_string_tables_have_the_same_keys():
    js_text = _script_body(viewer.PAGE_HTML)
    en_match = re.search(r"const STRINGS_EN = (\{.*?\n\});", js_text, re.S)
    zh_match = re.search(r"const STRINGS_ZH_HANT = (\{.*?\n\});", js_text, re.S)
    assert en_match, "expected a `const STRINGS_EN = {...};` object literal"
    assert zh_match, "expected a `const STRINGS_ZH_HANT = {...};` object literal"
    en = json.loads(en_match.group(1))
    zh = json.loads(zh_match.group(1))
    assert set(en.keys()) == set(zh.keys())
    assert len(en) == 86


def test_no_cjk_outside_the_zh_hant_table():
    html = viewer.PAGE_HTML
    match = re.search(r"const STRINGS_ZH_HANT = \{.*?\n\};", html, re.S)
    assert match, "expected a `const STRINGS_ZH_HANT = {...};` object literal"
    remainder = html[:match.start()] + html[match.end():]
    assert remainder.count("繁體中文") == 1, \
        "expected exactly one CJK string (the switch button label) outside the zh-Hant table"
    remainder = remainder.replace("繁體中文", "", 1)
    bad = [ch for ch in remainder
           if any(lo <= ord(ch) <= hi for lo, hi in _CJK_RANGES)]
    assert bad == [], "unexpected CJK outside the zh-Hant table: %r" % bad


def test_every_i18n_attribute_names_a_key():
    strings_en = _strings_en()
    attrs = re.findall(
        r'data-i18n(?:-html|-title|-aria-label)?="([^"]+)"', viewer.PAGE_HTML)
    assert attrs, "expected at least one data-i18n* attribute"
    for key in attrs:
        assert key in strings_en, "data-i18n* attribute names an unknown key: %r" % key


def test_every_note_code_has_a_key():
    strings_en = _strings_en()
    codes = ["reason-unknown", "alive-inferred", "background-shell",
             "registry-may-be-stale", "previous-turn-failed"]
    for code in codes:
        assert "note." + code in strings_en


def test_html_defaults_to_english_and_prepaint_reads_the_language_key():
    html = viewer.PAGE_HTML
    assert '<html lang="en">' in html
    head_match = re.search(r"<head>.*?</head>", html, re.S)
    assert head_match, "expected a <head> block"
    assert "agent-viewer-lang" in head_match.group(0)


def test_language_switch_has_two_labelled_buttons():
    html = viewer.PAGE_HTML
    en_match = re.search(r'<button data-lang-pref="en"[^>]*>([^<]*)</button>', html)
    zh_match = re.search(r'<button data-lang-pref="zh-Hant"[^>]*>([^<]*)</button>', html)
    assert en_match, "expected a data-lang-pref=\"en\" button"
    assert zh_match, "expected a data-lang-pref=\"zh-Hant\" button"
    assert en_match.group(1) == "English"
    assert zh_match.group(1) == "繁體中文"


def test_render_signature_includes_language():
    js_text = _script_body(viewer.PAGE_HTML)
    match = re.search(r"const sig = JSON\.stringify\((.+?)\);", js_text)
    assert match, "expected render()'s `const sig = ...;` line"
    assert "langPref" in match.group(1)


def test_attention_notes_put_codes_before_raw_text():
    js_text = _script_body(viewer.PAGE_HTML)
    match = re.search(r"const notes = (.+?);", js_text)
    assert match, "expected activityHTML's `const notes = ...;` line"
    line = match.group(1)
    assert "row.noteCodes" in line
    assert "row.notes" in line
    assert line.index("row.noteCodes") < line.index("row.notes")


# ================= top summary: the same three words the cards use ========

def _summary_body():
    js_text = _script_body(viewer.PAGE_HTML)
    match = re.search(r"function summary\(\)\{(.*?)\n\}", js_text, re.S)
    assert match, "expected a `function summary(){...}` block"
    return match.group(1)


def test_summary_shows_waiting_done_and_working_chips():
    body = _summary_body()
    for key in ("summary.waiting", "summary.done", "state.working"):
        assert "tr('%s')" % key in body
    assert "tr('title.waiting', {n: waiting})" in body


def test_summary_waiting_count_leaves_done_rows_out():
    """「等待處理」 is every card that needs you except 「完成，等指示」,
    which has its own 「完成」 count next to it."""
    assert "r.state !== 'done' && META[r.state].human" in _summary_body()


def test_summary_does_not_count_seen_rows():
    """已讀 only stops a card flashing; the numbers up top follow the cards'
    state alone, so pressing it on a card must not change any of them."""
    assert "acks" not in _summary_body()
    strings_en = _strings_en()
    assert "summary.unread" not in strings_en
    assert "title.unread" not in strings_en


def test_done_and_working_chips_take_their_cards_colours():
    """完成 and 執行中 light up in their cards' colours (.s-done / .s-work
    set --c) whenever they count anything, the way 等待處理 already does."""
    body = _summary_body()
    assert "const doneCls = done ? 'lit' : '';" in body
    assert "const workCls = work ? 'lit' : '';" in body
    assert '<span class="chip s-done ${doneCls}">' in body
    assert '<span class="chip s-work ${workCls}">' in body
    assert ".chip.lit{border-color:var(--c);color:var(--c)}" in viewer.PAGE_HTML
    assert ".chip.lit b{color:var(--c)}" in viewer.PAGE_HTML


def test_zh_hant_summary_labels_are_the_three_categories():
    js_text = _script_body(viewer.PAGE_HTML)
    match = re.search(r"const STRINGS_ZH_HANT = (\{.*?\n\});", js_text, re.S)
    assert match, "expected a `const STRINGS_ZH_HANT = {...};` object literal"
    zh = json.loads(match.group(1))
    assert zh["summary.waiting"] == "等待處理"
    assert zh["summary.done"] == "完成"
    assert zh["state.working"] == "執行中"


def test_every_permission_wait_rings_the_ask_chime():
    # A permission wait needs the person as much as a question does, so an
    # inferred one (every Codex permission) rings the same audible chime; its
    # checkbox still decides whether it rings at all.
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to execute the embedded display functions")
    script = _script_body(viewer.PAGE_HTML)
    ring = re.search(r"function ringForRows\([^\n]*\)\{.*?\n\}", script, re.S).group()
    states = re.search(r"const HUMAN_STATES = .*", script).group()
    harness = "\n".join([
        states, ring,
        "let soundOn = true, firstFetch = true; const acks = new Set(), lastSeenEntryId = new Map();",
        "const doneChimeEl = {checked: false}; const inferredChimeEl = {checked: true};",
        "const rung = []; function chime(kind){ rung.push(kind); }",
        "const rows = id => [{key: 'p', state: 'permission', certainty: 'inferred', entryId: id},",
        "                    {key: 'c', state: 'permission', certainty: 'confirmed', entryId: id}];",
        "ringForRows(rows('a')); ringForRows(rows('b'));",
        "inferredChimeEl.checked = false; ringForRows(rows('c'));",
        "console.log(JSON.stringify(rung));",
    ])
    result = subprocess.run([node, "-e", harness], capture_output=True, encoding="utf-8", check=True)
    assert json.loads(result.stdout) == ["ask", "ask", "ask"]


def test_every_looping_animation_steps_instead_of_tweening():
    # #350: a looping animation that tweens makes Chrome repaint every frame
    # for as long as the page is open (~30% of a core in a headless probe);
    # stepped, the value changes a few times per cycle and the frames in
    # between are skipped (~2 CPU-seconds per 20 s against ~1 with none).
    html = viewer.PAGE_HTML
    looping = [part.strip() for decl in re.findall(r"animation:([^;}]*)", html)
               for part in re.split(r",(?![^()]*\))", decl) if "infinite" in part]
    assert len(looping) == 9
    for part in looping:
        assert "steps(" in part, part
    spins = [part for part in looping if part.startswith("spin ")]
    # Two steps of a full turn are the same frame; eight keep it visibly turning.
    assert spins and all("steps(8)" in part for part in spins)
