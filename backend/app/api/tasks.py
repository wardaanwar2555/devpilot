from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..schemas.analysis import ApprovalRequest
from ..services import pipeline, store
from .security import current_owner

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _row(task_id: str, owner: str):
    row = store.get_task(task_id, owner)
    if not row:
        raise HTTPException(404, "Task not found")
    return row


def _summary(row) -> dict:
    state = store.load_state(row)
    return {"id": row.id, "repository_url": row.repository_url, "task": row.task_text, "status": row.status,
            "error": row.error or "", "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
            "finding_count": len(state.get("findings", [])),
            "verdict": (state.get("report") or {}).get("verdict")}


@router.get("")
def list_tasks(owner: str = Depends(current_owner)):
    return [_summary(r) for r in store.list_tasks(owner)]


@router.get("/{task_id}")
def get_task(task_id: str, owner: str = Depends(current_owner)):
    row = _row(task_id, owner)
    state = store.load_state(row)
    return {**_summary(row), "events": store.load_events(row), "repo_meta": state.get("repo_meta"),
            "plan": state.get("plan", []), "tool_status": state.get("tool_status"),
            "has_patch": bool(state.get("patch")), "secrets_flagged": state.get("secrets_flagged", 0)}


@router.get("/{task_id}/findings")
def findings(task_id: str, owner: str = Depends(current_owner)):
    return store.load_state(_row(task_id, owner)).get("findings", [])


@router.get("/{task_id}/patch")
def patch(task_id: str, owner: str = Depends(current_owner)):
    state = store.load_state(_row(task_id, owner))
    if not state.get("patch"):
        raise HTTPException(404, "No patch was proposed for this task")
    return {"patch": state["patch"], "test": state.get("test"), "test_results": state.get("test_results"),
            "review": state.get("review"), "approval": state.get("approval")}


@router.post("/{task_id}/approve")
async def approve(task_id: str, body: ApprovalRequest, background: BackgroundTasks, owner: str = Depends(current_owner)):
    row = _row(task_id, owner)
    if row.status != "awaiting_approval":
        raise HTTPException(409, f"Task is {row.status}; only tasks awaiting approval can be approved or rejected")
    if not body.approved:
        pipeline.record_rejection(task_id, body.note)
        return {"status": "completed", "approved": False}
    state = store.load_state(row)
    state["approval"] = {"approved": True, "note": body.note, "at": datetime.now(timezone.utc).isoformat()}
    store.update_task(task_id, status="testing", state=state)
    background.add_task(pipeline.run_verification, task_id)
    return {"status": "testing", "approved": True}


@router.get("/{task_id}/report")
def report(task_id: str, owner: str = Depends(current_owner)):
    row = _row(task_id, owner)
    rep = store.load_state(row).get("report")
    if not rep:
        raise HTTPException(404, f"Report not ready (task is {row.status})")
    return rep
