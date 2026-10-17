# Architecture

## Layers
1. **React dashboard** (`frontend/`): submit a repo, watch agent steps, review findings/diff/test, approve, read the report. All HTTP calls go through `services/api.js`; Vite proxies `/api` to FastAPI in development.
2. **FastAPI backend** (`backend/app/api`): validation (Pydantic), optional bearer auth, rate limiting, background tasks, task persistence.
3. **Agent workflow** (`backend/app/agents/graph.py`): a single graph definition executed by LangGraph (or a built-in runner if LangGraph is missing or `USE_LANGGRAPH=false`). Two phases split by the approval gate.
4. **Tools** (`backend/app/tools`): GitHub client, static analyzer, patch validator, LLM client, sandbox runner, secret redaction. Agents reach the outside world only through these.
5. **Storage** (`services/store.py`): one `tasks` table (state and events as JSON). SQLite by default, PostgreSQL via `DATABASE_URL`.

## Why two phases
Phase 1 is read-only and produces a proposal. Phase 2 executes code, so it only starts from `POST /approve`. The approval, its timestamp and the note are stored in the report.

## Design decisions
- **LLM annotates, tools find.** Findings come from deterministic tools, so a clean file is not given fabricated bugs.
- **Backend builds the diff.** The model returns an exact snippet and its replacement; we apply it only if it matches exactly once, generate the diff ourselves and re-parse the result.
- **Evidence ladder.** Reports use `verified / weak / failed / inconclusive / not_run / no_patch`. `verified` requires fail-before **and** pass-after.
- **Provenance everywhere.** Events and findings carry a source (static, rule, model, sandbox) that the UI shows as a tag.
- **Dependency injection.** `Deps` bundles the LLM, GitHub fetcher, sandbox and event emitter, which keeps the workflow testable without network or Docker.

## State
`DevPilotState` (TypedDict): repository, task, files, findings, plan, proposal, patch, patched_files, test, test_results, review, approval, report, plus retry counters.

## Extending
- New static rule: add a visitor method in `tools/static_analyzer.py` and a fixture in `benchmarks/`.
- New automatic fix: add a function to `RULE_FIXERS` in `agents/repair_agent.py` and a counter in `agents/test_agent.py`.
- Other languages: add an eligibility rule, an analyzer and a sandbox image per language.
- Pull requests: add a tool that pushes a branch only after `approval.approved` is true, using a token with minimal scopes.
