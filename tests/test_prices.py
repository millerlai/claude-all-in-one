"""usage_report.py's price-table half: `load_price_table()` and
`resolve_price()` (unit 5 of the work breakdown -- the query functions
`track_report`/`range_report`/`data_start_date` are unit 6, not covered
here).

The design is docs/design/2026-08-30-track-usage-accounting-detail.md, the
`price table` section and D9/D12; each test names the Verification-table row
it stands for.
"""
import json
import os

import usage_report

SHIPPED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins", "cai", "prices.json")

SEVEN_IDENTIFIERS = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    "opus",
    "sonnet",
    "haiku",
    "<synthetic>",
)


def _override_dir(tmp_path, monkeypatch):
    """Points config_root() at an isolated directory, so a test's override
    file never touches the developer's real ~/.claude/cai/prices.json."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    override_dir = tmp_path / "cai"
    override_dir.mkdir()
    return override_dir / "prices.json"


# --- shipped table shape: seven identifiers, each classified -------------

def test_shipped_table_ships():
    assert os.path.isfile(SHIPPED_PATH)


def test_seven_measured_identifiers_each_resolve(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    table = usage_report.load_price_table()
    for identifier in SEVEN_IDENTIFIERS:
        price = usage_report.resolve_price(identifier, table)
        assert price is not None, "%s should resolve to a price" % identifier


def test_aliases_resolve_to_the_full_identifier_not_a_prefix_match(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    table = usage_report.load_price_table()
    assert usage_report.resolve_price("opus", table) == usage_report.resolve_price(
        "claude-opus-5", table)
    assert usage_report.resolve_price("sonnet", table) == usage_report.resolve_price(
        "claude-sonnet-5", table)
    assert usage_report.resolve_price("haiku", table) == usage_report.resolve_price(
        "claude-haiku-4-5-20251001", table)


def test_synthetic_is_priced_zero_not_unpriced(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    table = usage_report.load_price_table()
    price = usage_report.resolve_price("<synthetic>", table)
    assert price is not None
    assert all(rate == 0 for rate in price.values())


def test_5m_and_1h_cache_write_rates_differ_60_percent(monkeypatch, tmp_path):
    """The two ephemeral_* keys must map to different rates -- mixing them up
    silently reprices every cache write by up to 48% (see the
    implementation-notes Deviation for unit 1/2)."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    table = usage_report.load_price_table()
    price = usage_report.resolve_price("claude-opus-5", table)
    assert price["ephemeral_5m_input_tokens"] == 6.25
    assert price["ephemeral_1h_input_tokens"] == 10.00


def test_table_carries_a_version_string():
    table = usage_report.load_price_table()
    assert isinstance(table.get("version"), str) and table["version"]


# --- UC7: unpriced is None, never 0 ----------------------------------------

def test_missing_model_resolves_to_none_not_zero(monkeypatch, tmp_path):
    override_path = _override_dir(tmp_path, monkeypatch)
    with open(override_path, "w", encoding="utf-8") as fh:
        json.dump({"version": "test", "models": {}}, fh)

    # Load a shipped table with one model deliberately missing, rather than
    # the real shipped file, so the assertion is not at the mercy of
    # whichever models the real prices.json happens to ship today.
    shipped = tmp_path / "shipped.json"
    with open(shipped, "w", encoding="utf-8") as fh:
        json.dump({"version": "test-shipped", "models": {
            "claude-sonnet-5": {"input_tokens": 2.0, "output_tokens": 10.0,
                                 "cache_read_input_tokens": 0.2,
                                 "ephemeral_1h_input_tokens": 4.0,
                                 "ephemeral_5m_input_tokens": 2.5},
        }, "aliases": {}}, fh)

    table = usage_report.load_price_table(str(shipped))
    assert usage_report.resolve_price("claude-opus-5", table) is None
    assert usage_report.resolve_price("claude-sonnet-5", table) is not None


# --- per-model override merge ------------------------------------------

def test_override_changes_only_the_model_it_names(monkeypatch, tmp_path):
    override_path = _override_dir(tmp_path, monkeypatch)
    with open(override_path, "w", encoding="utf-8") as fh:
        json.dump({"models": {
            "claude-opus-5": {"input_tokens": 999.0, "output_tokens": 999.0,
                               "cache_read_input_tokens": 999.0,
                               "ephemeral_1h_input_tokens": 999.0,
                               "ephemeral_5m_input_tokens": 999.0},
        }}, fh)

    shipped_table = usage_report.load_price_table()

    overridden_opus = usage_report.resolve_price("claude-opus-5", shipped_table)
    assert overridden_opus["input_tokens"] == 999.0

    # Compare against a load with no override present: point CLAUDE_CONFIG_DIR
    # at a directory that has no cai/prices.json at all.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-override-here"))
    baseline_table = usage_report.load_price_table()
    baseline_sonnet = usage_report.resolve_price("claude-sonnet-5", baseline_table)

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    overridden_sonnet = usage_report.resolve_price("claude-sonnet-5", shipped_table)
    assert overridden_sonnet == baseline_sonnet


def test_override_count_reflects_number_of_models_overridden(monkeypatch, tmp_path):
    override_path = _override_dir(tmp_path, monkeypatch)
    with open(override_path, "w", encoding="utf-8") as fh:
        json.dump({"models": {
            "claude-opus-5": {"input_tokens": 1.0, "output_tokens": 1.0,
                               "cache_read_input_tokens": 1.0,
                               "ephemeral_1h_input_tokens": 1.0,
                               "ephemeral_5m_input_tokens": 1.0},
        }}, fh)
    table = usage_report.load_price_table()
    assert table.get("override_count") == 1


# --- broken override cannot take down the shipped table --------------------

def test_broken_json_override_falls_back_to_shipped_table(monkeypatch, tmp_path):
    override_path = _override_dir(tmp_path, monkeypatch)
    with open(override_path, "w", encoding="utf-8") as fh:
        fh.write("{ this is not json")

    table = usage_report.load_price_table()
    assert usage_report.resolve_price("claude-opus-5", table) is not None
    assert table.get("override_error")


def test_wrong_shaped_override_falls_back_to_shipped_table(monkeypatch, tmp_path):
    override_path = _override_dir(tmp_path, monkeypatch)
    with open(override_path, "w", encoding="utf-8") as fh:
        json.dump(["not", "an", "object"], fh)

    table = usage_report.load_price_table()
    assert usage_report.resolve_price("claude-opus-5", table) is not None
    assert table.get("override_error")


def test_missing_override_file_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nothing-here"))
    table = usage_report.load_price_table()
    assert usage_report.resolve_price("claude-opus-5", table) is not None
    assert not table.get("override_error")
    assert table.get("override_count") == 0
