#!/usr/bin/env python3
"""A person's own tier -> model choice, applied to this installed cai plugin.

models.json says which tier (chore/build/think) each component plays and which
model each tier defaults to; gen-models.py writes those defaults into the
source tree. This is the per-user half. The choice lives outside the plugin, at
`<config root>/cai/model-choice.json` (CLAUDE_CONFIG_DIR, else ~/.claude), so
`/plugin update` never touches it, and every assigned component's frontmatter
`model:` line in the plugin root this script sits in is rewritten to match.
`/cai:models` runs `show` and `set`/`reset`; the SessionStart hook runs
`apply --hook`, which puts the choice back into a copy an update just
installed with cai's defaults.

    model_choice.py show
    model_choice.py set <tier>=<model> [<tier>=<model> ...]
    model_choice.py reset [<tier> ...]       # every tier when none is named
    model_choice.py apply [--hook]

Claude Code reads a component's `model:` when a session starts, so a rewrite
takes effect after a restart. A plugin's source tree -- a checkout or a
marketplace clone, with `.claude-plugin/marketplace.json` two levels up -- is
never rewritten: that would put one person's choice into what everyone
installs.

Exit: 0 ok; 1 a file could not be read, parsed or written, or the root is a
source tree; 2 bad arguments. `apply --hook` always exits 0.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import usage_collector  # noqa: E402

FORMAT = 1
# An alias or a full model id, and nothing a YAML scalar or a shell could read
# as more than one word -- the shape the Codex installer accepts too.
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}\Z")
# Offered on the menu beside each tier's own default. Any other model stays
# reachable by typing its name, so a new family needs no cai release first.
KNOWN_ALIASES = ("haiku", "sonnet", "opus", "fable")
MENU_MAX = 4  # options per question the menu tool accepts
# Bytes, not text: an installed copy may be CRLF, and only the value may move.
MODEL_LINE = re.compile(rb"^model:[ \t]*(\S+)[ \t]*\r?$", re.MULTILINE)


def choice_path():
    return Path(usage_collector.config_root()) / "cai" / "model-choice.json"


def load_spec(root):
    spec = json.loads((root / "models.json").read_text(encoding="utf-8"))
    return spec["roles"], spec["assignments"]


def load_choice(path, roles):
    """The saved tier -> model map, {} when there is no file. A tier
    models.json no longer has, or a value that is not a model name, is left
    out rather than failing the whole choice."""
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not (isinstance(data, dict) and data.get("format") == FORMAT
            and isinstance(data.get("roles"), dict)):
        raise ValueError(f"{path} is not a format-{FORMAT} model choice")
    return {tier: model for tier, model in data["roles"].items()
            if tier in roles and isinstance(model, str) and MODEL_RE.match(model)}


def write_atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_choice(path, choice):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"format": FORMAT, "roles": choice}, indent=2) + "\n"
    write_atomic(path, text.encode("utf-8"))


def is_source_tree(root):
    return (root.parent.parent / ".claude-plugin" / "marketplace.json").is_file()


def in_effect(roles, choice):
    return {tier: choice.get(tier, role["alias"]) for tier, role in roles.items()}


def rewrite(root, assignments, models):
    """Set each assigned component's frontmatter `model:` value to its tier's
    model; every other byte, line endings included, stays as it was. Returns
    the relative paths it changed."""
    changed = []
    for rel, tier in sorted(assignments.items()):
        path = root / rel
        data = path.read_bytes()
        end = data.find(b"\n---", 3) if data.startswith(b"---") else -1
        match = MODEL_LINE.search(data, 0, end) if end != -1 else None
        want = models[tier].encode("ascii")
        if match is None or match.group(1) == want:
            continue
        write_atomic(path, data[:match.start(1)] + want + data[match.end(1):])
        changed.append(rel)
    return changed


def component(rel):
    parts = rel.split("/")
    return f"/cai:{parts[1]}" if parts[0] == "skills" else parts[-1][:-len(".md")]


def mapping_lines(roles, assignments, choice):
    models = in_effect(roles, choice)
    lines = []
    for tier, role in roles.items():
        tag = (f"saved; cai default {role['alias']}" if tier in choice else "cai default")
        names = ", ".join(component(rel) for rel, t in sorted(assignments.items()) if t == tier)
        lines.append(f"tier {tier}: {models[tier]} ({tag}) -- {names}")
    return lines


def offer_lines(roles, choice):
    models = in_effect(roles, choice)
    lines = []
    for tier, role in roles.items():
        order = []
        for model in (models[tier], role["alias"]) + KNOWN_ALIASES:
            if model not in order:
                order.append(model)
        entries = []
        for model in order[:MENU_MAX]:
            marks = [mark for mark, hit in (("in effect", model == models[tier]),
                                            ("cai default", model == role["alias"])) if hit]
            entries.append(f"{model} ({', '.join(marks)})" if marks else model)
        lines.append(f"offer {tier}: {', '.join(entries)}")
    return lines


def parse_answers(answers, roles):
    """[(tier, model)] from `tier=model` words, or a ValueError naming the
    first bad one -- checked before anything is written."""
    parsed = []
    for word in answers:
        tier, sep, model = word.partition("=")
        if not sep or tier not in roles:
            raise ValueError(f"{word!r}: expected <tier>=<model>, tier one of {', '.join(roles)}")
        if not MODEL_RE.match(model):
            raise ValueError(f"{word!r}: {model!r} is not a model name "
                             f"(allowed: {MODEL_RE.pattern})")
        parsed.append((tier, model))
    return parsed


def report(roles, assignments, choice, changed):
    for line in mapping_lines(roles, assignments, choice):
        print(line)
    if changed:
        print(f"rewrote {len(changed)} file(s); restart Claude Code to use the new models")
    else:
        print("no file needed rewriting")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    sub.add_parser("set").add_argument("answers", nargs="+", metavar="TIER=MODEL")
    sub.add_parser("reset").add_argument("tiers", nargs="*", metavar="TIER")
    sub.add_parser("apply").add_argument("--hook", action="store_true")
    args = ap.parse_args(argv)

    if args.command == "apply" and args.hook:
        return apply_hook()

    try:
        roles, assignments = load_spec(ROOT)
    except (OSError, ValueError, KeyError) as e:
        print(f"cannot read {ROOT / 'models.json'}: {e}")
        return 1

    if args.command == "set":
        try:
            answers = parse_answers(args.answers, roles)
        except ValueError as e:
            print(e)
            return 2
    if args.command == "reset":
        unknown = [t for t in args.tiers if t not in roles]
        if unknown:
            print(f"unknown tier(s): {', '.join(unknown)}; tier one of {', '.join(roles)}")
            return 2

    path = choice_path()
    try:
        choice = load_choice(path, roles)
    except (OSError, ValueError) as e:
        print(f"cannot read the saved choice, not overwritten: {e}")
        return 1

    if args.command == "show":
        for line in mapping_lines(roles, assignments, choice) + offer_lines(roles, choice):
            print(line)
        print(f"choice file: {path}")
        return 0

    if is_source_tree(ROOT):
        print(f"{ROOT} is a plugin source tree, not an installed copy; "
              "a choice is applied to installed copies only")
        return 1

    if args.command == "set":
        for tier, model in answers:
            if model == roles[tier]["alias"]:
                choice.pop(tier, None)
            else:
                choice[tier] = model
    elif args.command == "reset":
        for tier in args.tiers or list(choice):
            choice.pop(tier, None)

    try:
        if args.command in ("set", "reset"):
            save_choice(path, choice)
        changed = rewrite(ROOT, assignments, in_effect(roles, choice))
    except OSError as e:
        print(f"cannot update the saved choice or the installed copy: {e}")
        return 1
    report(roles, assignments, choice, changed)
    return 0


def apply_hook():
    """SessionStart: put the saved choice back, say so only when a file
    changed, and never fail -- a session must start whatever happens here."""
    try:
        if is_source_tree(ROOT):
            return 0
        roles, assignments = load_spec(ROOT)
        choice = load_choice(choice_path(), roles)
        changed = rewrite(ROOT, assignments, in_effect(roles, choice))
        message = (f"cai: re-applied your model choice to {len(changed)} file(s); "
                   "restart Claude Code for it to take effect." if changed else None)
    except Exception as e:  # noqa: BLE001 -- never block a session start
        message = f"cai: could not apply your model choice ({e}); run /cai:models to check it."
    if message:
        print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
