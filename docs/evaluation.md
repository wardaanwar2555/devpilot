# Evaluation

Report measured numbers only, with the size of the benchmark next to them.

## What exists
| Check | Command | Current result (this repository's fixtures) |
| --- | --- | --- |
| Unit and integration tests | `cd backend && python -m pytest` | 52 passing |
| Analyzer benchmark | `python benchmarks/run_benchmark.py` | 7/7 known bugs detected, 0 false positives on 2 clean files |
| ML severity | `python ml/train_severity.py` | Runs on synthetic data: smoke test only |
| ML duplicates | `python ml/evaluate.py` | Runs on synthetic data: smoke test only |

The benchmark is **9 hand-written files**. It guards against regressions; it is not an estimate of accuracy on real code.

## What you should still measure (portfolio checklist)
1. Build 20–50 real bug-fix cases (e.g. from BugsInPy or your own repos) with the failing test that exposes each bug.
2. For each, record: bug detected? false positives per 1k lines? patch applies? test fails before / passes after? previously passing tests still pass?
3. Record time per task and LLM tokens/cost per task.
4. For ML: use real labelled issues (≥ 500 rows), split by repository or time, compare against the majority baseline, and report macro-F1 with a confusion matrix. If the model does not beat the baseline, say so.
5. Compare LLM-written tests vs template tests: how often does the LLM test fail-before/pass-after?

## Known gaps
- Real LLM behaviour (patch/test quality, JSON compliance) has not been measured here.
- The Docker sandbox command is unit-tested for flags and status mapping; run it on your machine with `docker build` first and try a repo with a bare `except:`.
