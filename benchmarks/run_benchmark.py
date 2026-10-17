"""Measure the static analyzer against fixtures with known bugs.

    python benchmarks/run_benchmark.py            # from the repo root, with the backend venv active

Reports recall on known bugs and false positives (any non-info finding) on clean files.
Add fixtures and entries in expected.json to grow the benchmark; report its size alongside the numbers.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
from app.tools.static_analyzer import analyze_files  # noqa: E402


def main() -> int:
    expected = json.loads((ROOT / "expected.json").read_text())
    files = [{"path": p.name, "content": p.read_text()} for p in sorted((ROOT / "fixtures").glob("*.py"))]
    start = time.perf_counter()
    findings, status = analyze_files(files)
    elapsed = time.perf_counter() - start

    hits, misses = [], []
    for bug in expected["known_bugs"]:
        ok = any(f["path"] == bug["path"] and f["rule_id"] == bug["rule_id"] and abs(f["line"] - bug["line"]) <= 1
                 for f in findings)
        (hits if ok else misses).append(bug)
    false_pos = [f for f in findings if f["path"] in expected["clean_files"] and f["severity"] != "info"]

    result = {
        "fixtures": len(files), "known_bugs": len(expected["known_bugs"]), "detected": len(hits),
        "recall": round(len(hits) / len(expected["known_bugs"]), 3), "missed": misses,
        "clean_files": len(expected["clean_files"]), "false_positives_on_clean_files": len(false_pos),
        "tool_status": status, "seconds": round(elapsed, 2),
    }
    print(json.dumps(result, indent=2))
    (ROOT / "results.json").write_text(json.dumps(result, indent=2))
    return 0 if not misses and not false_pos else 1


if __name__ == "__main__":
    sys.exit(main())
