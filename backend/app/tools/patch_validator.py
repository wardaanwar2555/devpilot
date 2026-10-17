"""Patch building and validation.

The model never hands us a diff to execute. It proposes (old_snippet, new_snippet); we apply that
to the fetched file ourselves and *generate* the unified diff with difflib. The result is validated
before a human sees it.
"""
from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass, field, asdict
from pathlib import PurePosixPath


class PatchError(Exception):
    pass


@dataclass
class Validation:
    ok: bool
    problems: list[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def check_path(path: str, allowed: set[str]) -> str | None:
    """Return a problem description, or None when the path is acceptable."""
    if not path or "\x00" in path:
        return "empty or invalid path"
    if path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path) or "\\" in path:
        return "absolute or non-POSIX path"
    if ".." in PurePosixPath(path).parts:
        return "path traversal"
    if path not in allowed:
        return "file was not part of the analysed repository"
    return None


def build_unified_diff(path: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile=f"a/{path}", tofile=f"b/{path}", n=3,
    ))


def apply_snippet(content: str, old_snippet: str, new_snippet: str) -> str:
    if not old_snippet.strip():
        raise PatchError("old_snippet is empty")
    count = content.count(old_snippet)
    if count == 0:
        raise PatchError("old_snippet was not found in the file (the model must copy it exactly)")
    if count > 1:
        raise PatchError(f"old_snippet appears {count} times; it must be unique")
    return content.replace(old_snippet, new_snippet, 1)


def materialize(original: str, proposal: dict) -> str:
    """Produce the patched file content from a proposal."""
    if proposal.get("new_content") is not None:
        return proposal["new_content"]
    return apply_snippet(original, proposal.get("old_snippet", ""), proposal.get("new_snippet", ""))


def diff_paths(diff: str) -> set[str]:
    paths = set()
    for line in diff.splitlines():
        if line.startswith(("--- ", "+++ ")):
            name = line[4:].split("\t")[0].strip()
            if name != "/dev/null":
                paths.add(re.sub(r"^[ab]/", "", name))
    return paths


def validate_patch(files: dict[str, str], proposal: dict, max_changed_lines: int = 80) -> tuple[Validation, str | None, str]:
    """Validate a proposal. Returns (validation, patched_content, unified_diff)."""
    problems: list[str] = []
    path = proposal.get("file", "")
    if (issue := check_path(path, set(files))):
        return Validation(False, [f"Rejected path {path!r}: {issue}"]), None, ""
    original = files[path]
    try:
        patched = materialize(original, proposal)
    except PatchError as exc:
        return Validation(False, [str(exc)]), None, ""
    if patched == original:
        return Validation(False, ["The patch changes nothing"]), None, ""
    diff = build_unified_diff(path, original, patched)
    if diff_paths(diff) - {path}:
        problems.append("Diff touches more than the selected file")
    added = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    if added + removed > max_changed_lines:
        problems.append(f"Patch changes {added + removed} lines (limit {max_changed_lines})")
    if path.endswith(".py"):
        try:
            ast.parse(patched)
        except SyntaxError as exc:
            try:
                ast.parse(original)
                problems.append(f"Patched file has a syntax error at line {exc.lineno}: {exc.msg}")
            except SyntaxError:
                # the original was already broken; it is only a problem if the fix did not fix it
                problems.append(f"Patched file still has a syntax error at line {exc.lineno}: {exc.msg}")
    return Validation(not problems, problems, added, removed), patched, diff
