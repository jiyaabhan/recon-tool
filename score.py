"""
Step 4: score the output against the answer key.

Usage:
  python score.py            # scores the AI run
  python score.py --baseline # scores the no-AI run
"""
import sys
import pandas as pd

suffix = "_baseline" if "--baseline" in sys.argv else ""
key = pd.read_csv("data/answer_key.csv")
m = pd.read_csv(f"output/matches{suffix}.csv")
review = pd.read_csv(f"output/review_queue{suffix}.csv")

df = key.merge(m, on="b_row")
df["true_item_code"] = df.true_item_code.fillna("")
df["matched_item_code"] = df.matched_item_code.fillna("")
df["correct"] = df.true_item_code == df.matched_item_code

print(f"=== Match accuracy{' (baseline, no AI)' if suffix else ' (with AI)'} ===")
print(f"Overall: {df.correct.sum()} / {len(df)} rows correct ({df.correct.mean():.0%})\n")

print("By method:")
print(df.groupby("method").correct.agg(rows="count", correct="sum").to_string(), "\n")

print("By planted issue:")
print(df.groupby("planted_issue").correct.agg(rows="count", correct="sum").to_string(), "\n")

wrong = df[~df.correct]
if len(wrong):
    print("Mistakes (write these up honestly in the README):")
    print(wrong[["b_row", "b_code", "b_name", "true_item_code",
                 "matched_item_code", "method"]].to_string(index=False), "\n")

print("Review queue by issue type:")
print(review.issue.value_counts().to_string())
