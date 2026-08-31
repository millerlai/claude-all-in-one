"""Unit 1: the capability interface, classify(), and GitHubBackend.

Everything here drives ticket_backend through CAI_TICKET_CLI pointed at
fake_gh.py -- no real `gh`, no network (per the unit's own instructions:
the e2e check against issue #48 is run by the person who dispatched this,
not by this suite).
"""
import json
import subprocess
import sys

import pytest

import ticket_backend as tb


def fake_cli(tmp_path, script_body):
    """Writes a throwaway CAI_TICKET_CLI target that runs `script_body` as a
    Python script, and returns the full path (with extension -- DD9)."""
    path = tmp_path / "fake_gh.py"
    path.write_text(script_body, encoding="utf-8")
    return json.dumps([sys.executable, str(path)])


def set_cli(monkeypatch, argv_json):
    monkeypatch.setenv(tb.CLI_ENV, argv_json)


# --- classify(): one test per branch, six categories, closed set -----------

def test_classify_exceptions_map_to_unreachable():
    assert tb.classify(FileNotFoundError(), -1, "") == "unreachable"
    assert tb.classify(subprocess.TimeoutExpired("gh", 10), -1, "") == "unreachable"
    assert tb.classify(OSError("boom"), -1, "") == "unreachable"


def test_classify_zero_exit_is_ok():
    assert tb.classify(None, 0, "") == "ok"


def test_classify_auth_failed_real_wordings():
    assert tb.classify(None, 1, "HTTP 401: something") == "auth-failed"
    assert tb.classify(None, 1, "Bad credentials (https://api.github.com/graphql)") \
        == "auth-failed"
    # case-insensitive substring match
    assert tb.classify(None, 1, "http 401 unauthorized") == "auth-failed"


def test_classify_ticket_not_found_real_wordings():
    assert tb.classify(None, 1, "Could not resolve to an issue or pull request "
                                "with the number of 999.") == "ticket-not-found"
    assert tb.classify(None, 1, "Could not resolve to a Repository with the "
                                "name 'x/y'.") == "ticket-not-found"


def test_classify_unreachable_error_connecting():
    assert tb.classify(None, 1, "error connecting to api.github.com") == "unreachable"


def test_classify_body_too_long_is_unclassified():
    assert tb.classify(None, 1, "body is too long (maximum is 65536 "
                                "characters)") == "unclassified"


def test_classify_fallback_is_unclassified():
    assert tb.classify(None, 1, "some other never-seen-before message") == "unclassified"
    assert tb.classify(None, 1, "") == "unclassified"
    assert tb.classify(None, 1, None) == "unclassified"


def test_classify_always_returns_a_closed_category():
    cases = [
        (FileNotFoundError(), -1, ""),
        (None, 0, ""),
        (None, 1, "HTTP 401"),
        (None, 1, "Could not resolve to a Repository"),
        (None, 1, "error connecting to x"),
        (None, 1, "body is too long"),
        (None, 1, "anything else"),
    ]
    for exc, rc, stderr in cases:
        assert tb.classify(exc, rc, stderr) in tb.CATEGORIES


# --- AC9: raw stderr never survives classify() ------------------------------

def test_classify_never_returns_the_raw_stderr_text():
    secret = "Bearer sk-test-4f8a9c21"
    result = tb.classify(None, 1, "HTTP 401: Bad credentials, %s" % secret)
    assert secret not in result
    assert result == "auth-failed"


# --- numeric comment id parsing (fact 1) ------------------------------------

def test_numeric_comment_id_is_parsed_from_the_url_not_the_node_id():
    url = "https://github.com/millerlai/claude-all-in-one/issues/48#issuecomment-1234567890"
    assert tb._numeric_comment_id(url) == "1234567890"


# --- BACKENDS registry -------------------------------------------------------

def test_backends_registry_resolves_both_names():
    assert tb.get("github").name == "github"
    assert tb.get("local-stub").name == "local-stub"
    assert tb.get("nonexistent") is None


# --- FileNotFoundError and TimeoutExpired both -> unreachable, through run --

def test_missing_cli_is_unreachable(tmp_path, monkeypatch):
    set_cli(monkeypatch, str(tmp_path / "does-not-exist.exe"))
    backend = tb.GitHubBackend()
    value, category = backend.whoami(str(tmp_path))
    assert value is None
    assert category == "unreachable"


def test_timeout_is_unreachable(tmp_path, monkeypatch):
    script = (
        "import time, sys\n"
        "time.sleep(30)\n"
    )
    monkeypatch.setattr(tb, "TIMEOUT_SECONDS", 0.2)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    value, category = backend.whoami(str(tmp_path))
    assert value is None
    assert category == "unreachable"


# --- transition_once: idempotent, safe to retry -----------------------------

def test_transition_once_is_idempotent(tmp_path, monkeypatch):
    script = (
        "import sys\n"
        "print('! Issue #48 is already closed')\n"
        "sys.exit(0)\n"
    )
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    ok, category = backend.transition_once(str(tmp_path), "48")
    assert ok is True
    assert category == "ok"
    # second call, same script -- still exits 0
    ok2, category2 = backend.transition_once(str(tmp_path), "48")
    assert ok2 is True
    assert category2 == "ok"


def test_transition_once_failure_reports_a_category(tmp_path, monkeypatch):
    script = (
        "import sys\n"
        "sys.stderr.write('HTTP 401: Bad credentials\\n')\n"
        "sys.exit(1)\n"
    )
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    ok, category = backend.transition_once(str(tmp_path), "48")
    assert ok is False
    assert category == "auth-failed"


# --- read() ------------------------------------------------------------------

def test_read_success(tmp_path, monkeypatch):
    script = (
        "import json, sys\n"
        "print(json.dumps({'number': 48, 'title': 'a title', 'body': 'the body'}))\n"
    )
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    value, category = backend.read(str(tmp_path), "48")
    assert category == "ok"
    assert value == {"number": "48", "title": "a title", "body": "the body"}


def test_read_not_found(tmp_path, monkeypatch):
    script = (
        "import sys\n"
        "sys.stderr.write('Could not resolve to an issue or pull request "
        "with the number of 9999.\\n')\n"
        "sys.exit(1)\n"
    )
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    value, category = backend.read(str(tmp_path), "9999")
    assert value is None
    assert category == "ticket-not-found"


# --- upsert_comment: cache hit updates in place, no create ------------------

def test_upsert_comment_updates_the_matching_comment_in_place(tmp_path, monkeypatch):
    log = tmp_path / "calls.log"
    script = (
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(argv) + '\\n')\n"
        "if argv[:2] == ['issue', 'view']:\n"
        "    print(json.dumps({'comments': [\n"
        "        {'body': '[cai track: x]\\nold', 'author': {'login': 'octocat'},\n"
        "         'url': 'https://github.com/o/r/issues/48#issuecomment-111'}]}))\n"
        "elif argv[:3] == ['api', '--method', 'PATCH']:\n"
        "    print(json.dumps({'html_url': "
        "'https://github.com/o/r/issues/48#issuecomment-111'}))\n"
        "else:\n"
        "    sys.exit(3)\n"
    ) % str(log)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    url, category = backend.upsert_comment(
        str(tmp_path), "48", "[cai track: x]", "[cai track: x]\nnew", "octocat")
    assert category == "ok"

    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(c.startswith("issue view") for c in calls)
    patch_calls = [c for c in calls if c.startswith("api --method PATCH")]
    assert len(patch_calls) == 1
    assert "issues/comments/111" in patch_calls[0]
    # node id (IC_...) never appears in what was sent
    assert "IC_" not in patch_calls[0]
    # no create call was ever made
    assert not any(c.startswith("issue comment") for c in calls)


def test_upsert_comment_patch_sends_the_exact_intended_body(tmp_path, monkeypatch):
    # The create path already proves its body never touches argv (below);
    # the PATCH/update path sends the body through -f body=..., and until
    # now no test read back what actually arrived there. subprocess.run()
    # passes argv as a list, never through a shell, so a body containing
    # shell metacharacters is not a shell-injection risk here -- but the
    # exact text still has to survive the trip intact.
    log = tmp_path / "calls.log"
    script = (
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, \"a\", encoding=\"utf-8\") as fh:\n"
        "    fh.write(json.dumps(argv) + chr(10))\n"
        "if argv[:2] == [\"issue\", \"view\"]:\n"
        "    print(json.dumps({\"comments\": [\n"
        "        {\"body\": \"[cai track: x]\\nold\", \"author\": {\"login\": \"octocat\"},\n"
        "         \"url\": \"https://github.com/o/r/issues/48#issuecomment-111\"}]}))\n"
        "elif argv[:3] == [\"api\", \"--method\", \"PATCH\"]:\n"
        "    print(json.dumps({\"html_url\": "
        "\"https://github.com/o/r/issues/48#issuecomment-111\"}))\n"
        "else:\n"
        "    sys.exit(3)\n"
    ) % str(log)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()

    intended_body = ("[cai track: x]\n| stage | status | note |\n"
                      "| build | passed | pipes | and \"quotes\" |\n"
                      "non-ASCII: \u4e2d\u6587")
    url, category = backend.upsert_comment(
        str(tmp_path), "48", "[cai track: x]", intended_body, "octocat")
    assert category == "ok"

    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    patch_calls = [c for c in calls if c[:3] == ["api", "--method", "PATCH"]]
    assert len(patch_calls) == 1
    assert ("body=" + intended_body) in patch_calls[0]


def test_upsert_comment_creates_when_no_match(tmp_path, monkeypatch):
    log = tmp_path / "calls.log"
    script = (
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(argv) + '\\n')\n"
        "if argv[:2] == ['issue', 'view']:\n"
        "    print(json.dumps({'comments': []}))\n"
        "elif argv[:2] == ['issue', 'comment']:\n"
        "    print('https://github.com/o/r/issues/48#issuecomment-222')\n"
        "else:\n"
        "    sys.exit(3)\n"
    ) % str(log)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    url, category = backend.upsert_comment(
        str(tmp_path), "48", "[cai track: x]", "[cai track: x]\nbody\nwith \"quotes\"",
        "octocat")
    assert category == "ok"
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(c.startswith("issue comment") for c in calls)
    assert "--body-file" in calls[-1]
    # the body itself never touches argv for the create path
    assert "quotes" not in calls[-1]


def test_upsert_comment_skips_a_differently_authored_marker_match(tmp_path, monkeypatch):
    log = tmp_path / "calls.log"
    script = (
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(argv) + '\\n')\n"
        "if argv[:2] == ['issue', 'view']:\n"
        "    print(json.dumps({'comments': [\n"
        "        {'body': '[cai track: x]\\nsomeone elses', "
        "'author': {'login': 'someone-else'},\n"
        "         'url': 'https://github.com/o/r/issues/48#issuecomment-999'}]}))\n"
        "elif argv[:2] == ['issue', 'comment']:\n"
        "    print('https://github.com/o/r/issues/48#issuecomment-333')\n"
        "else:\n"
        "    sys.exit(3)\n"
    ) % str(log)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    url, category = backend.upsert_comment(
        str(tmp_path), "48", "[cai track: x]", "[cai track: x]\nmine", "octocat")
    assert category == "ok"
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any(c.startswith("issue comment") for c in calls)


# --- DD10: 403 on write -> one extra whoami -> identity-differs path -------

def test_upsert_comment_403_with_a_different_identity_is_forbidden(tmp_path, monkeypatch, capsys):
    log = tmp_path / "calls.log"
    script = (
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(argv) + '\\n')\n"
        "if argv[:2] == ['issue', 'view']:\n"
        "    print(json.dumps({'comments': [\n"
        "        {'body': '[cai track: x]\\nold', 'author': {'login': 'octocat'},\n"
        "         'url': 'https://github.com/o/r/issues/48#issuecomment-111'}]}))\n"
        "elif argv[:3] == ['api', '--method', 'PATCH']:\n"
        "    sys.stderr.write('HTTP 403: Forbidden\\n')\n"
        "    sys.exit(1)\n"
        "elif argv[:2] == ['api', 'user']:\n"
        "    print('new-login')\n"
        "else:\n"
        "    sys.exit(3)\n"
    ) % str(log)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    url, category = backend.upsert_comment(
        str(tmp_path), "48", "[cai track: x]", "[cai track: x]\nnew", "octocat")

    assert url is None
    assert category == "forbidden"
    calls = log.read_text(encoding="utf-8").splitlines()
    # exactly one whoami, triggered only after the 403
    assert sum(1 for c in calls if c.startswith("api user")) == 1
    # no second marked comment was ever created
    assert not any(c.startswith("issue comment") for c in calls)

    out = capsys.readouterr().out
    assert "octocat" in out
    assert "new-login" in out


def test_upsert_comment_403_with_the_same_identity_is_still_forbidden(tmp_path, monkeypatch, capsys):
    # classify()'s own decision order has no 403 rule -- the design reserves
    # "forbidden" for exactly this: 403 (or "forbidden") in a write's stderr,
    # regardless of whether the identity changed. DD10's extra whoami only
    # decides which *message* is printed (identity change vs. a plain
    # permissions problem on the same account), never the category.
    log = tmp_path / "calls.log"
    script = (
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(argv) + '\\n')\n"
        "if argv[:2] == ['issue', 'view']:\n"
        "    print(json.dumps({'comments': [\n"
        "        {'body': '[cai track: x]\\nold', 'author': {'login': 'octocat'},\n"
        "         'url': 'https://github.com/o/r/issues/48#issuecomment-111'}]}))\n"
        "elif argv[:3] == ['api', '--method', 'PATCH']:\n"
        "    sys.stderr.write('HTTP 403: Forbidden\\n')\n"
        "    sys.exit(1)\n"
        "elif argv[:2] == ['api', 'user']:\n"
        "    print('octocat')\n"
        "else:\n"
        "    sys.exit(3)\n"
    ) % str(log)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    url, category = backend.upsert_comment(
        str(tmp_path), "48", "[cai track: x]", "[cai track: x]\nnew", "octocat")
    assert url is None
    assert category == "forbidden"

    calls = log.read_text(encoding="utf-8").splitlines()
    # still no second marked comment
    assert not any(c.startswith("issue comment") for c in calls)

    out = capsys.readouterr().out
    # a permissions message, not an identity-change one -- the login did not
    # change, so nothing here should claim it did
    assert "48" in out
    assert "permission" in out.lower()
    assert "identity" not in out.lower()


# --- non-ASCII stdout: gh always answers UTF-8, decoding must not depend on
#     the console's own locale (e2e bug report, 2026-08-31: cp950 crashed
#     mid-projection the moment the mirror comment itself carried Chinese) --

def test_upsert_comment_reads_back_non_ascii_content_it_wrote(tmp_path, monkeypatch):
    # The mirror comment's body is state.md's note, and this repo's own
    # notes are written in Chinese. `gh` always emits UTF-8 regardless of
    # the console's locale, so the fake CLI writes raw UTF-8 bytes straight
    # to the stdout pipe -- bypassing its own text-mode stdout, which on a
    # cp950 console would choke on the very content it is meant to produce.
    marker = "[cai track: x]"
    log = tmp_path / "calls.log"
    script = (
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(argv) + '\\n')\n"
        "if argv[:2] == ['issue', 'view']:\n"
        "    payload = {'comments': [\n"
        "        {'body': '[cai track: x]\\n中文筆記，投影內容',\n"
        "         'author': {'login': 'octocat'},\n"
        "         'url': 'https://github.com/o/r/issues/48#issuecomment-111'}]}\n"
        "    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False)"
        ".encode('utf-8'))\n"
        "elif argv[:3] == ['api', '--method', 'PATCH']:\n"
        "    payload = {'html_url': "
        "'https://github.com/o/r/issues/48#issuecomment-111'}\n"
        "    sys.stdout.buffer.write(json.dumps(payload).encode('utf-8'))\n"
        "else:\n"
        "    sys.exit(3)\n"
    ) % str(log)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    url, category = backend.upsert_comment(
        str(tmp_path), "48", marker, marker + "\n新的中文內容", "octocat")

    assert category == "ok"
    assert url == "https://github.com/o/r/issues/48#issuecomment-111"
    calls = log.read_text(encoding="utf-8").splitlines()
    # the marker match found the comment and updated it -- no second create
    assert not any(c.startswith("issue comment") for c in calls)


def test_invalid_byte_sequences_never_crash_the_parse(tmp_path, monkeypatch):
    # Bytes that are not valid UTF-8 at all -- errors="replace" must turn
    # this into mangled-but-decodable text, not a UnicodeDecodeError, and a
    # json.loads() that then fails on the mangled text must become
    # "unclassified", not an escaping exception.
    log = tmp_path / "calls.log"
    script = (
        "import sys\n"
        "argv = sys.argv[1:]\n"
        "with open(%r, 'a', encoding='utf-8') as fh:\n"
        "    fh.write(' '.join(argv) + '\\n')\n"
        "sys.stdout.buffer.write(b'\\xff\\xfe not valid utf-8 or json')\n"
    ) % str(log)
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()

    value, category = backend.read(str(tmp_path), "48")
    assert value is None
    assert category == "unclassified"


class _FakeCompletedProcess:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_backend_methods_never_raise_when_stdout_is_none(monkeypatch):
    # subprocess.run() itself does not raise here: a background reader
    # thread's own decode failure is swallowed by Python's default thread
    # excepthook (it only prints a traceback), leaving the CompletedProcess
    # it produces with stdout=None. No `except` clause in run() can catch
    # that -- every call site has to treat a non-str stdout as a parse
    # failure instead of assuming subprocess.run() always hands back text.
    def fake_run(*args, **kwargs):
        return _FakeCompletedProcess(0, None, "")

    monkeypatch.setattr(tb.subprocess, "run", fake_run)
    backend = tb.GitHubBackend()

    value, category = backend.whoami(".")
    assert value is None
    assert category == "unclassified"

    value, category = backend.read(".", "48")
    assert value is None
    assert category == "unclassified"

    url, category = backend.upsert_comment(".", "48", "[m]", "body", "octocat")
    assert url is None
    assert category == "unclassified"

    # transition_once never reads stdout, so a None value cannot break it --
    # this call exists only to prove that all four methods survive, not
    # just the three that parse output.
    ok, category = backend.transition_once(".", "48")
    assert category == "ok"


# --- StubBackend: registered but not this unit's job ------------------------

def test_stub_backend_is_registered_and_answers_without_a_process():
    """The registry resolves both names, and the stub is real.

    Unit 1 left this asserting NotImplementedError because the stub was a
    placeholder; unit 2 implemented it, so the assertion that matters now is
    the one AC23 rests on -- a second backend answers the same four methods
    with no external process at all."""
    stub = tb.get("local-stub")
    assert stub.name == "local-stub"
    login, category = stub.whoami(".")
    assert category in tb.CATEGORIES
    assert login


# --- observability: timeout is always passed --------------------------------

def test_every_call_passes_the_configured_timeout(tmp_path, monkeypatch):
    seen = {}
    real_run = subprocess.run

    def spy(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    script = "print('octocat')\n"
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    backend = tb.GitHubBackend()
    backend.whoami(str(tmp_path))
    assert seen["timeout"] == tb.TIMEOUT_SECONDS


# --- DD9: CAI_TICKET_CLI without an extension warns once --------------------

def test_missing_extension_warns(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(tb.CLI_ENV, str(tmp_path / "gh"))  # no extension
    backend = tb.GitHubBackend()
    backend.whoami(str(tmp_path))
    out = capsys.readouterr().out
    assert "extension" in out.lower()


# --- Blocker 2: a malformed CAI_TICKET_CLI override must not raise ---------

def test_cli_prefix_malformed_json_override_does_not_raise(monkeypatch, capsys):
    monkeypatch.setenv(tb.CLI_ENV, "[not valid json")
    argv = tb._cli_prefix()
    assert argv == ["[not valid json"]
    out = capsys.readouterr().out
    assert out != ""  # a warning, not silence -- but never an exception


def test_run_survives_a_malformed_cli_env_override(tmp_path, monkeypatch):
    # The full path a projection actually takes: run() must still return a
    # category, never propagate the JSONDecodeError _cli_prefix() used to
    # raise.
    monkeypatch.setenv(tb.CLI_ENV, "[not valid json")
    done, category = tb.run(["api", "user", "--jq", ".login"], cwd=str(tmp_path))
    assert done is None
    assert category == "unreachable"


# --- observability: one line per call, never the payload --------------------

def test_argv_summary_never_prints_the_body_it_carries():
    """The design asks for an argv *summary*. A comment body is a whole
    rendered table, and printing it verbatim both breaks the one-line
    contract and puts the table on screen on every projection."""
    body = ("[cai track: x]\nline two\n| stage | status | note |\n"
            + "| intake | done | " + "y" * 300 + " |")
    line = tb._argv_summary(["api", "--method", "PATCH",
                             "repos/o/r/issues/comments/1", "-f",
                             "body=" + body])
    assert "\n" not in line
    assert "y" * 50 not in line
    assert "api --method PATCH" in line
    assert len(line) < 200


def test_argv_summary_leaves_short_arguments_alone():
    line = tb._argv_summary(["issue", "view", "48", "--json", "comments"])
    assert line == "issue view 48 --json comments"


def test_run_prints_one_summarised_line_per_call(tmp_path, monkeypatch, capsys):
    """Asserting on run()'s real output, not just on the helper.

    The first version of this fix changed only the summary helper and one of
    run()'s two print sites, so the helper's own tests passed while the line
    a projection actually prints was unchanged. Only driving run() catches
    that."""
    script = "import sys\nsys.exit(0)\n"
    set_cli(monkeypatch, fake_cli(tmp_path, script))
    body = "line one\nline two\n" + "z" * 300
    run_out = tb.run(["api", "--method", "PATCH", "-f", "body=" + body],
                     cwd=str(tmp_path))
    printed = capsys.readouterr().out.strip()
    assert len(printed.splitlines()) == 1
    assert "z" * 50 not in printed
    # The line starts with the configured CLI prefix (here python.exe plus
    # the fake script), so the subcommand is inside it rather than at the
    # front -- what matters is that it survives summarising while the body
    # does not.
    assert "api --method PATCH" in printed
    assert printed.endswith("-> ok")
    assert run_out[1] == "ok"
