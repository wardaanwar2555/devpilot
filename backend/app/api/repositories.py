from fastapi import APIRouter, Depends, HTTPException

from ..schemas.analysis import InspectRequest
from ..tools.github_client import GitHubError, inspect_repository, parse_repo_url
from .security import rate_limit

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.post("/inspect", dependencies=[Depends(rate_limit)])
async def inspect(req: InspectRequest):
    owner, repo = parse_repo_url(req.repository_url)
    try:
        meta = await inspect_repository(owner, repo)
    except GitHubError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    meta["eligible_count"] = len(meta["eligible"])
    meta["eligible"] = meta["eligible"][:50]
    return meta
