"""Run tests inside a locked-down, disposable Docker container.

Repository code is never executed in the API process. If Docker (or the image) is missing, the
result is `unavailable` and the report says verification did not happen.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path

from ..config import Settings

MAX_OUTPUT = 20_000


@dataclass
class RunResult:
    status: str  # passed | failed | error | timeout | unavailable
    label: str = ""
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    timed_out: bool = False
    passed: int = 0
    failed: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _write(base: Path, files: dict[str, str]) -> None:
    root = base.resolve()
    for rel, content in files.items():
        target = (root / rel).resolve()
        if root not in target.parents:
            raise ValueError(f"unsafe path {rel!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _chmod_readable(base: Path) -> None:
    for p in [base, *base.rglob("*")]:
        try:
            p.chmod(0o755 if p.is_dir() else 0o644)
        except OSError:
            pass


def _count(pattern: str, text: str) -> int:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def docker_ready(settings: Settings) -> tuple[bool, str]:
    if not settings.sandbox_enabled:
        return False, "Sandbox disabled (SANDBOX_ENABLED=false)."
    if not shutil.which("docker"):
        return False, "Docker is not installed or not on PATH."
    try:
        out = subprocess.run(["docker", "image", "inspect", settings.sandbox_image],
                             capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False, "Docker did not respond. Is Docker Desktop running?"
    if out.returncode != 0:
        return False, f"Sandbox image missing. Build it: docker build -t {settings.sandbox_image} sandbox/"
    return True, ""


def run_tests(settings: Settings, repo_files: dict[str, str], test_files: dict[str, str], label: str) -> RunResult:
    ready, why = docker_ready(settings)
    if not ready:
        return RunResult(status="unavailable", label=label, note=why)

    name = f"devpilot-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="devpilot-") as tmp:
        base = Path(tmp)
        _write(base / "repo", repo_files)
        _write(base / "tests", test_files)
        _chmod_readable(base)
        # Put the repo root and every source directory on the import path.
        dirs = sorted({str(Path(p).parent).replace("\\", "/") for p in repo_files})
        pypath = ":".join(["/work/repo"] + [f"/work/repo/{d}" for d in dirs if d not in ("", ".")][:20])
        cmd = [
            "docker", "run", "--rm", "--name", name,
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", "512m", "--cpus", "1", "--pids-limit", "100",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--user", "10001:10001",
            "--mount", f"type=bind,source={base},target=/work,readonly",
            "-w", "/work",
            "-e", f"PYTHONPATH={pypath}", "-e", "PYTHONDONTWRITEBYTECODE=1",
            settings.sandbox_image,
            "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short", "/work/tests",
        ]
        start = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=settings.sandbox_timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True)
            return RunResult(status="timeout", label=label, timed_out=True,
                             duration_s=round(time.monotonic() - start, 2),
                             note=f"Killed after {settings.sandbox_timeout}s.")
        except OSError as exc:
            return RunResult(status="unavailable", label=label, note=f"Could not start Docker: {exc}")
        duration = round(time.monotonic() - start, 2)

    out, err = proc.stdout[-MAX_OUTPUT:], proc.stderr[-MAX_OUTPUT:]
    # pytest exit codes: 0 passed, 1 tests failed, 2 interrupted/collection error, 5 no tests.
    status = {0: "passed", 1: "failed"}.get(proc.returncode, "error")
    note = {2: "Collection or import error: the test could not run (often a missing dependency).",
            5: "No tests were collected."}.get(proc.returncode, "")
    if proc.returncode in (125, 126, 127):
        note = "Docker could not start the container."
    return RunResult(status=status, label=label, exit_code=proc.returncode, stdout=out, stderr=err,
                     duration_s=duration, passed=_count(r"(\d+) passed", out), failed=_count(r"(\d+) failed", out),
                     note=note)
