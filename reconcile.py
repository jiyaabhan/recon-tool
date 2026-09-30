"""
Steps 2-3: reconcile source_b against source_a.

  Stage 1 (code only): exact code match, but only trusted if the names also agree.
  Stage 2 (code only): high-confidence fuzzy name match.
  Stage 3 (AI):        ambiguous rows go to an LLM with the top candidates.
  Then:                matched pairs are checked for field conflicts, which go to
                       a human review queue instead of being auto-resolved.

Usage:
  python reconcile.py            # uses the LLM (needs ANTHROPIC_API_KEY)
  python reconcile.py --no-llm   # baseline: code-only, no AI
"""
import json
import os
import sys

import pandas as pd

try:
    from rapidfuzz import fuzz
    def similarity(a, b):
        return fuzz.token_sort_ratio(a.lower(), b.lower())
except ImportError:  # fallback so the script still runs without rapidfuzz
    from difflib import SequenceMatcher
    def similarity(a, b):
        return 100 * SequenceMatcher(None, " ".join(sorted(a.lower().split())),
                                     " ".join(sorted(b.lower().split()))).ratio()

USE_LLM = "--no-llm" not in sys.argv
AUTO_MATCH = 90       # fuzzy score at or above this = confident match
NAME_CHECK = 85       # an exact code match with names below this is suspicious
COST_TOLERANCE = 0.05 # >5% cost difference = conflict
MODEL = "claude-sonnet-5-5"

a = pd.read_csv("data/source_a.csv")
b = pd.read_csv("data/source_b.csv")
a_by_code = {r.item_code: r for r in a.itertuples()}


def top_candidates(name, k=3):
    scored = [(similarity(name, r.description), r) for r in a.itertuples()]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:k]


def ask_llm(b_row, candidates):
    """Ask the model to pick a candidate or say none match. Returns (code, confidence, reason)."""
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    options = "\n".join(
        f"{i+1}. code={r.item_code} | name={r.description} | unit={r.uom}"
        for i, (_, r) in enumerate(candidates)
    )
    prompt = f"""You are reconciling item records between two systems for a furniture manufacturer.

Legacy record: code={b_row.code} | name={b_row.item_name} | unit={b_row.unit}

Candidate matches from the ERP:
{options}

Legacy codes and names are often abbreviated or use shortened prefixes, and codes are sometimes
typed wrong. Decide which candidate is the same physical item, or "none" if no candidate is.
Only match if you are genuinely confident. Respond with JSON only, no other text:
{{"match": "<item_code or none>", "confidence": "high|medium|low", "reason": "<one sentence>"}}"""
    msg = client.messages.create(model=MODEL, max_tokens=2000,
                                 messages=[{"role": "user", "content": prompt}])
    # the reply can include a thinking block before the answer, so keep only text blocks
    text = "".join(b.text for b in msg.content if b.type == "text")
    text = text[text.find("{"): text.rfind("}") + 1]  # pull out just the JSON object
    out = json.loads(text)
    code = None if out["match"].lower() == "none" else out["match"]
    return code, out["confidence"], out["reason"]


matches, log = [], []
for idx, row in enumerate(b.itertuples(), start=1):
    match, method, detail = None, None, ""

    # Stage 1: exact code, verified by name
    if row.code in a_by_code:
        score = similarity(row.item_name, a_by_code[row.code].description)
        best_score, best = top_candidates(row.item_name, k=1)[0]
        name_points_elsewhere = best.item_code != row.code and best_score > score
        if score >= NAME_CHECK and not name_points_elsewhere:
            match, method, detail = row.code, "exact_code", f"name score {score:.0f}"
        else:
            detail = (f"code exists but name fits {best.item_code} better "
                      f"({best_score:.0f} vs {score:.0f}), treated as ambiguous")

    # Stage 2: confident fuzzy name match
    if match is None:
        cands = top_candidates(row.item_name)
        best_score, best = cands[0]
        runner_up = cands[1][0]
        if best_score >= AUTO_MATCH and best_score - runner_up >= 5:
            match, method = best.item_code, "fuzzy_auto"
            detail = f"score {best_score:.0f} (runner-up {runner_up:.0f})"

        # Stage 3: ambiguous
        elif USE_LLM:
            llm_cands = top_candidates(row.item_name, k=5)
            # if the legacy code exists in A, always show that item to the model too
            if row.code in a_by_code and all(r.item_code != row.code for _, r in llm_cands):
                llm_cands.append((0, a_by_code[row.code]))
            code, conf, reason = ask_llm(row, llm_cands)
            if code and conf in ("high", "medium"):
                match, method = code, f"llm_{conf}"
            else:
                method = "needs_review"
            detail = f"LLM said {code or 'none'} ({conf}): {reason}"
        else:
            # baseline without AI: take the best guess if it's decent, else unmatched
            if best_score >= 70:
                match, method = best.item_code, "fuzzy_guess"
            else:
                method = "needs_review"
            detail = f"best score {best_score:.0f}"

    matches.append({"b_row": idx, "b_code": row.code, "b_name": row.item_name,
                    "matched_item_code": match, "method": method})
    log.append({"b_row": idx, "method": method, "detail": detail})

m = pd.DataFrame(matches)

# ---------- Conflict checks on matched pairs ----------
review = []
for rec in m.itertuples():
    if rec.matched_item_code is None or pd.isna(rec.matched_item_code):
        review.append({"b_row": rec.b_row, "issue": "unmatched",
                       "detail": f"{rec.b_code} / {rec.b_name}: no confident match, may not exist"})
        continue
    a_row = a_by_code[rec.matched_item_code]
    b_row = b.iloc[rec.b_row - 1]
    if abs(b_row.std_cost - a_row.cost) / a_row.cost > COST_TOLERANCE:
        review.append({"b_row": rec.b_row, "issue": "cost_conflict",
                       "detail": f"{rec.matched_item_code}: A={a_row.cost} vs B={b_row.std_cost}"})
    if b_row.bottleneck_wc != a_row.work_center:
        review.append({"b_row": rec.b_row, "issue": "work_center_conflict",
                       "detail": f"{rec.matched_item_code}: A={a_row.work_center} vs B={b_row.bottleneck_wc}"})

# duplicates: two B rows matched to the same A item
dupes = m[m.matched_item_code.notna() & m.duplicated("matched_item_code", keep=False)]
for rec in dupes.itertuples():
    review.append({"b_row": rec.b_row, "issue": "duplicate",
                   "detail": f"{rec.matched_item_code} matched by more than one B row"})

# items in A that nothing in B matched
for code in sorted(set(a.item_code) - set(m.matched_item_code.dropna())):
    review.append({"b_row": "", "issue": "missing_from_b", "detail": f"{code} has no row in B"})

os.makedirs("output", exist_ok=True)
suffix = "" if USE_LLM else "_baseline"
m.to_csv(f"output/matches{suffix}.csv", index=False)
pd.DataFrame(review).to_csv(f"output/review_queue{suffix}.csv", index=False)
pd.DataFrame(log).to_csv(f"output/decision_log{suffix}.csv", index=False)

print(m.method.value_counts().to_string())
print(f"\n{len(review)} items sent to human review -> output/review_queue{suffix}.csv")
