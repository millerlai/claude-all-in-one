"""gen-models.py -- retier() must touch only the `model:` value.

The module file is hyphenated, so it is loaded through `importlib`. Its
docstring promises the rest of every file is left byte for byte alone; on
Windows a text-mode write turned every LF into CRLF (#217).
"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "plugins" / "cai" / "scripts" / "gen-models.py"

_spec = importlib.util.spec_from_file_location("gen_models", SCRIPT)
gen_models = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_models)


def test_retier_changes_only_the_model_value_and_keeps_lf_line_endings(tmp_path):
    path = tmp_path / "agent.md"
    path.write_bytes(b"---\nname: x\nmodel: haiku\n---\n\nbody line\n")
    assert gen_models.retier(path, "sonnet") == "haiku"
    assert path.read_bytes() == b"---\nname: x\nmodel: sonnet\n---\n\nbody line\n"
