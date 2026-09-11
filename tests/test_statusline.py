"""statusline.py's `render()` — the shape of the line, and the colour bands.

Two things here are easy to get wrong and impossible to notice from a
screenshot. First, every field Claude Code sends is optional at some point in a
session's life (issue #75's payload documentation, and the "Fields that may be
absent / may be null" lists in the status line docs), so `render()` has to
survive a payload with nothing in it. Second, the rate-limit windows report
*used* while the context window reports *remaining*, and this line shows all
three as remaining -- an inversion that would read as plausible either way if
it were backwards.

The colour assertions compare against the module's own constants: what is
under test is which band a number falls into, not the escape code a band is
painted with.
"""
import re

import pytest

import statusline
from statusline import GREEN, YELLOW, RED, BRIGHT_CYAN, RESET

ANSI = re.compile(r"\033\[[0-9;]*m")


def plain(line):
    return ANSI.sub("", line)


@pytest.fixture(autouse=True)
def _no_git(monkeypatch):
    """`render()` shells out to git for the branch. Left alone, every test
    below would assert on whatever branch the developer happens to be on."""
    monkeypatch.setattr(statusline, "git_branch", lambda _: "")


def ctx(remaining):
    return {"context_window": {"remaining_percentage": remaining}}


def test_empty_payload_renders_an_empty_line():
    # Claude Code runs the status line once at session start, before any of
    # this exists. Raising here would print "statusline: error" instead.
    assert statusline.render({}) == ""


def test_every_segment_appears_in_order():
    line = plain(statusline.render({
        "workspace": {"current_dir": "/home/u/proj", "repo": {"name": "cai"}},
        "model": {"display_name": "Opus 5"},
        "effort": {"level": "max"},
        "context_window": {"remaining_percentage": 92},
        "rate_limits": {"five_hour": {"used_percentage": 25},
                        "seven_day": {"used_percentage": 40}},
    }))
    assert line == "cai · Opus 5 [max] · ctx 92% · 5h 75% · 7d 60%"


def test_rate_limit_windows_are_shown_as_remaining_not_used():
    line = plain(statusline.render(
        {"rate_limits": {"five_hour": {"used_percentage": 88}}}))
    assert line == "5h 12%"


@pytest.mark.parametrize("remaining, color", [
    (100, GREEN), (50, GREEN),
    (49, YELLOW), (21, YELLOW),
    (20, RED), (0, RED),
])
def test_colour_bands(remaining, color):
    assert statusline.render(ctx(remaining)) == f"{color}ctx {remaining}%{RESET}"


def test_a_band_is_chosen_from_the_rounded_value():
    # 49.6 prints as "50%", and a 50% painted amber next to a green 50%
    # elsewhere on the line is not something anyone can debug after the fact.
    line = statusline.render(ctx(49.6))
    assert plain(line) == "ctx 50%"
    assert line.startswith(GREEN)


def test_a_null_context_percentage_is_skipped():
    # Present-but-null early in a session and again after /compact.
    assert statusline.render(ctx(None)) == ""


def test_the_project_name_is_the_brightest_thing_on_the_line():
    line = statusline.render({"workspace": {"current_dir": "/home/u/proj",
                                            "repo": {"name": "cai"}}})
    assert line == f"{BRIGHT_CYAN}cai{RESET}"


def test_the_directory_name_stands_in_when_there_is_no_origin_remote():
    line = statusline.render({"workspace": {"current_dir": "/home/u/proj"}})
    assert plain(line) == "proj"


def test_the_branch_sits_between_project_and_model(monkeypatch):
    monkeypatch.setattr(statusline, "git_branch", lambda _: "feat/x")
    line = plain(statusline.render({"workspace": {"current_dir": "/home/u/proj"},
                                    "model": {"display_name": "Sonnet 5"}}))
    assert line == "proj · feat/x · Sonnet 5"


def test_effort_is_dropped_on_a_model_that_has_none():
    # Absent, not empty, for any model without the reasoning-effort parameter.
    line = plain(statusline.render({"model": {"display_name": "Haiku 4.5"}}))
    assert line == "Haiku 4.5"
