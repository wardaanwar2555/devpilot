"""Deterministic analysis: Python AST checks + Ruff + Bandit.

Nothing here imports or executes the analysed code. Findings are *candidates*:
only syntax errors are marked `confirmed`.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

from .secrets import redact

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_MARKER = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")


def finding_id(path: str, line: int, rule_id: str) -> str:
    return hashlib.sha1(f"{path}:{line}:{rule_id}".encode()).hexdigest()[:10]


def make_finding(*, path, line, title, severity, category, details, rule_id, source,
                 source_text=None, confirmed=False, next_step="") -> dict:
    evidence = ""
    if source_text is not None:
        lines = source_text.splitlines()
        if 1 <= line <= len(lines):
            evidence = redact(lines[line - 1].strip())[:200]
    return {
        "id": finding_id(path, line, rule_id), "title": title, "severity": severity, "category": category,
        "path": path, "line": line, "details": redact(details), "evidence": evidence, "rule_id": rule_id,
        "source": source, "confirmed": confirmed, "next_step": next_step,
        "priority_score": 0.0, "ml_severity": None, "llm_verdict": None, "llm_explanation": None,
    }


# --------------------------------------------------------------------------- AST
class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, source: str):
        self.path, self.source, self.findings = path, source, []

    def _add(self, **kw):
        self.findings.append(make_finding(path=self.path, source="ast", source_text=self.source, **kw))

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        swallow = all(isinstance(s, ast.Pass) for s in node.body)
        if node.type is None:
            self._add(
                line=node.lineno, title="Bare except clause", severity="medium", category="reliability",
                rule_id="devpilot.bare-except",
                details="Catches every exception, including KeyboardInterrupt and SystemExit"
                        + (", and discards it silently." if swallow else "."),
                next_step="Catch the specific exception types you expect, or at least `Exception`.",
            )
        elif swallow:
            self._add(
                line=node.lineno, title="Exception silently ignored", severity="low", category="reliability",
                rule_id="devpilot.silent-except",
                details="The handler body is only `pass`, so failures disappear without a trace.",
                next_step="Log the error or handle it explicitly.",
            )
        self.generic_visit(node)

    def _check_defaults(self, node):
        defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
        for d in defaults:
            mutable = isinstance(d, (ast.List, ast.Dict, ast.Set)) or (
                isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in {"list", "dict", "set"}
            )
            if mutable:
                self._add(
                    line=d.lineno, title="Mutable default argument", severity="medium", category="correctness",
                    rule_id="devpilot.mutable-default",
                    details="Default values are created once, so state leaks between calls.",
                    next_step="Use `None` as the default and create the object inside the function.",
                )

    def visit_FunctionDef(self, node):
        self._check_defaults(node)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


def analyze_source(source: str, path: str) -> list[dict]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [make_finding(
            path=path, line=exc.lineno or 1, title="Python syntax error", severity="high", category="syntax",
            details=f"{exc.msg}. The file does not parse with Python {sys.version_info.major}.{sys.version_info.minor}.",
            rule_id="devpilot.syntax-error", source="ast", source_text=source, confirmed=True,
            next_step="Fix the syntax. (Python 2 code will also report this.)",
        )]
    visitor = _Visitor(path, source)
    visitor.visit(tree)
    findings = visitor.findings
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT and (m := _MARKER.search(tok.string)):
                findings.append(make_finding(
                    path=path, line=tok.start[0], title=f"{m.group(1)} marker", severity="info", category="maintenance",
                    details="Unfinished work is marked in a comment.", rule_id="devpilot.todo", source="ast",
                    source_text=source, next_step="Resolve it or track it in an issue.",
                ))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return findings


# ------------------------------------------------------------------ Ruff / Bandit
_RUFF_HIGH = {"F821", "F822", "F823"}
_RUFF_LOW = {"F841", "F811", "E711", "E712", "F541"}
_RUFF_SELECT = "F,B,E711,E712"
_RUFF_IGNORE = "F401,B006,B008,B904,B007,B905,F403,F405"  # noisy, or already covered by AST checks


def _write_tree(files: dict[str, str], base: Path) -> None:
    root = base.resolve()
    for rel, content in files.items():
        target = (root / rel).resolve()
        if root not in target.parents:  # path traversal guard
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def run_ruff(files: dict[str, str]) -> tuple[list[dict], str]:
    if not files:
        return [], "skipped"
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_tree(files, base)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", "--output-format", "json",
                 "--select", _RUFF_SELECT, "--ignore", _RUFF_IGNORE, "."],
                cwd=base, capture_output=True, text=True, timeout=90,
            )
            data = json.loads(proc.stdout or "[]")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            return [], f"unavailable ({exc.__class__.__name__})"
        out = []
        for item in data:
            code = item.get("code")
            if not code:
                continue
            rel = str(Path(item["filename"]).resolve().relative_to(base.resolve())).replace("\\", "/")
            sev = "high" if code in _RUFF_HIGH else "low" if code in _RUFF_LOW else "medium"
            out.append(make_finding(
                path=rel, line=item["location"]["row"], title=item["message"][:120], severity=sev,
                category="correctness" if code.startswith("F") else "bug-risk",
                details=f"Ruff rule {code}: {item['message']}. A lint rule flags a *potential* defect, not a proven one.",
                rule_id=code, source="ruff", source_text=files.get(rel),
                next_step="Check the surrounding code to see whether this is a real defect.",
            ))
        return out, "ok"


def run_bandit(files: dict[str, str]) -> tuple[list[dict], str]:
    if not files:
        return [], "skipped"
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write_tree(files, base)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "bandit", "-r", str(base), "-f", "json", "-q", "--skip", "B101"],
                capture_output=True, text=True, timeout=90,
            )
            data = json.loads(proc.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            return [], f"unavailable ({exc.__class__.__name__})"
        out = []
        for item in data.get("results", []):
            rel = str(Path(item["filename"]).resolve().relative_to(base.resolve())).replace("\\", "/")
            sev = {"HIGH": "high", "MEDIUM": "medium"}.get(item["issue_severity"], "low")
            out.append(make_finding(
                path=rel, line=item["line_number"], title=item["issue_text"][:120], severity=sev,
                category="security", rule_id=item["test_id"], source="bandit", source_text=files.get(rel),
                details=f"Bandit {item['test_id']} ({item['test_name']}), confidence {item['issue_confidence'].lower()}: "
                        f"{item['issue_text']}",
                next_step="Review whether untrusted input can reach this code.",
            ))
        return out, "ok"


def analyze_files(files: list[dict], run_external: bool = True) -> tuple[list[dict], dict]:
    """Run every analyzer. Returns (findings, tool_status)."""
    findings: list[dict] = []
    status = {"ast": "ok", "ruff": "skipped", "bandit": "skipped"}
    for f in files:
        findings += analyze_source(f["content"], f["path"])
    broken = {x["path"] for x in findings if x["rule_id"] == "devpilot.syntax-error"}
    parseable = {f["path"]: f["content"] for f in files if f["path"] not in broken}
    if run_external:
        ruff_f, status["ruff"] = run_ruff(parseable)
        bandit_f, status["bandit"] = run_bandit(parseable)
        findings += ruff_f + bandit_f
    unique = {}
    for f in findings:
        unique.setdefault(f["id"], f)
    ordered = sorted(unique.values(), key=lambda x: (-SEVERITY_RANK[x["severity"]], x["path"], x["line"]))
    return ordered, status
