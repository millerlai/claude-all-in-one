#!/usr/bin/env python3
"""Which skills and agents were configured, and which ones ever actually ran.

GAP-06 asks "what did we install and never use". `agent-radar` cannot answer
it: its session output carries totals (`skill_calls: 33`) and no names, and its
scanner only looks under `.claude/`, so a repo that ships its skills from
`plugins/cai/` reads as having none. Both are recorded in
docs/design/2026-08-29-capability-gap-analysis.md under GAP-06.

The data was never the problem -- it is in the session logs, one JSON object
per line, and a `Skill` tool_use carries `input.skill` while an `Agent`
tool_use carries `input.subagent_type`. This groups by that name.

Counting DAYS, not calls, is deliberate. "Used 40 times in one afternoon" and
"used once a week for eight weeks" are different facts about whether something
earns its place, and the second is the one that matters.

Usage:  activation.py [--projects DIR] [--root DIR ...] [--days N] [--json]
Exit:   0 report written, 1 usage error.
"""
import argparse
import collections
import datetime
import glob
import json
import os
import sys

DEFAULT_PROJECTS = os.path.expanduser("~/.claude/projects")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Deliberately NOT `~/.claude` whole: that tree contains plugins/cache/,
# several hundred SKILL.md belonging to other people's plugins. Counting
# those produces a "313 never used" list that must not be acted on, which is
# the exact failure this measurement exists to avoid. Pass --root to widen.
DEFAULT_ROOTS = [os.path.join(HERE, "plugins", "cai"),
                 os.path.expanduser("~/.claude/skills"),
                 os.path.expanduser("~/.claude/agents")]


def frontmatter_name(path):
    """The `name:` a component declares, or None.

    This has to come from the file, not the directory. gstack ships a skill at
    `.../skills/gstack-browse/SKILL.md` whose frontmatter says `name: browse`,
    and it is `browse` that appears in the session log. Deriving the name from
    the folder listed a skill used 6 times across 5 days as never invoked --
    the exact way a measurement talks you into cutting something that works."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            if fh.readline().strip() != "---":
                return None
            for line in fh:
                if line.strip() == "---":
                    return None
                if line.startswith("name:"):
                    return line.split(":", 1)[1].strip().strip('"\'') or None
    except OSError:
        return None
    return None


def invocation_name(path, kind):
    """The name a component is called by: its declared `name:`, prefixed with
    the plugin that ships it. `plugins/cai/skills/track/SKILL.md` is invoked as
    `cai:track`; a skill in `~/.claude/skills/` is invoked bare."""
    parts = os.path.normpath(path).split(os.sep)
    declared = frontmatter_name(path)
    fallback = parts[-2] if kind == "skill" else os.path.splitext(parts[-1])[0]
    name = declared or fallback
    if "plugins" in parts:
        plugin = parts[parts.index("plugins") + 1]
        return "%s:%s" % (plugin, name)
    return name


def short(path):
    """Path relative to the repo when that is meaningful, absolute when not.
    relpath raises across Windows drive letters, and a crash while printing a
    report is a silly way to lose the report."""
    try:
        return os.path.relpath(path, HERE)
    except ValueError:
        return path


# A vendored dependency tree is somebody else's internals, not configuration
# anyone chose. Playwright ships files under `lib/agents/*.md` that are not
# agents in this sense at all, and counting them as "configured but never
# invoked" is noise on top of the one list this script exists to produce.
SKIP_DIRS = {"node_modules", ".git", "__pycache__"}


def configured(roots):
    """Every skill and agent under `roots`: name -> (path, the root it came from).

    Walking rather than globbing a fixed depth: the whole point is not to
    repeat agent-radar's mistake of only recognising one directory layout."""
    found = {"skill": {}, "agent": {}}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            parts = dirpath.split(os.sep)
            if "SKILL.md" in filenames and "skills" in parts:
                path = os.path.join(dirpath, "SKILL.md")
                found["skill"][invocation_name(path, "skill")] = (path, root)
            if parts and parts[-1] == "agents":
                for name in filenames:
                    if name.endswith(".md"):
                        path = os.path.join(dirpath, name)
                        found["agent"][invocation_name(path, "agent")] = (path, root)
    return found


def activated(projects_dir, since=None):
    """Every Skill and Agent invocation in the session logs, by name.

    Reading is forgiving throughout: a log being written while this runs ends
    in a half line, and one unreadable line must not cost the whole report."""
    use = {"skill": collections.defaultdict(set), "agent": collections.defaultdict(set)}
    calls = {"skill": collections.Counter(), "agent": collections.Counter()}
    files = sorted(glob.glob(os.path.join(projects_dir, "*", "*.jsonl")))
    for path in files:
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                day = (rec.get("timestamp") or "")[:10]
                if since and day and day < since:
                    continue
                content = (rec.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    args = block.get("input") or {}
                    if block.get("name") == "Skill":
                        kind, name = "skill", args.get("skill")
                    elif block.get("name") == "Agent":
                        kind, name = "agent", args.get("subagent_type")
                    else:
                        continue
                    if not name:
                        continue
                    calls[kind][name] += 1
                    if day:
                        use[kind][name].add(day)
    return files, calls, use


def report(kind, conf, calls, days, out):
    ours = sorted(conf)
    seen = sorted(calls, key=lambda n: (-len(days[n]), -calls[n], n))
    # Width from the data, so one long name cannot shear the whole table.
    width = max([len(n) for n in list(ours) + list(seen)] + [16])

    print("\n=== %s: %d configured, %d ever invoked" % (kind, len(ours), len(seen)),
          file=out)
    print("%-*s %6s %6s  %s" % (width, "name", "calls", "days", "configured here?"),
          file=out)
    for name in seen:
        print("%-*s %6d %6d  %s" % (width, name, calls[name], len(days[name]),
                                    "yes" if name in conf else "elsewhere"), file=out)

    # Grouped by root, because "5 of our 9 agents" is the finding and it must
    # not be read off a list where somebody else's bundle supplies the bulk.
    never = [n for n in ours if n not in calls]
    print("\n-- configured but never invoked (%d of %d):" % (len(never), len(ours)),
          file=out)
    by_root = collections.defaultdict(list)
    for name in never:
        by_root[conf[name][1]].append(name)
    for root in sorted(by_root):
        group = by_root[root]
        total = sum(1 for n in ours if conf[n][1] == root)
        print("   %s  (%d of %d)" % (short(root), len(group), total), file=out)
        for name in group:
            print("      %s" % name, file=out)
    return never


BLIND_SPOTS = """
-- what this cannot see, so nobody reads a zero as a verdict:
   rules/*.md          never invoked by name; they are prepended to context.
                       Their usage cannot be measured this way at all.
   hooks, commands     do not appear in the session logs as tool_use.
   one busy day        a component used 40 times in one afternoon shows as
                       1 day. Days are the honest unit; calls are context.
   reachability        a component only reachable through another unused one
                       is ONE finding, not two. Five agents dispatched by a
                       skill nobody ran are evidence about the skill.
   reference files     a stage followed by reading its reference .md is not a
                       Skill invocation and will always count zero here.
   this is not a cut list. A count answers "was it used", never "is it
   right" -- a rule can be load-bearing and rarely tripped. Measuring the
   wrong thing is how you delete a rule that was doing its job.
"""


class ArgParser(argparse.ArgumentParser):
    # Same convention as the plugin's scripts: a usage mistake exits 1.
    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        sys.exit(1)


def main():
    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("--projects", default=DEFAULT_PROJECTS,
                    help="session log root (default: ~/.claude/projects)")
    ap.add_argument("--root", action="append", dest="roots", default=None,
                    help="where to look for configured components; repeatable")
    ap.add_argument("--days", type=int, default=None,
                    help="only count invocations from the last N days")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    roots = args.roots or DEFAULT_ROOTS
    since = None
    if args.days:
        since = (datetime.date.today()
                 - datetime.timedelta(days=args.days)).isoformat()

    conf = configured(roots)
    files, calls, days = activated(args.projects, since)

    if args.json:
        json.dump({kind: {"configured": {n: short(v[0]) for n, v in conf[kind].items()},
                          "calls": dict(calls[kind]),
                          "days": {n: sorted(d) for n, d in days[kind].items()}}
                   for kind in ("skill", "agent")},
                  sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0

    print("session logs: %d file(s) under %s%s"
          % (len(files), args.projects, " since %s" % since if since else ""))
    print("configured roots: %s" % ", ".join(roots))
    for kind in ("skill", "agent"):
        report(kind, conf[kind], calls[kind], days[kind], sys.stdout)
    print(BLIND_SPOTS)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
