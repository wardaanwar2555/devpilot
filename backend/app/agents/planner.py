from __future__ import annotations

from ..tools.llm_client import LLMError
from .context import Deps

# Findings the repair agent can plausibly fix without understanding the whole project.
SKIP_RULES = {"devpilot.todo"}


def candidates(findings: list[dict]) -> list[dict]:
    return [f for f in findings
            if f["rule_id"] not in SKIP_RULES and f["severity"] != "info"
            and f.get("llm_verdict") not in ("possible_false_positive", "style_only")]


async def run(state: dict, deps: Deps) -> dict:
    pool = candidates(state["findings"])[: deps.settings.max_plan_steps * 3]
    if not pool:
        deps.emit("create_plan", "done", "No actionable findings, so no repair plan was created.")
        return {"plan": []}
    plan = [{"finding_id": f["id"], "path": f["path"], "line": f["line"], "title": f["title"],
             "action": f["next_step"] or "Investigate and fix.", "rationale": f"Priority score {f['priority_score']}."}
            for f in pool[: deps.settings.max_plan_steps]]
    kind = "deterministic"
    if deps.llm.enabled:
        listing = "\n".join(f"- id {f['id']}: {f['title']} ({f['rule_id']}, {f['severity']}) {f['path']}:{f['line']}"
                            for f in pool)
        prompt = (f"User task: {state['task'][:500]}\nCandidate findings:\n{listing}\n"
                  'Return JSON {"steps":[{"finding_id":"...","action":"one sentence","rationale":"one sentence"}]} '
                  f"with at most {deps.settings.max_plan_steps} steps, most important first. Use only the ids above.")
        try:
            result = await deps.llm.complete_json(prompt, max_tokens=700)
            by_id = {f["id"]: f for f in pool}
            steps = []
            for s in result.get("steps", []):
                f = by_id.get(s.get("finding_id"))
                if f and all(x["finding_id"] != f["id"] for x in steps):
                    steps.append({"finding_id": f["id"], "path": f["path"], "line": f["line"], "title": f["title"],
                                  "action": str(s.get("action", ""))[:300], "rationale": str(s.get("rationale", ""))[:300]})
            if steps:
                plan, kind = steps[: deps.settings.max_plan_steps], "llm"
        except LLMError as exc:
            deps.emit("create_plan", "running", f"Model unavailable ({exc}); using heuristic plan.")
    deps.emit("create_plan", "done", f"Planned {len(plan)} step(s); the first will be attempted.", kind)
    return {"plan": plan}
