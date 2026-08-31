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
