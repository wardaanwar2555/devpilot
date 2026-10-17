import subprocess

import httpx
import pytest

from app.config import get_settings
from app.tools import github_client, sandbox_runner


def _mock_github(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(github_client.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


async def test_inspect_and_fetch(monkeypatch):
    def handler(req: httpx.Request):
        url = str(req.url)
        if url.endswith("/repos/o/r"):
            return httpx.Response(200, json={"default_branch": "main", "private": False, "stargazers_count": 5, "description": "d"})
        if "/branches/main" in url:
            return httpx.Response(200, json={"commit": {"sha": "c0ffee"}})
        if "/git/trees/c0ffee" in url:
            return httpx.Response(200, json={"truncated": False, "tree": [
                {"path": "pkg/a.py", "type": "blob", "size": 20, "sha": "1"},
                {"path": "node_modules/x.py", "type": "blob", "size": 20, "sha": "2"},
                {"path": "README.md", "type": "blob", "size": 20, "sha": "3"}]})
        if url.endswith("/c0ffee/pkg/a.py"):
            return httpx.Response(200, content=b"x = 1\n")
        return httpx.Response(404)

    _mock_github(monkeypatch, handler)
    meta = await github_client.inspect_repository("o", "r")
    assert meta["commit"] == "c0ffee" and [e["path"] for e in meta["eligible"]] == ["pkg/a.py"]
    files, skipped = await github_client.fetch_sources("o", "r", meta["commit"], meta["eligible"])
    assert files == [{"path": "pkg/a.py", "content": "x = 1\n"}] and skipped == []


@pytest.mark.parametrize("status,expected", [(404, 404), (403, 429), (429, 429)])
async def test_error_mapping(monkeypatch, status, expected):
    _mock_github(monkeypatch, lambda req: httpx.Response(status, json={}))
    with pytest.raises(github_client.GitHubError) as exc:
        await github_client.inspect_repository("o", "r")
    assert exc.value.status_code == expected


async def test_private_repo_rejected(monkeypatch):
    _mock_github(monkeypatch, lambda req: httpx.Response(200, json={"default_branch": "main", "private": True}))
    with pytest.raises(github_client.GitHubError):
        await github_client.inspect_repository("o", "r")


def _ready(monkeypatch):
    monkeypatch.setattr(sandbox_runner.shutil, "which", lambda _: "/usr/bin/docker")


def test_unavailable_without_docker(monkeypatch):
    monkeypatch.setattr(sandbox_runner.shutil, "which", lambda _: None)
    r = sandbox_runner.run_tests(get_settings(), {"a.py": "x=1"}, {"t.py": "def test_a(): pass"}, "x")
    assert r.status == "unavailable" and "Docker" in r.note


def test_docker_command_is_locked_down(monkeypatch):
    _ready(monkeypatch)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="1 passed in 0.01s", stderr="")

    monkeypatch.setattr(sandbox_runner.subprocess, "run", fake_run)
    r = sandbox_runner.run_tests(get_settings(), {"pkg/a.py": "x=1"}, {"test_x.py": "def test_a(): pass"}, "patched")
    joined = " ".join(calls[-1])
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--pids-limit 100",
                 "--memory 512m", "--user 10001:10001", "readonly"):
        assert flag in joined, flag
    assert "--privileged" not in joined and "docker.sock" not in joined
    assert r.status == "passed" and r.passed == 1


@pytest.mark.parametrize("code,status", [(0, "passed"), (1, "failed"), (2, "error"), (5, "error")])
def test_exit_code_mapping(monkeypatch, code, status):
    _ready(monkeypatch)
    def fake_run(cmd, **kw):
        rc = 0 if "inspect" in cmd else code  # the image check must succeed; only pytest's exit code varies
        return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="")

    monkeypatch.setattr(sandbox_runner.subprocess, "run", fake_run)
    assert sandbox_runner.run_tests(get_settings(), {"a.py": ""}, {"t.py": ""}, "x").status == status


def test_timeout_kills_container(monkeypatch):
    _ready(monkeypatch)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "run" in cmd:
            raise subprocess.TimeoutExpired(cmd, 1)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(sandbox_runner.subprocess, "run", fake_run)
    r = sandbox_runner.run_tests(get_settings(), {"a.py": ""}, {"t.py": ""}, "x")
    assert r.status == "timeout" and any(c[:2] == ["docker", "kill"] for c in calls)


def test_path_traversal_in_workspace_is_refused(monkeypatch):
    _ready(monkeypatch)
    monkeypatch.setattr(sandbox_runner.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))
    with pytest.raises(ValueError):
        sandbox_runner.run_tests(get_settings(), {"../escape.py": "x"}, {"t.py": ""}, "x")
