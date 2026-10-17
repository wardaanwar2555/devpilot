from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..config import Settings
from ..tools.llm_client import LLMClient
from ..tools.sandbox_runner import RunResult


@dataclass
class Deps:
    """Everything the workflow needs from the outside world (injectable for tests)."""
    settings: Settings
    llm: LLMClient
    emit: Callable[..., None]  # emit(step, status, message, kind="deterministic")
    fetch_repo: Callable[[str], Awaitable[tuple[dict, list[dict]]]]
    run_sandbox: Callable[[dict[str, str], dict[str, str], str], RunResult]


def window(content: str, line: int, radius: int = 25) -> str:
    lines = content.splitlines()
    return "\n".join(lines[max(0, line - 1 - radius): line + radius])


def file_map(state: dict[str, Any]) -> dict[str, str]:
    return {f["path"]: f["content"] for f in state.get("files", [])}
