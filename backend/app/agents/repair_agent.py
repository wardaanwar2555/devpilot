"""Repair agent: rule-based fixers first (exact and cheap), the model for everything else."""
from __future__ import annotations

import re

from ..tools.llm_client import LLMError
from ..tools.secrets import redact
from .context import Deps, file_map, window


def _line_fix(content: str, line: int, transform) -> tuple[str, str] | None:
    lines = content.splitlines(keepends=True)
    if not 1 <= line <= len(lines):
        return None
    new_line = transform(lines[line - 1])
    if new_line == lines[line - 1]:
        return None
    lines[line - 1] = new_line
    return "".join(lines), lines[line - 1]


def _bare_except(line: str) -> str:
    return re.sub(r"^(\s*)except\s*:", r"\1except Exception:", line)


def _none_comparison(line: str) -> str:
    return re.sub(r"!=\s*None\b", "is not None", re.sub(r"==\s*None\b", "is None", line))


RULE_FIXERS = {
    "devpilot.bare-except": (_bare_except, "Replace the bare `except:` with `except Exception:` so system-exit signals are not swallowed."),
    "E711": (_none_comparison, "Compare to None with `is` / `is not`, as PEP 8 recommends."),
}


async def run(state: dict, deps: Deps) -> dict:
    step = state["plan"][0]
    finding = next(f for f in state["findings"] if f["id"] == step["finding_id"])
    files = file_map(state)
    original = files[finding["path"]]
    attempt = state.get("retries", 0)

    if attempt == 0 and finding["rule_id"] in RULE_FIXERS:
        transform, why = RULE_FIXERS[finding["rule_id"]]
        fixed = _line_fix(original, finding["line"], transform)
        if fixed:
            deps.emit("propose_patch", "done", "Applied a deterministic rule-based fix.", "rule")
            return {"proposal": {"file": finding["path"], "finding_id": finding["id"], "explanation": why,
                                 "new_content": fixed[0], "source": "rule", "tests_to_add": []}}

    if not deps.llm.enabled:
        deps.emit("propose_patch", "done", "No rule-based fix exists for this finding and no LLM is configured.")
        return {"proposal": None}

    feedback = f"\nYour previous attempt was rejected: {state['last_patch_error']}\n" if state.get("last_patch_error") else ""
    prompt = (
        f"Fix this issue with the smallest possible change.\nFinding: {finding['title']} ({finding['rule_id']}) "
        f"at {finding['path']}:{finding['line']}\nDetails: {finding['details']}\n{feedback}"
        f"<untrusted_code>\n{redact(window(original, finding['line'], 30))}\n</untrusted_code>\n"
        'Return JSON {"old_snippet":"<text copied EXACTLY from the code, unique in the file, <=30 lines>",'
        '"new_snippet":"<replacement>","explanation":"<=3 sentences","cannot_fix":false}. '
        'If you cannot fix it safely, return {"cannot_fix":true,"explanation":"why"}.'
    )
    try:
        result = await deps.llm.complete_json(prompt, max_tokens=1500)
    except LLMError as exc:
        deps.emit("propose_patch", "done", f"Model failed ({exc}); no patch proposed.")
        return {"proposal": None}
    if result.get("cannot_fix") or not result.get("old_snippet"):
        deps.emit("propose_patch", "done", "Model declined to patch: " + str(result.get("explanation", ""))[:200], "llm")
        return {"proposal": None, "patch_declined": True}
    deps.emit("propose_patch", "done", "Model proposed a patch (unverified).", "llm")
    return {"proposal": {"file": finding["path"], "finding_id": finding["id"], "source": "llm",
                         "explanation": str(result.get("explanation", ""))[:600],
                         "old_snippet": str(result["old_snippet"]), "new_snippet": str(result.get("new_snippet", "")),
                         "tests_to_add": []}}
