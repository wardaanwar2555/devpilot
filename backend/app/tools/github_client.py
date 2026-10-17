"""Read-only GitHub access. Never clones and never executes repository code."""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote

import httpx

from ..config import get_settings

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

_URL_RE = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
EXCLUDED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "build", "dist",
    "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "vendor", "third_party", "generated",
}
_SENSITIVE = re.compile(r"(^|/)(\.env.*|.*\.(pem|key|p12|pfx)|id_[rd]sa.*|.*secret.*|.*credential.*)$", re.I)
_GENERATED = re.compile(r"_pb2(_grpc)?\.py$")


class GitHubError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def parse_repo_url(url: str) -> tuple[str, str]:
    """Accept only https://github.com/<owner>/<repo>. Anything else is rejected."""
    match = _URL_RE.match(url.strip())
    if not match:
        raise ValueError("Use a public GitHub repository URL like https://github.com/owner/repo")
    owner, repo = match.group(1), match.group(2)
    if owner in {".", ".."} or repo in {".", ".."}:
        raise ValueError("Invalid repository name")
    return owner, repo


def is_eligible_path(path: str) -> bool:
    if not path.endswith(".py") or path.startswith("/") or ".." in path.split("/"):
        return False
    if any(part in EXCLUDED_DIRS for part in path.split("/")[:-1]):
        return False
    return not (_SENSITIVE.search(path) or _GENERATED.search(path))


def select_eligible(tree: list[dict], max_files: int, max_file_bytes: int, max_total_bytes: int) -> list[dict]:
    """Pick Python source files within the configured limits (non-test code first)."""
    candidates = [
        {"path": e["path"], "size": e.get("size", 0), "sha": e.get("sha", "")}
        for e in tree
        if e.get("type") == "blob" and is_eligible_path(e["path"]) and 0 < e.get("size", 0) <= max_file_bytes
    ]
    candidates.sort(key=lambda e: ("test" in e["path"].lower(), e["size"], e["path"]))
    chosen, total = [], 0
    for entry in candidates:
        if len(chosen) >= max_files or total + entry["size"] > max_total_bytes:
            continue
        chosen.append(entry)
        total += entry["size"]
    return chosen


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _get_json(client: httpx.AsyncClient, url: str) -> dict:
    try:
        response = await client.get(url, headers=_headers())
    except httpx.HTTPError as exc:
        raise GitHubError(f"Could not reach GitHub: {exc.__class__.__name__}") from exc
    if response.status_code == 404:
        raise GitHubError("Repository not found, or it is private. Only public repositories are supported.", 404)
    if response.status_code in (403, 429):
        raise GitHubError("GitHub rate limit reached. Set GITHUB_TOKEN in backend/.env or try again later.", 429)
    if response.status_code >= 400:
        raise GitHubError(f"GitHub returned HTTP {response.status_code}")
    return response.json()


async def inspect_repository(owner: str, repo: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        meta = await _get_json(client, f"{API}/repos/{owner}/{repo}")
        if meta.get("private"):
            raise GitHubError("Private repositories are not supported.", 403)
        branch = meta["default_branch"]
        branch_info = await _get_json(client, f"{API}/repos/{owner}/{repo}/branches/{quote(branch)}")
        commit = branch_info["commit"]["sha"]
        tree = await _get_json(client, f"{API}/repos/{owner}/{repo}/git/trees/{commit}?recursive=1")
    entries = tree.get("tree", [])
    eligible = select_eligible(entries, settings.max_files, settings.max_file_bytes, settings.max_total_bytes)
    py_total = sum(1 for e in entries if e.get("type") == "blob" and e["path"].endswith(".py"))
    return {
        "repository": f"{owner}/{repo}",
        "description": meta.get("description") or "",
        "stars": meta.get("stargazers_count", 0),
        "branch": branch,
        "commit": commit,
        "tree_truncated": bool(tree.get("truncated")),
        "python_files_total": py_total,
        "eligible": eligible,
    }


async def fetch_sources(owner: str, repo: str, commit: str, entries: list[dict]) -> tuple[list[dict], list[str]]:
    """Download file contents at an exact commit. Returns (files, skipped_paths)."""
    settings = get_settings()
    sem = asyncio.Semaphore(8)

    async def one(client: httpx.AsyncClient, entry: dict):
        url = f"{RAW}/{owner}/{repo}/{commit}/{quote(entry['path'])}"
        async with sem:
            try:
                resp = await client.get(url)
            except httpx.HTTPError:
                return entry["path"], None
        if resp.status_code != 200 or len(resp.content) > settings.max_file_bytes:
            return entry["path"], None
        try:
            return entry["path"], resp.content.decode("utf-8")
        except UnicodeDecodeError:
            return entry["path"], None

    async with httpx.AsyncClient(timeout=20) as client:
        results = await asyncio.gather(*(one(client, e) for e in entries))
    files = [{"path": p, "content": c} for p, c in results if c is not None]
    skipped = [p for p, c in results if c is None]
    return files, skipped
