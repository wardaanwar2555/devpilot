"""Train a severity classifier and compare it with a baseline.

    python train_severity.py --data datasets/severity_sample.csv

Splits by repository when a `repo` column exists (reduces leakage). Reports macro-F1 for a
majority-class baseline and TF-IDF + logistic regression, writes metrics to results/ and saves the
model to models/severity.joblib. The backend's ranker uses that file automatically if it exists.
"""
import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import make_pipeline

HERE = Path(__file__).parent


def split(df, seed):
    if "repo" in df and df["repo"].nunique() > 2:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=seed)
        tr, te = next(gss.split(df, groups=df["repo"]))
        return df.iloc[tr], df.iloc[te], "group split by repo"
    tr, te = train_test_split(df, test_size=0.3, stratify=df["severity"], random_state=seed)
    return tr, te, "stratified random split"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "datasets/severity_sample.csv"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(args.data).dropna(subset=["text", "severity"])
    train, test, how = split(df, args.seed)
    labels = sorted(df["severity"].unique())

    models = {
        "majority_baseline": DummyClassifier(strategy="most_frequent"),
        "tfidf_logreg": make_pipeline(TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1),
                                      LogisticRegression(max_iter=1000, class_weight="balanced")),
    }
    results = {"data": args.data, "rows": len(df), "train": len(train), "test": len(test), "split": how, "models": {}}
    for name, model in models.items():
        model.fit(train["text"], train["severity"])
        pred = model.predict(test["text"])
        results["models"][name] = {
            "macro_f1": round(f1_score(test["severity"], pred, average="macro", zero_division=0), 4),
            "report": classification_report(test["severity"], pred, output_dict=True, zero_division=0),
            "labels": labels,
            "confusion_matrix": confusion_matrix(test["severity"], pred, labels=labels).tolist(),
        }
        print(f"{name:20s} macro-F1 = {results['models'][name]['macro_f1']:.3f}")
    gain = results["models"]["tfidf_logreg"]["macro_f1"] - results["models"]["majority_baseline"]["macro_f1"]
    results["beats_baseline"] = gain > 0
    print(f"split: {how}; train={len(train)} test={len(test)}; gain over baseline: {gain:+.3f}")
    if len(df) < 500:
        print("WARNING: fewer than 500 rows. Treat these numbers as a smoke test, not evidence.")

    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/severity_metrics.json").write_text(json.dumps(results, indent=2))
    if not args.no_save:
        final = models["tfidf_logreg"].fit(df["text"], df["severity"])  # refit on all data for deployment
        (HERE / "models").mkdir(exist_ok=True)
        joblib.dump(final, HERE / "models/severity.joblib")
        print("saved models/severity.joblib")


if __name__ == "__main__":
    main()
