"""#450: a query skips the file-text scan only when no text hit can rank.

A text hit scores at most TEXT_LINE_CAP; once `limit` index hits score strictly
more, no text hit can enter the first `limit` rows, so the bodies stay unread.
Everywhere else the full scan runs, and the rows are the ones it always gave."""
import pytest

import codemap_index as idx
import codemap_inventory as inventory
import codemap_query
import codemap_store
from codemap_repo import make_repo

FILES = {
    "needle_a.py": "def needle():\n    return 1\n",
    "needle_b.py": "def needle_two():\n    return 'needle'\n",
    "needle_c.py": "def needle_three():\n    pass\n",
    "notes.md": "needle\nneedle\nNEEDLE\n",
    "other.txt": "a needle here\n",
    "log.md": "needle\n" * 6,      # six matching lines: a text hit held at the cap
}


@pytest.fixture
def repo(tmp_path):
    make_repo(tmp_path, FILES)
    idx.build(str(tmp_path))
    return str(tmp_path), codemap_store.load(str(tmp_path))


def _count_reads(monkeypatch):
    reads = []
    real = inventory.read_tracked

    def counting(*args, **kwargs):
        reads.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(inventory, "read_tracked", counting)
    return reads


def _hit(score):
    return codemap_query.Hit(score, "p", 1, "path", "p")


@pytest.mark.parametrize("limit", [1, 2, 3, 6])   # 6 index hits: the last limit that fills
def test_filled_limit_leaves_the_bodies_unread(repo, monkeypatch, limit):
    top, index = repo
    reads = _count_reads(monkeypatch)
    hits = codemap_query.query(top, index, "needle", limit)
    assert len(hits) == limit and all(h.score > codemap_query.TEXT_LINE_CAP for h in hits)
    assert reads == []


def test_an_unfilled_limit_still_scans_every_body(repo, monkeypatch):
    top, index = repo
    reads = _count_reads(monkeypatch)
    codemap_query.query(top, index, "needle", 1000)
    assert sorted(reads) == sorted(FILES)


@pytest.mark.parametrize("limit", [-3, -1, 0, 1, 2, 3, 5, 10, 1000])
def test_rows_match_the_full_scan(repo, monkeypatch, limit):
    top, index = repo
    got = codemap_query.query(top, index, "needle", limit)
    monkeypatch.setattr(codemap_query, "_text_cannot_rank", lambda hits, n: False)
    assert got == codemap_query.query(top, index, "needle", limit)


@pytest.mark.parametrize("limit", [1, 2, 3, 10])
def test_a_capped_text_hit_still_ranks_when_index_scores_are_low(repo, monkeypatch, limit):
    # Real weights keep every index hit above the cap, so the gate never has to
    # let a text hit through; with every weight at 1 it must, and log.md's
    # capped text hit (5) outranks the best index hit (4).
    top, index = repo
    for weight in ("NAME_EQUALS", "NAME_HAS", "QUALIFIED_HAS", "PATH_HAS"):
        monkeypatch.setattr(codemap_query, weight, 1)
    got = codemap_query.query(top, index, "needle", limit)
    assert (got[0].kind, got[0].score, got[0].path) == ("text", codemap_query.TEXT_LINE_CAP, "log.md")
    monkeypatch.setattr(codemap_query, "_text_cannot_rank", lambda hits, n: False)
    assert got == codemap_query.query(top, index, "needle", limit)


def test_the_gate_is_strict_and_positive_only():
    cap = codemap_query.TEXT_LINE_CAP
    assert codemap_query._text_cannot_rank([_hit(cap + 1)] * 2, 2)
    assert not codemap_query._text_cannot_rank([_hit(cap + 1), _hit(cap)], 2)  # tie: full scan
    assert not codemap_query._text_cannot_rank([_hit(cap + 1)], 2)             # fewer than limit
    assert not codemap_query._text_cannot_rank([_hit(cap + 1)], 0)
    assert not codemap_query._text_cannot_rank([_hit(cap + 1)], -1)


def test_the_gate_reads_the_limit_th_best_score_of_more_hits_than_the_limit():
    cap = codemap_query.TEXT_LINE_CAP
    high, low = _hit(cap + 1), _hit(cap)
    # The 2nd best is cap + 1 wherever the hits sit in the list; a gate that
    # skipped the sort, read the worst score, or sorted ascending gets one wrong.
    assert codemap_query._text_cannot_rank([low, low, high, high], 2)
    assert codemap_query._text_cannot_rank([high, high, low, low], 2)
    assert codemap_query._text_cannot_rank([high, low, high, high], 2)
    assert not codemap_query._text_cannot_rank([high, low, low, low], 2)   # 2nd best is a tie
    assert not codemap_query._text_cannot_rank([low, high, low, low], 2)


def test_a_failed_listing_still_raises_when_the_scan_is_skipped(repo, monkeypatch):
    top, index = repo

    def broken(_top):
        raise inventory.GitFailed("git ls-files failed")

    monkeypatch.setattr(inventory, "list_tracked", broken)
    with pytest.raises(inventory.GitFailed):
        codemap_query.query(top, index, "needle", 2)
