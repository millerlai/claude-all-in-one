"""viewer.py's ### page component: PAGE_HTML, the JS embedded in it.

Static checks only -- an actual browser XSS check ("does an escaped string
really render as text") is explicitly left for the verify stage per the
design's Verification table; this file owns the static regex scan that
every `${...}` JS template-literal interpolation is either wrapped in
esc() or on an explicit, precisely-inventoried allowlist of non-string
(numeric/boolean/class-name/prebuilt-safe-HTML) expressions.
"""
import re

import viewer

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
    "activityHTML(row)",
    # summary(): hotCls is '' or 'hot'; pad(...) numeric; unreadHTML
    # prebuilt from a numeric count and literal HTML only.
    "hotCls", "pad(human.length)", "unreadHTML", "pad(work)",
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
