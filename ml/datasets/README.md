# Datasets

`severity_sample.csv` and `duplicates_sample.csv` are **tiny synthetic smoke-test files**. They exist so the
scripts run end to end. **Do not quote metrics from them.** The labels were written from the semantics of
Bandit/Ruff rules, not from real maintainers' judgement.

For a credible result, build a real dataset and keep the same columns:

| file | columns |
| --- | --- |
| `severity.csv` | `text` (issue title + description), `severity` (low/medium/high), `repo` (used to split by repository) |
| `duplicates.csv` | `id`, `text`, `group` (issues sharing a group are duplicates; blank = unique) |

Sources: public GitHub issues/commits, curated bug-fix sets (e.g. BugsInPy). Check each licence and
labelling method, and split by repository or time to avoid leakage.
