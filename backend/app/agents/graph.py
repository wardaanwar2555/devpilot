"""Agent workflow. Two phases separated by a mandatory human-approval gate.

Phase 1: analyze -> detect -> plan -> propose patch -> validate (retry loop) -> generate tests -> [pause]
Phase 2 (only after approval): run tests in the sandbox -> review -> report
The same graph definition runs on LangGraph when installed, or on a small built-in runner.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, TypedDict

from ..services.report_service import build_report, compute_verdict
from ..tools import patch_validator
from ..tools.github_client import parse_repo_url
from ..tools.llm_client import LLMError
from ..tools.secrets import count_secrets, redact
from ..tools.static_analyzer import analyze_files
from . import bug_agent, planner, repair_agent, test_agent
from .context import Deps, file_map

END = "__end__"


class DevPilotState(TypedDict, total=False):
    task_id: str
    repository_url: str
    task: str
    repo_meta: dict
    files: list
    skipped: list
    tool_status: dict
    secrets_flagged: int
    findings: list
    plan: list
    proposal: dict | None
    patch_declined: bool
    retries: int
    last_patch_error: str
    patch_ok: bool
    patch: dict | None
    patched_files: dict
    test: dict
    test_results: dict
    review: dict
    approval: dict
    report: dict


class Flow:
    def __init__(self, entry: str, nodes: dict[str, Callable], edges: dict[str, Any]):
        self.entry, self.nodes, self.edges = entry, nodes, edges

    async def run(self, state: dict, use_langgraph: bool = True) -> dict:
        if use_langgraph:
            graph = self._compile_langgraph()
            if graph is not None:
                return await graph.ainvoke(state)
        current = self.entry
        while current != END:
            state = {**state, **(await self.nodes[current](state))}
            nxt = self.edges[current]
            current = nxt(state) if callable(nxt) else nxt
        return state

    def _compile_langgraph(self):
        try:
            from langgraph.graph import StateGraph, START
        except ImportError:
            return None
        g = StateGraph(DevPilotState)
        for name, fn in self.nodes.items():
            g.add_node(name, fn)
        g.add_edge(START, self.entry)
        for name, nxt in self.edges.items():
            if callable(nxt):
                g.add_conditional_edges(name, nxt)
            else:
                g.add_edge(name, END if nxt == END else nxt)
        return g.compile()


# --------------------------------------------------------------------------- phase 1
def build_analysis_flow(deps: Deps) -> Flow:
    cfg = deps.settings

    async def analyze_repository(state):
        deps.emit("analyze_repository", "running", "Fetching repository source (read-only, no cloning).")
        meta, files = await deps.fetch_repo(state["repository_url"])
        deps.emit("analyze_repository", "running", f"Fetched {len(files)} Python files. Running AST, Ruff and Bandit.")
        findings, status = await asyncio.to_thread(analyze_files, files)
        secrets = sum(count_secrets(f["content"]) for f in files)
        deps.emit("analyze_repository", "done", f"{len(findings)} candidate findings from static tools.")
        return {"repo_meta": meta, "files": files, "findings": findings, "tool_status": status,
                "secrets_flagged": secrets, "retries": 0}

    async def detect_issues(state):
        deps.emit("detect_issues", "running", "Ranking findings.")
        return await bug_agent.run(state, deps)

    async def create_plan(state):
        deps.emit("create_plan", "running", "Planning repairs.")
        return await planner.run(state, deps)

    async def propose_patch(state):
        deps.emit("propose_patch", "running", "Proposing a patch." if not state.get("retries") else
                  f"Retrying (attempt {state['retries'] + 1}).")
        return await repair_agent.run(state, deps)

    async def validate_patch(state):
        proposal = state.get("proposal")
        if not proposal:
            deps.emit("validate_patch", "skipped", "Nothing to validate.")
            return {"patch_ok": False, "patch": None}
        deps.emit("validate_patch", "running", "Checking path, size, applicability and syntax.")
        validation, patched, diff = patch_validator.validate_patch(file_map(state), proposal, cfg.max_patch_lines)
        if not validation.ok:
            msg = "; ".join(validation.problems)
            deps.emit("validate_patch", "failed", f"Rejected: {msg}")
            return {"patch_ok": False, "retries": state.get("retries", 0) + 1, "last_patch_error": msg, "patch": None}
        finding = next(f for f in state["findings"] if f["id"] == proposal["finding_id"])
        deps.emit("validate_patch", "done", f"Patch is valid (+{validation.lines_added}/-{validation.lines_removed}).")
        patch = {"file": proposal["file"], "finding_id": finding["id"], "finding_title": finding["title"],
                 "explanation": proposal["explanation"], "unified_diff": diff, "source": proposal["source"],
                 "validation": validation.as_dict(), "original": file_map(state)[proposal["file"]], "patched": patched}
        return {"patch_ok": True, "patch": patch, "patched_files": {proposal["file"]: patched}}

    async def generate_tests(state):
        deps.emit("generate_tests", "running", "Writing a regression test.")
        return await test_agent.run(state, deps)

    async def generate_report(state):
        deps.emit("report", "running", "Compiling report.")
        report = build_report(state)
        deps.emit("report", "done", "Report ready.")
        return {"report": report}

    def after_plan(state):
        return "propose_patch" if state.get("plan") else "generate_report"

    def after_validate(state):
        if state.get("patch_ok"):
            return "generate_tests"
        if state.get("proposal") and not state.get("patch_declined") and state.get("retries", 0) <= cfg.max_retries:
            return "propose_patch"
        return "generate_report"

    nodes = {"analyze_repository": analyze_repository, "detect_issues": detect_issues, "create_plan": create_plan,
             "propose_patch": propose_patch, "validate_patch": validate_patch, "generate_tests": generate_tests,
             "generate_report": generate_report}
    edges = {"analyze_repository": "detect_issues", "detect_issues": "create_plan", "create_plan": after_plan,
             "propose_patch": "validate_patch", "validate_patch": after_validate, "generate_tests": END,
             "generate_report": END}
    return Flow("analyze_repository", nodes, edges)


# --------------------------------------------------------------------------- phase 2
def build_verification_flow(deps: Deps) -> Flow:
    async def run_tests(state):
        deps.emit("run_tests", "running", "Running tests in the isolated sandbox (original code, then patched code).")
        original = file_map(state)
        patched = {**original, **state["patched_files"]}
        tests = {state["test"]["path"]: state["test"]["code"]}
        baseline = await asyncio.to_thread(deps.run_sandbox, original, tests, "original code")
        if baseline.status == "unavailable":
            deps.emit("run_tests", "failed", baseline.note)
            return {"test_results": {"baseline": baseline.as_dict(), "patched": baseline.as_dict()}}
        after = await asyncio.to_thread(deps.run_sandbox, patched, tests, "patched code")
        deps.emit("run_tests", "done", f"Original: {baseline.status}. Patched: {after.status}.")
        return {"test_results": {"baseline": baseline.as_dict(), "patched": after.as_dict()}}

    async def review(state):
        deps.emit("review", "running", "Weighing the evidence.")
        res = state["test_results"]
        review = {"verdict": compute_verdict(res.get("baseline"), res.get("patched")), "notes": []}
        if deps.llm.enabled and state.get("patch"):
            prompt = ('List up to 3 regression risks of this diff. Return JSON {"risks":["..."]}.\n'
                      f"<untrusted_code>\n{redact(state['patch']['unified_diff'][:4000])}\n</untrusted_code>")
            try:
                review["notes"] = [str(r)[:300] for r in (await deps.llm.complete_json(prompt, 500)).get("risks", [])[:3]]
            except LLMError:
                pass
        deps.emit("review", "done", f"Verdict: {review['verdict'].replace('_', ' ')}.")
        return {"review": review}

    async def generate_report(state):
        deps.emit("report", "running", "Compiling report.")
        report = build_report(state)
        deps.emit("report", "done", "Report ready.")
        return {"report": report}

    return Flow("run_tests", {"run_tests": run_tests, "review": review, "generate_report": generate_report},
                {"run_tests": "review", "review": "generate_report", "generate_report": END})
