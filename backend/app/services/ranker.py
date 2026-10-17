"""Finding prioritisation: transparent heuristic score, optionally nudged by a trained ML model."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..tools.static_analyzer import SEVERITY_RANK

MODEL_PATH = Path(__file__).resolve().parents[3] / "ml" / "models" / "severity.joblib"
_CATEGORY_WEIGHT = {"syntax": 1.5, "security": 1.0, "correctness": 0.8, "bug-risk": 0.6, "reliability": 0.5,
                    "maintenance": 0.0}


@lru_cache(maxsize=1)
def _load_model():
    try:
        import joblib
        return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
    except Exception:
        return None


def rank_findings(findings: list[dict]) -> list[dict]:
    model = _load_model()
    if model is not None and findings:
        texts = [f"{f['title']} {f['details']} {f['rule_id']}" for f in findings]
        try:
            for f, label in zip(findings, model.predict(texts)):
                f["ml_severity"] = str(label)
        except Exception:
            pass
    for f in findings:
        score = SEVERITY_RANK[f["severity"]] + _CATEGORY_WEIGHT.get(f["category"], 0.3)
        score += 2.0 if f["confirmed"] else 0.0
        if f.get("ml_severity") in ("high", "critical"):
            score += 0.4
        if f.get("llm_verdict") == "possible_false_positive":
            score -= 1.5
        elif f.get("llm_verdict") == "style_only":
            score -= 1.0
        f["priority_score"] = round(score, 2)
    return sorted(findings, key=lambda f: (-f["priority_score"], f["path"], f["line"]))
