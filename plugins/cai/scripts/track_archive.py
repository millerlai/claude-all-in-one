#!/usr/bin/env python3
"""Copies a finished track out of a linked worktree into the main checkout,
before the worktree, and the ignored `.cai/` inside it, is removed (#468).

`.cai/` ignores itself (cai_paths.py), and removing a worktree deletes its
ignored files, so a track that `/cai:track done` or `cancel` archived under
the worktree's `.cai/track/done/` would go with it -- and so would the
glossary terms build wrote into the worktree's `.cai/cai-context.md`. Run
right after the move into `done/`, this copies the archived track directory
to the main checkout's `.cai/track/done/` (`-1`, `-2` ... when that name is
taken) and adds the worktree's glossary entries the main checkout lacks,
each under the same `## ` heading. A term both define differently keeps the
main checkout's definition and is named, for a person to settle.

Related security Contexts, their original evidence, dependency snapshots and
input documents are read before copying and saved in the archive's
`security-evidence/` afterwards. Their
project-relative paths and bytes stay unchanged, including inputs moved to done/.
Outside a linked worktree only this evidence capture runs. Every write is a file
write from this script, which Claude Code's
worktree isolation does not refuse; its Edit and Write tools would be.

Usage:  track_archive.py --track-dir DIR [--project-dir DIR]
Exit:   0 done or nothing to do, 2 the copy failed (the last line says why),
        1 usage error.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cai_paths  # noqa: E402
import glossary_check  # noqa: E402
import ledger  # noqa: E402
import preflight  # noqa: E402
import security_design  # noqa: E402

HEADING = re.compile(r"^## ")


def free_name(directory, name):
    target, n = os.path.join(directory, name), 0
    while os.path.exists(target):
        n += 1
        target = os.path.join(directory, "%s-%d" % (name, n))
    return target


def entries(text):
    """(heading, term key, line) for every glossary entry, in file order."""
    heading, out = None, []
    for line in text.splitlines():
        if HEADING.match(line):
            heading = line.rstrip()
            continue
        match = glossary_check.ENTRY.match(line)
        if match:
            out.append((heading, glossary_check.name_key(match.group("term")), line.rstrip()))
    return out


def merge_glossary(source_text, target_text):
    """(new target text, added terms, conflicting terms)."""
    have = {key: line for _, key, line in entries(target_text)}
    lines = target_text.splitlines()
    added, conflicts = [], []
    for heading, key, line in entries(source_text):
        heading = heading or "## Domain"
        if key in have:
            if have[key] != line:
                conflicts.append(line.split("**")[1])
            continue
        have[key] = line
        added.append(line.split("**")[1])
        if heading in lines:
            # After the last line of that heading's section.
            at = lines.index(heading) + 1
            while at < len(lines) and not HEADING.match(lines[at]):
                at += 1
            while at > lines.index(heading) + 1 and not lines[at - 1].strip():
                at -= 1
            lines.insert(at, line)
        else:
            lines += ["", heading, line]
    return "\n".join(lines) + "\n", added, conflicts


def write_atomic(path, text):
    # A plain open, not mkstemp: mkstemp's 0600 would replace the file's mode.
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def security_files(track_dir, project_dir):
    """Read related evidence, keyed by its original project-relative paths."""
    root, track = Path(project_dir).resolve(), Path(track_dir).resolve()
    original = track.parent.parent / track.name if track.parent.name == "done" else track
    artifacts = {original / "intake.md", track / "intake.md"}
    row = preflight.state_row(str(track), "design")
    names = [row[2]] if row is not None and len(row) > 2 else []
    names += [record.get("artifact") for record in ledger.records(str(track), "design")]
    for name in names:
        if not isinstance(name, str) or name in ("", ledger.NO_ARTIFACT):
            continue
        for base in (root, original, track):
            candidate = (base / name).resolve()
            if candidate.is_relative_to(root):
                artifacts.add(candidate)

    contexts = []
    for artifact in sorted(artifacts):
        if not artifact.is_relative_to(root):
            continue
        context = security_design.read_context(str(root), str(artifact))
        if context is None:
            continue
        if (context.get("artifact") != artifact.relative_to(root).as_posix()
                or not isinstance(context.get("provenance"), list)):
            raise security_design.SecurityFormatError("archive: malformed security Context")
        directory = Path(security_design.context_path(str(root), str(artifact))).parent
        contexts.append((artifact, directory, context))
    if not contexts:
        return {}, 0

    files = {}

    def keep(value, expected=None):
        path = security_design._project_path(str(root), str(value))
        try:
            relative = Path(os.path.abspath(root / str(value))).relative_to(root)
        except ValueError:
            raise security_design.SecurityFormatError("archive: evidence path must stay inside the project") from None
        # `done` moved track-local inputs, but their signed paths must not change.
        source = track / path.relative_to(original) if path.is_relative_to(original) else path
        source = security_design._project_path(str(root), str(source))
        if relative not in files:
            files[relative] = source.read_bytes()
        if expected is not None and (not security_design._sha(expected)
                or hashlib.sha256(files[relative]).hexdigest() != expected):
            raise security_design.SecurityFormatError("archive: security evidence fingerprint mismatch")

    for artifact, directory, context in contexts:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                keep(path)
        keep(artifact)
        for proof in context["provenance"]:
            if not isinstance(proof, dict) or not security_design._strings(proof, ("path",)):
                raise security_design.SecurityFormatError("archive: malformed security Evidence")
            keep(proof["path"], proof["sha256"])
        for dependency in context.get("dependencies") or []:
            keep(dependency["snapshot_path"], dependency["sha256"])
        if context.get("review") is not None:
            keep(context["review"]["response_path"], context["review"]["response_sha256"])
        if security_design.read_context(str(root), str(artifact)) != context:
            raise security_design.SecurityFormatError("archive: security Context changed during capture")
    if (track / "intake.md").is_file():
        keep(original / "intake.md")
    return files, len(contexts)


def write_security(archive_dir, files):
    bundle = Path(archive_dir).resolve() / "security-evidence"
    contents = {security_design._project_path(str(bundle), relative.as_posix()): content
                for relative, content in files.items()}
    for target, content in contents.items():
        if target.exists() and target.read_bytes() != content:
            raise OSError("security evidence changed after capture: %s" % target.relative_to(bundle))
    for target, content in contents.items():
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


def archive(track_dir, project_dir):
    """(exit code, lines to print)."""
    try:
        # Read everything before copying: missing evidence must leave the
        # worktree available for recovery, without a partial successful archive.
        files, captured = security_files(track_dir, project_dir)
    except (OSError, KeyError, TypeError, security_design.SecurityFormatError, ledger.LedgerError) as exc:
        return 2, ["could not preserve security evidence: %s" % exc]
    security = ["security evidence: %d Context(s) captured" % captured] if captured else []
    top, why = cai_paths.main_checkout(project_dir)
    if top is None:
        try:
            write_security(track_dir, files)
        except (OSError, security_design.SecurityFormatError) as exc:
            return 2, ["could not preserve security evidence: %s" % exc]
        return 0, security + [why]
    out = []
    try:
        cai = cai_paths.ensure_dir(top)
        done = os.path.join(cai, "track", "done")
        os.makedirs(done, exist_ok=True)
        dest = free_name(done, os.path.basename(os.path.normpath(track_dir)))
        shutil.copytree(track_dir, dest)
        write_security(dest, files)
        out.append("copied %s to %s" % (os.path.abspath(track_dir), dest))
        out += security

        source = os.path.join(project_dir, cai_paths.GLOSSARY)
        if os.path.isfile(source):
            target = os.path.join(top, cai_paths.GLOSSARY)
            with open(source, encoding="utf-8") as fh:
                source_text = fh.read()
            if not os.path.isfile(target):
                write_atomic(target, source_text)
                out.append("glossary: copied to %s" % target)
            else:
                with open(target, encoding="utf-8") as fh:
                    text, added, conflicts = merge_glossary(source_text, fh.read())
                if added:
                    write_atomic(target, text)
                out.append("glossary: %d added to %s, %d conflicting"
                           % (len(added), target, len(conflicts)))
                out += ["conflict %s: kept the main checkout's definition" % term
                        for term in conflicts]
    except (OSError, UnicodeDecodeError, security_design.SecurityFormatError) as exc:
        return 2, out + ["could not copy into the main checkout: %s" % exc]
    return 0, out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--project-dir", default=".")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.track_dir):
        print("no such track directory: %s" % args.track_dir)
        return 2
    code, lines = archive(args.track_dir, os.path.abspath(args.project_dir))
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
