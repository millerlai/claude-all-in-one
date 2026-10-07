"""Unit 3: resolve_start_command -- AC2 (a) declared wins, (b) invalid has its own
exit code and no candidates, (c) the resolver never writes."""
import hashlib
import json
import os
import subprocess
import sys

import pytest

import resolve_start_command as rsc

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "plugins", "cai", "scripts", "resolve_start_command.py")

GOOD = {"start": ["npm", "run", "dev"], "ready": "http://127.0.0.1:3000/"}


def put(root, rel, text):
    path = os.path.join(str(root), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def cfg(root, obj):
    put(root, ".claude/cai.json", obj if isinstance(obj, str) else json.dumps(obj))


def pkg(root, scripts):
    put(root, "package.json", json.dumps({"scripts": scripts}))


def snapshot(root):
    out = {}
    for base, _dirs, files in os.walk(str(root)):
        for name in files:
            p = os.path.join(base, name)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, str(root))] = hashlib.sha256(fh.read()).hexdigest()
    return out


# ---- validate: accepted shapes ----

def test_validate_accepts_minimal_and_fills_e2e():
    decl, problem = rsc.validate(dict(GOOD))
    assert problem is None
    assert decl == {"start": ["npm", "run", "dev"], "ready": "http://127.0.0.1:3000/", "e2e": {}}


def test_validate_accepts_e2e_and_port_everywhere():
    group = {"start": ["node", "s.js", "--port={port}"],
             "ready": "http://localhost:{port}/health",
             "e2e": {"smoke": ["npx", "playwright", "test", "--base={port}"]}}
    decl, problem = rsc.validate(group)
    assert problem is None
    assert decl["e2e"] == {"smoke": ["npx", "playwright", "test", "--base={port}"]}


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_validate_accepts_each_loopback_host(host):
    decl, problem = rsc.validate({"start": ["x"], "ready": "http://%s:8080/up" % host})
    assert problem is None and decl is not None


def test_constants():
    assert rsc.PORT == "{port}"
    assert rsc.LOOPBACK == ("127.0.0.1", "localhost", "::1")
    assert (rsc.EXIT_DECLARED, rsc.EXIT_CANDIDATES, rsc.EXIT_UNKNOWN, rsc.EXIT_INVALID) == (0, 3, 4, 5)


# ---- validate: every Errors case names the key ----

BAD = [
    ("not an object", ["start"], "run"),
    ("missing start", {"ready": GOOD["ready"]}, "start"),
    ("missing ready", {"start": ["x"]}, "ready"),
    ("start is a string", {"start": "npm run dev", "ready": GOOD["ready"]}, "start"),
    ("start empty", {"start": [], "ready": GOOD["ready"]}, "start"),
    ("start has non-string", {"start": ["x", 1], "ready": GOOD["ready"]}, "start"),
    ("start has empty word", {"start": ["x", ""], "ready": GOOD["ready"]}, "start"),
    ("start has newline", {"start": ["x\ny"], "ready": GOOD["ready"]}, "start"),
    ("start has CR", {"start": ["x\ry"], "ready": GOOD["ready"]}, "start"),
    ("start has NUL", {"start": ["x\0y"], "ready": GOOD["ready"]}, "start"),
    ("ready not a string", {"start": ["x"], "ready": 80}, "ready"),
    ("ready https", {"start": ["x"], "ready": "https://127.0.0.1:1/"}, "ready"),
    ("ready non loopback", {"start": ["x"], "ready": "http://example.com:1/"}, "ready"),
    ("ready userinfo trick", {"start": ["x"], "ready": "http://127.0.0.1@example.com/"}, "ready"),
    ("ready newline", {"start": ["x"], "ready": "http://127.0.0.1:1/\n"}, "ready"),
    ("ready bad port", {"start": ["x"], "ready": "http://127.0.0.1:abc/"}, "ready"),
    ("ready port in path only", {"start": ["x", "{port}"], "ready": "http://127.0.0.1:1/{port}"}, "ready"),
    ("ready has port, start lacks", {"start": ["x"], "ready": "http://127.0.0.1:{port}/"}, "{port}"),
    ("start has port, ready lacks", {"start": ["x", "{port}"], "ready": GOOD["ready"]}, "{port}"),
    ("e2e not an object", {**GOOD, "e2e": ["a"]}, "e2e"),
    ("e2e value not a list", {**GOOD, "e2e": {"a": "npx t"}}, "e2e"),
    ("e2e value empty list", {**GOOD, "e2e": {"a": []}}, "e2e"),
    ("e2e word has newline", {**GOOD, "e2e": {"a": ["x\n"]}}, "e2e"),
    ("e2e port but start lacks", {**GOOD, "e2e": {"a": ["t", "{port}"]}}, "{port}"),
    ("unknown key", {**GOOD, "reday": "x"}, "reday"),
]


@pytest.mark.parametrize("label,group,key", BAD, ids=[b[0] for b in BAD])
def test_validate_rejects(label, group, key):
    decl, problem = rsc.validate(group)
    assert decl is None
    assert isinstance(problem, str) and key in problem


# ---- resolve ----

def test_declared_wins_over_candidates(tmp_path):
    """AC2 (a)."""
    cfg(tmp_path, {"run": GOOD})
    pkg(tmp_path, {"dev": "vite", "start": "node ."})
    r = rsc.resolve(str(tmp_path))
    assert r["status"] == "declared"
    assert r["declaration"]["start"] == ["npm", "run", "dev"]
    assert r["candidates"] == [] and r["problem"] is None
    assert r["root"] == str(tmp_path)


def test_invalid_has_no_candidates_even_with_a_package_json(tmp_path):
    """AC2 (b)."""
    cfg(tmp_path, {"run": {"start": "npm run dev", "ready": GOOD["ready"]}})
    pkg(tmp_path, {"dev": "vite"})
    r = rsc.resolve(str(tmp_path))
    assert r["status"] == "invalid"
    assert r["candidates"] == [] and r["declaration"] is None
    assert "start" in r["problem"]


@pytest.mark.parametrize("text", ["{not json", "[1]", '"s"', json.dumps({"run": 5}),
                                  json.dumps({"run": None})])
def test_bad_cai_json_or_run_is_invalid(tmp_path, text):
    cfg(tmp_path, text)
    pkg(tmp_path, {"dev": "vite"})
    r = rsc.resolve(str(tmp_path))
    assert r["status"] == "invalid" and r["candidates"] == [] and r["problem"]


def test_no_run_key_falls_through_to_candidates(tmp_path):
    cfg(tmp_path, {"test": {"commands": ["make test"]}})
    pkg(tmp_path, {"dev": "vite"})
    assert rsc.resolve(str(tmp_path))["status"] == "candidates"


def test_candidates_for_dev_and_start_default_npm(tmp_path):
    pkg(tmp_path, {"dev": "vite", "start": "node .", "test": "jest"})
    r = rsc.resolve(str(tmp_path))
    assert r["status"] == "candidates" and r["declaration"] is None
    assert r["candidates"] == [
        {"start": ["npm", "run", "dev"], "origin": "package.json", "script": "dev"},
        {"start": ["npm", "run", "start"], "origin": "package.json", "script": "start"}]


@pytest.mark.parametrize("lock,pm", [("package-lock.json", "npm"), ("pnpm-lock.yaml", "pnpm"),
                                     ("yarn.lock", "yarn")])
def test_lockfile_picks_the_package_manager(tmp_path, lock, pm):
    pkg(tmp_path, {"dev": "vite"})
    put(tmp_path, lock, "")
    assert rsc.resolve(str(tmp_path))["candidates"][0]["start"] == [pm, "run", "dev"]


@pytest.mark.parametrize("scripts", [{}, {"test": "jest"}, {"dev": 5}])
def test_unknown_without_a_start_script(tmp_path, scripts):
    pkg(tmp_path, scripts)
    r = rsc.resolve(str(tmp_path))
    assert r["status"] == "unknown" and r["candidates"] == []


def test_unknown_with_nothing_at_all(tmp_path):
    assert rsc.resolve(str(tmp_path))["status"] == "unknown"


@pytest.mark.parametrize("text", ["{oops", "[]", "null"])
def test_unreadable_package_json_means_no_candidates(tmp_path, text):
    put(tmp_path, "package.json", text)
    r = rsc.resolve(str(tmp_path))
    assert r["status"] == "unknown" and r["problem"] is None


def test_resolve_never_writes(tmp_path):
    """AC2 (c): same file listing and sha256 before and after."""
    cfg(tmp_path, {"run": GOOD, "test": {"commands": ["x"]}})
    pkg(tmp_path, {"dev": "vite"})
    put(tmp_path, "pnpm-lock.yaml", "")
    for _ in range(2):  # second pass: an invalid declaration must not be "repaired" either
        before = snapshot(tmp_path)
        rsc.resolve(str(tmp_path))
        run_cli(tmp_path)
        assert snapshot(tmp_path) == before
        cfg(tmp_path, "{bad")


# ---- CLI ----

def run_cli(root):
    return subprocess.run([sys.executable, SCRIPT, "--project-dir", str(root)],
                          capture_output=True, timeout=60)


@pytest.mark.parametrize("setup,code,status", [
    (lambda r: cfg(r, {"run": GOOD}), 0, "declared"),
    (lambda r: pkg(r, {"dev": "vite"}), 3, "candidates"),
    (lambda r: None, 4, "unknown"),
    (lambda r: cfg(r, {"run": {"start": ["x"]}}), 5, "invalid"),
])
def test_cli_exit_codes_and_json(tmp_path, setup, code, status):
    setup(tmp_path)
    proc = run_cli(tmp_path)
    assert proc.returncode == code
    out = json.loads(proc.stdout.decode("utf-8"))
    assert out["status"] == status
    if status == "invalid":
        assert out["candidates"] == []
