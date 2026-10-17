"""Duplicate-issue retrieval: TF-IDF baseline vs sentence embeddings (optional).

    python evaluate.py --data datasets/duplicates_sample.csv [--embeddings all-MiniLM-L6-v2]

For every issue that has duplicates, rank all other issues by cosine similarity and report
MRR, recall@k and precision@k against the labelled groups.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

HERE = Path(__file__).parent


def score(sim: np.ndarray, groups: list[str], ks=(1, 3)) -> dict:
    n, rr, rec, prec = len(groups), [], {k: [] for k in ks}, {k: [] for k in ks}
    for i in range(n):
        if not groups[i]:
            continue
        relevant = {j for j in range(n) if j != i and groups[j] == groups[i]}
        order = [j for j in np.argsort(-sim[i]) if j != i]
        hits = [rank for rank, j in enumerate(order, 1) if j in relevant]
        rr.append(1 / hits[0])
        for k in ks:
            top = set(order[:k])
            rec[k].append(len(top & relevant) / len(relevant))
            prec[k].append(len(top & relevant) / k)
    out = {"queries": len(rr), "mrr": round(float(np.mean(rr)), 4)}
    for k in ks:
        out[f"recall@{k}"], out[f"precision@{k}"] = round(float(np.mean(rec[k])), 4), round(float(np.mean(prec[k])), 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "datasets/duplicates_sample.csv"))
    ap.add_argument("--embeddings", default="", help="sentence-transformers model name")
    args = ap.parse_args()
    df = pd.read_csv(args.data).fillna({"group": ""})
    texts, groups = df["text"].tolist(), df["group"].astype(str).replace("nan", "").tolist()

    results = {"rows": len(df)}
    tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english").fit_transform(texts)
    results["tfidf_baseline"] = score(cosine_similarity(tfidf), groups)
    if args.embeddings:
        try:
            from sentence_transformers import SentenceTransformer
            emb = SentenceTransformer(args.embeddings).encode(texts, normalize_embeddings=True)
            results[f"embeddings:{args.embeddings}"] = score(emb @ emb.T, groups)
        except ImportError:
            print("sentence-transformers is not installed; skipping embeddings.")
    for name, m in results.items():
        if isinstance(m, dict):
            print(f"{name:40s} {m}")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/duplicates_metrics.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
