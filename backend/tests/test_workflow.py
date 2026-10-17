import pytest

from app.agents.graph import build_analysis_flow, build_verification_flow
from app.agents.test_agent import screen_test_code
from helpers import REPO_FILES, ScriptedLLM, make_test_deps

BASE = {"task_id": "t", "repository_url": "https://github.com/o/r", "task": "fix bugs"}


@pytest.mark.parametrize("use_langgraph", [True, False])
async def test_rule_based_end_to_end(use_langgraph):
    deps, events = make_test_deps()
    state = await build_analysis_flow(deps).run(dict(BASE), use_langgraph)
    assert state["patch_ok"] and state["patch"]["source"] == "rule"
    assert "except Exception:" in state["patch"]["unified_diff"]
    assert state["test"]["kind"] == "pattern"
    assert "report" not in state  # nothing is verified before approval

    final = await build_verification_flow(deps).run(state, use_langgraph)
    assert final["review"]["verdict"] == "verified"
    assert "pattern" in final["report"]["markdown"].lower()
    assert any(step == "run_tests" for step, *_ in events)


async def test_unavailable_sandbox_is_never_reported_as_verified():
    from app.tools.sandbox_runner import RunResult
    deps, _ = make_test_deps(sandbox=lambda r, t, l: RunResult(status="unavailable", label=l, note="no docker"))
    state = await build_analysis_flow(deps).run(dict(BASE), False)
    final = await build_verification_flow(deps).run(state, False)
    assert final["review"]["verdict"] == "not_run"
    assert "Not verified" in final["report"]["verdict_text"]


async def test_clean_repo_produces_no_patch_and_a_report():
    deps, _ = make_test_deps(files=[REPO_FILES[1]])
    state = await build_analysis_flow(deps).run(dict(BASE), False)
    assert not state.get("patch_ok") and state["report"]["verdict"] == "no_patch"


async def test_llm_patch_retries_after_validation_failure():
    files = [{"path": "app/calc.py", "content": "def div(a, b):\n    return a / b\n"}]
    bug = {"id": "x"}  # placeholder; real id comes from analysis below
    deps, _ = make_test_deps(files=files)
    # No static finding exists for division, so craft one through a mutable default instead.
    files[0]["content"] = "def add(x, acc=[]):\n    acc.append(x)\n    return acc\n"
    llm = ScriptedLLM([
        {"annotations": []},                                    # bug agent
        {"steps": []},                                          # planner (falls back to heuristic)
        {"old_snippet": "not in file", "new_snippet": "x", "explanation": "bad"},   # attempt 1: invalid
        {"old_snippet": "def add(x, acc=[]):\n    acc.append(x)\n",
         "new_snippet": "def add(x, acc=None):\n    acc = [] if acc is None else acc\n    acc.append(x)\n",
         "explanation": "Use None default"},                    # attempt 2: valid
        {"test_code": "from calc import add\n\ndef test_no_shared_state():\n    add(1)\n    assert add(2) == [2]\n"},
    ])
    deps, events = make_test_deps(files=files, llm=llm)
    state = await build_analysis_flow(deps).run(dict(BASE), False)
    assert state["patch_ok"] and state["retries"] == 1 and state["patch"]["source"] == "llm"
    assert state["test"]["source"] == "llm"
    assert ("validate_patch", "failed", "deterministic") in events


async def test_retries_are_bounded():
    files = [{"path": "a.py", "content": "def f(x=[]):\n    return x\n"}]
    llm = ScriptedLLM([{"annotations": []}, {"steps": []}] + [{"old_snippet": "nope", "new_snippet": "y", "explanation": ""}] * 10)
    deps, _ = make_test_deps(files=files, llm=llm)
    state = await build_analysis_flow(deps).run(dict(BASE), False)
    assert not state["patch_ok"] and state["retries"] == deps.settings.max_retries + 1


def test_generated_test_screening():
    assert screen_test_code("def test_a():\n    assert 1\n") is None
    assert "forbidden import" in screen_test_code("import os\ndef test_a():\n    os.system('x')\n")
    assert "forbidden call" in screen_test_code("def test_a():\n    exec('1')\n")
    assert screen_test_code("x = 1") == "no test_ functions found"
