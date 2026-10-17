import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import pipeline
from app.tools import sandbox_runner
from app.tools.sandbox_runner import RunResult
from helpers import REPO_FILES

client = TestClient(app)


@pytest.fixture
def fake_backends(monkeypatch):
    async def fetch(url):
        return {"repository": "o/r", "branch": "main", "commit": "abc1234567"}, [dict(f) for f in REPO_FILES]

    def run(settings, repo, tests, label):
        bad = "except:" in repo.get("app/io.py", "")
        return RunResult(status="failed" if bad else "passed", label=label, exit_code=1 if bad else 0)

    monkeypatch.setattr(pipeline, "default_fetch_repo", fetch)
    monkeypatch.setattr(sandbox_runner, "run_tests", run)


def test_health():
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and "sandbox_ready" in body


def test_rejects_invalid_repo_url():
    assert client.post("/api/analysis", json={"repository_url": "https://evil.com/a/b"}).status_code == 422


def test_full_flow_with_approval_gate(fake_backends):
    resp = client.post("/api/analysis", json={"repository_url": "https://github.com/o/r"})
    assert resp.status_code == 202
    tid = resp.json()["task_id"]

    task = client.get(f"/api/tasks/{tid}").json()
    assert task["status"] == "awaiting_approval" and task["finding_count"] >= 1
    assert client.get(f"/api/tasks/{tid}/report").status_code == 404      # nothing verified yet
    assert client.get(f"/api/tasks/{tid}/findings").json()[0]["id"]
    patch = client.get(f"/api/tasks/{tid}/patch").json()
    assert "except Exception:" in patch["patch"]["unified_diff"] and patch["test"]["code"]

    assert client.post(f"/api/tasks/{tid}/approve", json={"approved": True}).json()["status"] == "testing"
    report = client.get(f"/api/tasks/{tid}/report").json()
    assert report["verdict"] == "verified" and report["approval"]["approved"] is True
    assert client.post(f"/api/tasks/{tid}/approve", json={"approved": True}).status_code == 409  # no double approval
    assert len(client.get("/api/tasks").json()) == 1


def test_rejection_produces_unverified_report(fake_backends):
    tid = client.post("/api/analysis", json={"repository_url": "https://github.com/o/r"}).json()["task_id"]
    client.post(f"/api/tasks/{tid}/approve", json={"approved": False, "note": "not now"})
    report = client.get(f"/api/tasks/{tid}/report").json()
    assert report["verdict"] == "not_run" and report["approval"]["approved"] is False


def test_unknown_task_and_auth(monkeypatch):
    assert client.get("/api/tasks/nope").status_code == 404
    monkeypatch.setenv("DEVPILOT_API_KEY", "s3cret")
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/tasks", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_task_isolation_between_owners(fake_backends, monkeypatch):
    monkeypatch.setenv("DEVPILOT_API_KEY", "key-a")
    tid = client.post("/api/analysis", json={"repository_url": "https://github.com/o/r"},
                      headers={"Authorization": "Bearer key-a"}).json()["task_id"]
    monkeypatch.setenv("DEVPILOT_API_KEY", "key-b")
    assert client.get(f"/api/tasks/{tid}", headers={"Authorization": "Bearer key-b"}).status_code == 404
