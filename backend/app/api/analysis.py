from fastapi import APIRouter, BackgroundTasks, Depends

from ..schemas.analysis import AnalysisRequest
from ..services import pipeline, store
from .security import current_owner, rate_limit

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("", status_code=202, dependencies=[Depends(rate_limit)])
async def start_analysis(req: AnalysisRequest, background: BackgroundTasks, owner: str = Depends(current_owner)):
    task_id = store.create_task(owner, req.repository_url, req.task)
    background.add_task(pipeline.run_analysis, task_id)
    return {"task_id": task_id, "status": "queued"}
