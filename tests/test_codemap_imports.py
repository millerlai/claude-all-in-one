"""AC12: every codemap script imports only the standard library and its siblings.

The scripts are listed by exact file name, never globbed: a script added later
must be added here, which is the point.
"""
import ast
import os
import sys

import codemap_store

SCRIPTS_DIR = os.path.dirname(os.path.abspath(codemap_store.__file__))

# script -> sibling modules it may import besides the standard library
ALLOWED_SIBLINGS = {
    "codemap_store.py": {"preflight"},
    "codemap_inventory.py": {"preflight"},
    "codemap_symbols.py": set(),
    "codemap_repomap.py": set(),
    "codemap_index.py": {"preflight", "codemap_store", "codemap_inventory",
                         "codemap_symbols", "codemap_repomap"},
    "codemap_query.py": {"codemap_store", "codemap_inventory"},
    "codemap_cli.py": {"preflight", "codemap_store", "codemap_inventory", "codemap_index",
                       "codemap_query"},
}


def _top_level_imports(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_each_codemap_script_imports_only_stdlib_and_named_siblings():
    for script, siblings in ALLOWED_SIBLINGS.items():
        found = _top_level_imports(os.path.join(SCRIPTS_DIR, script))
        extra = found - set(sys.stdlib_module_names) - siblings
        assert not extra, (script, extra)


def test_the_listed_scripts_exist():
    for script in ALLOWED_SIBLINGS:
        assert os.path.isfile(os.path.join(SCRIPTS_DIR, script)), script
