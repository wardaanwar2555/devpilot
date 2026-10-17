"""Glue between the API, the task store and the agent flows."""
from __future__ import annotations

from datetime import datetime, timezone

from ..agents.context import Deps
from ..agents.graph import build_analysis_flow, build_verification_flow
from ..config import get_settings
from ..tools import sandbox_runner
from ..tools.github_client import GitHubError, fetch_sources, inspect_repository, parse_repo_url
from ..tools.llm_client import LLMClient
from . import store


async def default_fetch_repo(url: str):
    owner, repo = parse_repo_url(url)
    meta = await inspect_repository(owner, repo)
    if not meta["eligible"]:
        raise GitHubError("No eligible Python files found in this repository.", 422)
    files, skipped = await fetch_sources(owner, repo, meta["commit"], meta["eligible"])
    meta = {k: v for k, v in meta.items() if k != "eligible"} | {"files_analyzed": len(files), "files_skipped": len(skipped)}
    return meta, files


def make_deps(task_id: str, **overrides) -> Deps:
    settings = get_settings()
    values = dict(
        settings=settings, llm=LLMClient(settings),
        emit=lambda step, status, message, kind="deterministic": store.append_event(task_id, step, status, message, kind),
        fetch_repo=default_fetch_repo,
        run_sandbox=lambda repo, tests, label: sandbox_runner.run_tests(settings, repo, tests, label),
    )
    values.update(overrides)
    return Deps(**values)


async def run_analysis(task_id: str, deps_factory=make_deps) -> None:
    row = store.get_task(task_id)
    if not row:
        return
    deps = deps_factory(task_id)
    store.update_task(task_id, status="running")
    try:
        state = {"task_id": task_id, "repository_url": row.repository_url, "task": row.task_text}
        final = await build_analysis_flow(deps).run(state, deps.settings.use_langgraph)
        awaiting = bool(final.get("patch_ok") and final.get("test"))
        if awaiting:
            deps.emit("await_approval", "waiting", "Review the diff and the test, then approve or reject.")
        store.update_task(task_id, status="awaiting_approval" if awaiting else "completed", state=final)
    except GitHubError as exc:
        store.update_task(task_id, status="failed", error=str(exc))
        deps.emit("analyze_repository", "failed", str(exc))
    except Exception as exc:  # noqa: BLE001 - surface a safe message, keep details in server logs
        import logging
        logging.getLogger("devpilot").exception("analysis failed")
        store.update_task(task_id, status="failed", error=f"Unexpected error: {exc.__class__.__name__}")
        deps.emit("analysis", "failed", f"Unexpected error: {exc.__class__.__name__}")


async def run_verification(task_id: str, deps_factory=make_deps) -> None:
    row = store.get_task(task_id)
    if not row:
        return
    deps = deps_factory(task_id)
    try:
        final = await build_verification_flow(deps).run(store.load_state(row), deps.settings.use_langgraph)
        store.update_task(task_id, status="completed", state=final)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("devpilot").exception("verification failed")
        store.update_task(task_id, status="failed", error=f"Unexpected error: {exc.__class__.__name__}")
        deps.emit("run_tests", "failed", f"Unexpected error: {exc.__class__.__name__}")


def record_rejection(task_id: str, note: str) -> None:
    from ..services.report_service import build_report
    row = store.get_task(task_id)
    state = store.load_state(row)
    state["approval"] = {"approved": False, "note": note, "at": datetime.now(timezone.utc).isoformat()}
    state["review"] = {"verdict": "not_run", "notes": []}
    state["report"] = build_report(state)
    store.update_task(task_id, status="completed", state=state)
