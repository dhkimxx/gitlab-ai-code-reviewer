import os
from typing import Iterable, List

from src.shared.types import GitDiffChange


_ALLOWED_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".go",
    ".rb",
    ".rs",
    ".swift",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".hpp",
    ".cs",
    ".php",
    ".scala",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".dockerfile",
}
_ALLOWED_CODE_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "CMakeLists.txt",
}


def is_code_file(path: str) -> bool:
    filename = os.path.basename(path)
    if filename in _ALLOWED_CODE_FILENAMES:
        return True

    _, ext = os.path.splitext(path.lower())
    return ext in _ALLOWED_CODE_EXTENSIONS


def collect_candidate_paths(changes: Iterable[GitDiffChange], max_files: int) -> List[str]:
    results: List[str] = []
    seen: set[str] = set()

    for change in changes:
        if change.get("deleted_file"):
            continue

        path = change.get("new_path") or change.get("old_path")
        if not path:
            continue
        if path in seen:
            continue
        if not is_code_file(path):
            continue

        seen.add(path)
        results.append(path)
        if len(results) >= max_files:
            break

    return results


def truncate_text(content: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(content)
    if len(content) <= max_chars:
        return content, False
    return content[:max_chars], True
