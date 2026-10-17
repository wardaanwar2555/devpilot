from app.agents.context import Deps
from app.config import get_settings
from app.tools.llm_client import LLMClient, LLMError
from app.tools.sandbox_runner import RunResult

REPO_FILES = [
    {"path": "app/io.py", "content": "def read(p):\n    try:\n        return open(p).read()\n    except:\n        return None\n"},
    {"path": "app/ok.py", "content": "def add(a, b):\n    return a + b\n"},
]


class ScriptedLLM(LLMClient):
    """Returns queued JSON replies; raises LLMError when the queue is empty."""
    def __init__(self, replies=()):
        super().__init__(get_settings())
        self.replies, self.prompts = list(replies), []

    @property
    def enabled(self):
        return True

    async def complete_json(self, user, max_tokens=1800):
        self.prompts.append(user)
        if not self.replies:
            raise LLMError("no scripted reply")
        return self.replies.pop(0)


def make_test_deps(files=REPO_FILES, llm=None, sandbox=None, events=None):
    events = events if events is not None else []

    async def fetch(url):
        return {"repository": "o/r", "branch": "main", "commit": "abc1234567"}, [dict(f) for f in files]

    def default_sandbox(repo, tests, label):
        # Simulates a real run: the pattern test fails on original code and passes on patched code.
        bad = "except:" in repo.get("app/io.py", "")
        return RunResult(status="failed" if bad else "passed", label=label, exit_code=1 if bad else 0,
                         passed=0 if bad else 1, failed=1 if bad else 0)

    return Deps(settings=get_settings(), llm=llm or LLMClient(get_settings()),
                emit=lambda step, status, msg, kind="deterministic": events.append((step, status, kind)),
                fetch_repo=fetch, run_sandbox=sandbox or default_sandbox), events
