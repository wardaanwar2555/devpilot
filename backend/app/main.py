from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import analysis, repositories, tasks
from .config import get_settings
from .tools.sandbox_runner import docker_ready

settings = get_settings()
app = FastAPI(title="DevPilot AI API", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=list(settings.cors_origins),
    allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"],
)
app.include_router(repositories.router)
app.include_router(analysis.router)
app.include_router(tasks.router)


@app.get("/api/health")
def health():
    s = get_settings()
    sandbox_ok, sandbox_note = docker_ready(s)
    return {"status": "ok", "project": "DevPilot AI", "llm_configured": bool(s.llm_api_key),
            "sandbox_ready": sandbox_ok, "sandbox_note": sandbox_note, "auth_required": bool(s.api_key)}
