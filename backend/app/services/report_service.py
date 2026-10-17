"""Builds the final report. Language is deliberately strict about what was and was not verified."""
from __future__ import annotations

from datetime import datetime, timezone

VERDICT_TEXT = {
    "verified": "Verified within the scope below: the test failed on the original code and passed on the patched code.",
    "weak": "Weak evidence: the test also passed on the original code, so it does not show that the issue was fixed.",
    "failed": "Not verified: the test failed on the patched code.",
    "inconclusive": "Inconclusive: the test run errored or timed out, so it proves nothing either way.",
    "not_run": "Not verified: tests were not run (sandbox unavailable or approval not granted).",
    "no_patch": "No patch was proposed, so there is nothing to verify.",
}


def compute_verdict(baseline: dict | None, patched: dict | None) -> str:
    if not baseline or not patched:
        return "not_run"
    if "unavailable" in (baseline["status"], patched["status"]):
        return "not_run"
    if patched["status"] == "failed":
        return "failed"
    if patched["status"] != "passed" or baseline["status"] in ("error", "timeout"):
        return "inconclusive"
    return "verified" if baseline["status"] == "failed" else "weak"


def _fmt_run(r: dict | None) -> str:
    if not r:
        return "not run"
    extra = f" ({r['note']})" if r.get("note") else ""
    return f"{r['status']}, exit {r.get('exit_code')}, {r.get('duration_s', 0)}s{extra}"


def build_report(state: dict) -> dict:
    meta, patch, test = state.get("repo_meta", {}), state.get("patch"), state.get("test")
    results, review = state.get("test_results") or {}, state.get("review") or {}
    findings = state.get("findings", [])
    verdict = review.get("verdict") or ("no_patch" if not patch else "not_run")
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    md = [f"# DevPilot report: {meta.get('repository', 'unknown')}",
          f"*Commit `{meta.get('commit', '')[:10]}` on `{meta.get('branch', '')}` · generated "
          f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC*", "",
          f"**Task:** {state.get('task', '')}", "", "## Verification status", f"**{verdict.replace('_', ' ')}**: {VERDICT_TEXT[verdict]}"]
    if test:
        md += ["", f"Test scope: {test['strength']}"]
    md += ["", "## Findings",
           f"{len(findings)} candidate issues from static analysis ({', '.join(f'{v} {k}' for k, v in counts.items()) or 'none'}). "
           "Only syntax errors are confirmed; everything else is a potential defect that needs human judgement.", ""]
    for f in findings[:10]:
        flag = f" [model: {f['llm_verdict'].replace('_', ' ')}]" if f.get("llm_verdict") else ""
        md.append(f"- **{f['severity']}** `{f['path']}:{f['line']}` {f['title']} ({f['source']} {f['rule_id']}){flag}")
    if patch:
        md += ["", "## Proposed change", f"Source: {'deterministic rule' if patch['source'] == 'rule' else 'language model (unverified suggestion)'}",
               patch["explanation"], "", "```diff", patch["unified_diff"].rstrip(), "```"]
    if results:
        md += ["", "## Test runs", f"- Original code: {_fmt_run(results.get('baseline'))}",
               f"- Patched code: {_fmt_run(results.get('patched'))}"]
    if review.get("notes"):
        md += ["", "## Reviewer notes (model-generated, not verified)", *[f"- {n}" for n in review["notes"]]]
    md += ["", "## Limitations",
           "- Only Python files within the size limits were analysed; the repository was never cloned or executed outside the sandbox.",
           "- The sandbox has no network, so tests that need third-party packages cannot run.",
           "- Nothing was pushed to GitHub. A human must review the diff and approve any pull request."]
    if state.get("tool_status"):
        md.append("- Tool status: " + ", ".join(f"{k}={v}" for k, v in state["tool_status"].items()) + ".")
    if state.get("secrets_flagged"):
        md.append(f"- {state['secrets_flagged']} possible secret(s) were found and redacted before any model call.")
    approval = state.get("approval")
    pr_title = f"Fix: {patch['finding_title']}" if patch else "No change proposed"
    return {
        "verdict": verdict, "verdict_text": VERDICT_TEXT[verdict], "pr_title": pr_title,
        "approval": approval, "finding_counts": counts, "markdown": "\n".join(md) + "\n",
    }
