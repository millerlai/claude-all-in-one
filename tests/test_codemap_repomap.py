"""AC6: every rendered text fits budget + tolerance; an oversized map splits
into shards by directory; a map exactly at the limit is not split."""
import codemap_repomap as rm


def _file(path):
    return {"path": path, "language": "python", "backend": "python-ast",
            "confidence": "exact", "parse": "symbols", "reason": None}


def _symbol(path, n):
    return {"path": path, "qualified_name": "func_%03d" % n, "kind": "function",
            "start_line": n * 3 + 1, "end_line": n * 3 + 2,
            "signature": "(a, b=%d)" % n, "name": "func_%03d" % n}


def _repo(dirs, per_file=1, files_per_dir=2):
    files, symbols = [], []
    for d in dirs:
        for i in range(files_per_dir):
            path = "%s/mod%d.py" % (d, i) if d else "mod%d.py" % i
            files.append(_file(path))
            symbols.extend(_symbol(path, n) for n in range(per_file))
    return files, symbols


def _tokens(text):
    # The budget's own rule (#405 dropped the production helper that only
    # these tests used): characters over CHARS_PER_TOKEN, rounded up.
    return -(-len(text) // rm.CHARS_PER_TOKEN)


def _fits(texts, budget, tolerance):
    return all(_tokens(t) <= budget + tolerance for t in texts.values())


def test_constants_are_the_decided_budget():
    assert (rm.BUDGET_TOKENS, rm.TOLERANCE_TOKENS, rm.CHARS_PER_TOKEN) == (1000, 100, 4)


def test_small_repo_is_one_repo_map():
    files, symbols = _repo(["pkg"], per_file=2)
    out = rm.render(files, symbols, 1000, 100)
    assert list(out) == ["repo-map.md"]
    assert "## pkg/mod0.py (python, exact)" in out["repo-map.md"]
    assert "L1-2 function func_000(a, b=0)" in out["repo-map.md"]


def test_oversized_repo_splits_into_shards_that_each_fit():
    files, symbols = _repo(["alpha", "beta", "gamma", "delta"], per_file=30)
    budget, tolerance = 400, 40
    out = rm.render(files, symbols, budget, tolerance)
    assert len(out) > 1
    assert _fits(out, budget, tolerance)
    assert set(out) - {"repo-map.md"} <= {"packages/%s.md" % d for d in
                                          ("alpha", "beta", "gamma", "delta")}
    index = out["repo-map.md"]
    for name in out:
        if name != "repo-map.md":
            assert ".cai/codemap/" + name in index


def test_a_shard_that_still_does_not_fit_is_split_by_the_next_directory():
    files, symbols = _repo(["top/one", "top/two", "top/three"], per_file=25)
    out = rm.render(files, symbols, 400, 40)
    assert _fits(out, 400, 40)
    assert "packages/top--one.md" in out
    assert "packages/top--two.md" in out


def test_root_files_go_to_the_root_shard():
    files, symbols = _repo(["", "alpha", "beta"], per_file=30)
    out = rm.render(files, symbols, 400, 40)
    assert "packages/(root).md" in out


def test_single_file_over_budget_is_truncated_with_a_pointer():
    files = [_file("big.py")]
    symbols = [_symbol("big.py", n) for n in range(200)]
    out = rm.render(files, symbols, 200, 20)
    assert _fits(out, 200, 20)
    text = "".join(out.values())
    assert "more symbols: Grep .cai/codemap/symbols.jsonl" in text


def test_exactly_at_the_limit_is_not_split_and_one_over_is():
    files, symbols = _repo(["alpha", "beta"], per_file=5)
    full = rm.render(files, symbols, 10 ** 6, 0)["repo-map.md"]
    tokens = _tokens(full)
    assert list(rm.render(files, symbols, tokens - 10, 10)) == ["repo-map.md"]
    assert len(rm.render(files, symbols, tokens - 11, 10)) > 1


def test_same_input_gives_the_same_text():
    files, symbols = _repo(["alpha", "beta", "gamma"], per_file=30)
    assert rm.render(files, symbols, 400, 40) == rm.render(list(reversed(files)),
                                                           list(reversed(symbols)), 400, 40)


def test_too_many_packages_for_the_index_itself_truncate_with_a_pointer():
    dirs = ["dir%03d" % i for i in range(120)]
    files, symbols = _repo(dirs, per_file=3, files_per_dir=1)
    out = rm.render(files, symbols, 300, 30)
    assert _fits(out, 300, 30)
    assert "more packages: Grep .cai/codemap/files.jsonl" in out["repo-map.md"]
