from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any
import sys


def import_lexicon_tool_module(module_name: str) -> Any:
    try:
        return import_module(module_name)
    except ModuleNotFoundError as exc:
        if not exc.name or not exc.name.startswith("tools"):
            raise
        repo_root = _find_repo_root(Path(__file__).resolve())
        if repo_root is None:
            raise
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        return import_module(module_name)


def _find_repo_root(start_path: Path) -> Path | None:
    for candidate in start_path.parents:
        if (candidate / "tools" / "lexicon").exists():
            return candidate
    return None
