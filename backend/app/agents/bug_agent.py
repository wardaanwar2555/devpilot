"""Bug analysis agent.

The model may only *annotate* findings that static tools already produced. It cannot invent new
findings, which keeps hallucinated bugs out of the report.
"""
from __future__ import annotations

from ..tools.llm_client import LLMError
from ..tools.secrets import redact
from ..services.ranker import rank_findings
from .context import Deps, file_map, window

VERDICTS = {"likely_bug", "possible_false_positive", "style_only"}
MAX_ANNOTATED = 12


async def run(state: dict, deps: Deps) -> dict:
    findings = rank_findings(state["findings"])
    if not deps.llm.enabled:
        deps.emit("detect_issues", "done", f"{len(findings)} findings ranked by heuristic (LLM not configured).")
        return {"findings": findings}

    files = file_map(state)
    top = [f for f in findings if f["severity"] != "info"][:MAX_ANNOTATED]
    blocks = []
    for f in top:
        code = redact(window(files.get(f["path"], ""), f["line"], 8))
        blocks.append(f"id: {f['id']}\nrule: {f['rule_id']} ({f['title']}) at {f['path']}:{f['line']}\n"
                      f"<untrusted_code>\n{code}\n</untrusted_code>")
    prompt = (
        "For each candidate finding below, judge it from the code shown. Return JSON: "
        '{"annotations":[{"id":"...","verdict":"likely_bug|possible_false_positive|style_only","explanation":"<=2 sentences"}]}. '
        "Only use ids from the list. Do not add new findings.\n\n" + "\n\n".join(blocks)
    )
    try:
        result = await deps.llm.complete_json(prompt, max_tokens=1500)
        by_id = {f["id"]: f for f in findings}
        applied = 0
        for a in result.get("annotations", []):
            f = by_id.get(a.get("id"))
            if f and a.get("verdict") in VERDICTS:
                f["llm_verdict"], f["llm_explanation"] = a["verdict"], str(a.get("explanation", ""))[:400]
                applied += 1
        deps.emit("detect_issues", "done", f"Model annotated {applied} of {len(top)} top findings.", "llm")
    except LLMError as exc:
        deps.emit("detect_issues", "done", f"Model unavailable ({exc}); kept static-analysis ranking.")
    return {"findings": rank_findings(findings)}
