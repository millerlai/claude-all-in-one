#!/usr/bin/env python3
"""The only writer of a track's pending.md. Zero deps.

A stage that cannot ask hands its questions up under `## Pending questions`;
if the session ends before they are all answered, they live only in the
conversation. This file keeps them on disk -- each question verbatim, the
round's whole report, and the answers so far -- so a later session can ask
what is still open instead of re-running the stage. The file is deliberately
not part of state.md or the ledger: nothing gates on it, and a write that
fails only falls back to the old behaviour (the round dies with the session).

Reading is forgiving and writing is strict, as in ledger.py: a command given
input it cannot use refuses and writes nothing. Text goes in by file path
only, never as an argument.

pending.md is a public contract. It starts `# pending questions`, then
`format: N`; a reader that does not know N must say so and read no further.
Change the layout and N moves up by one; load() keeps reading every old N.

Usage:  pending.py start  --track-dir DIR --stage S --round 1..3 --report-file F
        pending.py answer --track-dir DIR --question N --answer-file F
        pending.py clear  --track-dir DIR --stage S
Exit:   0 done, 2 refused or the write failed, 1 usage error.
"""
import argparse
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preflight  # noqa: E402
STAGES_JSON = os.path.join(HERE, "..", "skills", "track", "stages.json")
FILE_NAME = "pending.md"
FORMAT = 1
MAX_ROUND = 3
LABELS = ("Background", "Options", "Blocks")

ASCII_NUMBER = re.compile(r"[0-9]+")
TITLE = "# pending questions"
SECTION = re.compile(
    r"^## (?:question (\d+) \[(open|answered)\]|answer (\d+)|(report)) \((\d+) lines\)$")


class PendingError(Exception):
    """Something this script refuses to write, or a file it cannot read."""


class UnknownFormat(PendingError):
    """A well-formed header naming a format number this copy does not know."""

    def __init__(self, number):
        super().__init__("%s has format %d, which this version does not read"
                         % (FILE_NAME, number))
        self.number = number


def stage_ids():
    with open(STAGES_JSON, encoding="utf-8") as fh:
        return [row["id"] for row in json.load(fh)["stages"]]


def read_input(path):
    """A text file's content with LF line endings and no trailing newline.
    utf-8-sig because a PowerShell-written file starts with a BOM."""
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise PendingError("cannot read %s: %s" % (path, exc))
    return text.replace("\r\n", "\n").rstrip("\n")


def extract_questions(report):
    """Each question of the report's last `## Pending questions` section, as
    the exact lines the stage wrote, numbered 1..N."""
    lines = report.split("\n")
    heads = [i for i, ln in enumerate(lines) if ln.rstrip() == "## Pending questions"]
    if not heads:
        raise PendingError("the report has no `## Pending questions` section")
    body = []
    for ln in lines[heads[-1] + 1:]:
        if re.match(r"#{1,2} ", ln):
            break
        body.append(ln)
    starts = [i for i, ln in enumerate(body) if re.match(r"\d+\. ", ln)]
    if not starts:
        raise PendingError("`## Pending questions` holds no numbered question")
    if any(ln.strip() for ln in body[:starts[0]]):
        raise PendingError("text before question 1 in `## Pending questions`")
    questions = []
    for n, (start, end) in enumerate(zip(starts, starts[1:] + [len(body)]), 1):
        item = "\n".join(body[start:end]).rstrip("\n")
        if int(re.match(r"(\d+)\. ", item).group(1)) != n:
            raise PendingError("questions must be numbered 1, 2, 3 ... in order; "
                               "found %s where %d belongs"
                               % (item.split(".")[0], n))
        for label in LABELS:
            if not re.search(r"^\s*%s:" % label, item, re.M):
                raise PendingError("question %d has no `%s:` line" % (n, label))
        questions.append(item)
    return questions


def _block(header, text):
    lines = text.split("\n")
    return ["## %s (%d lines)" % (header, len(lines))] + lines + [""]


def render(stage, rnd, questions, report):
    """questions: [{"text": str, "answer": str or None}]."""
    out = [TITLE, "format: %d" % FORMAT, "stage: %s" % stage, "round: %d" % rnd,
           "questions: %d" % len(questions), ""]
    for n, q in enumerate(questions, 1):
        status = "answered" if q.get("answer") is not None else "open"
        out += _block("question %d [%s]" % (n, status), q["text"])
        if status == "answered":
            out += _block("answer %d" % n, q["answer"])
    out += _block("report", report)
    return "\n".join(out)


def load(path):
    """The parsed file: {format, stage, round, questions: [{n, status, text,
    answer}], report}. Raises UnknownFormat or PendingError, never anything
    else, so a reader can print one line and carry on."""
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PendingError("cannot read %s: %s" % (FILE_NAME, exc))
    # A person (or git's autocrlf) may have saved it with Windows line endings.
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[0] != TITLE:
        raise PendingError("%s does not start with `%s`" % (FILE_NAME, TITLE))
    head = {}
    for key in ("format", "stage", "round", "questions"):
        i = len(head) + 1
        m = re.match(r"%s: (\S+)$" % key, lines[i]) if i < len(lines) else None
        if not m:
            raise PendingError("%s is missing its `%s:` header" % (FILE_NAME, key))
        head[key] = m.group(1)
        if key == "format":
            # ASCII only: str.isdigit() is true for a superscript two, which
            # int() then rejects with a ValueError load() must never raise.
            if not ASCII_NUMBER.fullmatch(head[key]):
                raise PendingError("%s has a non-numeric format" % FILE_NAME)
            if int(head[key]) != FORMAT:
                raise UnknownFormat(int(head[key]))
    if not (ASCII_NUMBER.fullmatch(head["round"])
            and ASCII_NUMBER.fullmatch(head["questions"])):
        raise PendingError("%s has a non-numeric round or question count" % FILE_NAME)

    data = {"format": FORMAT, "stage": head["stage"], "round": int(head["round"]),
            "questions": [], "report": None}
    pos = 6  # five header lines, then one blank line
    while pos < len(lines):
        m = SECTION.match(lines[pos])
        if not m:
            raise PendingError("%s line %d is not a section header" % (FILE_NAME, pos + 1))
        count = int(m.group(5))
        body = lines[pos + 1:pos + 1 + count]
        if count < 1 or len(body) != count:
            raise PendingError("%s section at line %d is cut short" % (FILE_NAME, pos + 1))
        pos += 1 + count
        if pos < len(lines) and lines[pos] != "":
            raise PendingError("%s line %d should be blank" % (FILE_NAME, pos + 1))
        pos += 1
        text_ = "\n".join(body)
        if m.group(1):
            if int(m.group(1)) != len(data["questions"]) + 1:
                raise PendingError("%s questions are out of order" % FILE_NAME)
            data["questions"].append({"n": int(m.group(1)), "status": m.group(2),
                                      "text": text_, "answer": None})
        elif m.group(3):
            last = data["questions"][-1] if data["questions"] else None
            if not (last and last["status"] == "answered" and last["answer"] is None
                    and int(m.group(3)) == last["n"]):
                raise PendingError("%s has an answer with no question" % FILE_NAME)
            last["answer"] = text_
        else:
            data["report"] = text_
    if data["report"] is None or len(data["questions"]) != int(head["questions"]):
        raise PendingError("%s is incomplete" % FILE_NAME)
    if any(q["status"] == "answered" and q["answer"] is None for q in data["questions"]):
        raise PendingError("%s has an answered question with no answer" % FILE_NAME)
    return data


def write_atomic(path, text):
    # Temp file in the same directory, then one rename: a reader never sees
    # half a file, and a failed write leaves the old one untouched.
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=FILE_NAME + ".")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _path(track_dir):
    if not os.path.isdir(track_dir):
        raise PendingError("%s is not a directory" % track_dir)
    return os.path.join(track_dir, FILE_NAME)


def _finished(track_dir, stage):
    """True when state.md says `stage` is done or skipped: its round can no
    longer be resumed, and `track_state.py status` already calls the file
    stale and ignores it, so the writer must not let it block a later stage."""
    try:
        row = preflight.state_row(track_dir, stage)
    except (OSError, UnicodeDecodeError):
        return False
    return bool(row) and len(row) > 1 and row[1] in ("done", "skipped")


def start(track_dir, stage, rnd, report_file):
    path = _path(track_dir)
    if stage not in stage_ids():
        raise PendingError("unknown stage: %s (expected one of %s)"
                           % (stage, ", ".join(stage_ids())))
    if not 1 <= rnd <= MAX_ROUND:
        raise PendingError("round must be 1 to %d, got %d; a fourth round means "
                           "the stage failed" % (MAX_ROUND, rnd))
    report = read_input(report_file)
    questions = [{"text": t, "answer": None} for t in extract_questions(report)]
    if os.path.exists(path):
        # Another stage's round that nobody cleared is not ours to overwrite.
        # A file this script cannot read is overwritten only by refusing.
        existing = load(path)
        if existing["stage"] != stage and not _finished(track_dir, existing["stage"]):
            raise PendingError("%s already holds stage %s; clear it first"
                               % (FILE_NAME, existing["stage"]))
    write_atomic(path, render(stage, rnd, questions, report))


def answer(track_dir, number, answer_file):
    path = _path(track_dir)
    if not os.path.exists(path):
        raise PendingError("no %s in %s" % (FILE_NAME, track_dir))
    data = load(path)
    if not 1 <= number <= len(data["questions"]):
        raise PendingError("no question %d (this round has %d)"
                           % (number, len(data["questions"])))
    q = data["questions"][number - 1]
    if q["status"] == "answered":
        raise PendingError("question %d is already answered" % number)
    text = read_input(answer_file)
    if not text.strip():
        raise PendingError("the answer file is empty")
    q["answer"] = text
    write_atomic(path, render(data["stage"], data["round"], data["questions"],
                              data["report"]))


def clear(track_dir, stage):
    """Remove pending.md when it belongs to `stage`. A file for another stage
    stays; a file that cannot be read is refused, since its stage is unknown."""
    path = _path(track_dir)
    if not os.path.exists(path):
        return "no %s to clear" % FILE_NAME
    if load(path)["stage"] != stage:
        return "%s is for another stage; left alone" % FILE_NAME
    os.unlink(path)
    return "cleared %s" % FILE_NAME


class ArgParser(argparse.ArgumentParser):
    # argparse's own error() exits 2, which this script reserves for "refused".
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main(argv=None):
    # Questions and answers carry whatever alphabet a person used; a piped
    # stdout on Windows would otherwise default to the ANSI codepage.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    ap = ArgParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["start", "answer", "clear"])
    ap.add_argument("--track-dir", required=True)
    ap.add_argument("--stage")
    ap.add_argument("--round", type=int)
    ap.add_argument("--report-file")
    ap.add_argument("--question", type=int)
    ap.add_argument("--answer-file")
    args = ap.parse_args(argv)

    needs = {"start": ("stage", "round", "report_file"),
             "answer": ("question", "answer_file"),
             "clear": ("stage",)}[args.command]
    missing = [n for n in needs if getattr(args, n) is None]
    if missing:
        ap.error("%s needs --%s" % (args.command, ", --".join(m.replace("_", "-") for m in missing)))
    try:
        if args.command == "start":
            start(args.track_dir, args.stage, args.round, args.report_file)
            print("wrote %s" % os.path.join(args.track_dir, FILE_NAME))
        elif args.command == "answer":
            answer(args.track_dir, args.question, args.answer_file)
            print("recorded the answer to question %d" % args.question)
        else:
            print(clear(args.track_dir, args.stage))
    except PendingError as exc:
        print(exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("cannot write %s: %s" % (FILE_NAME, exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
