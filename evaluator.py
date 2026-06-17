import os
import sys
import json
import time
import sqlite3
import argparse
from datetime import datetime
from google import genai
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from agent import run_agent, CACHE, _load_cache
from tools.exposure_tool import get_sector_exposures

GROUND_TRUTH_PATH = os.path.join(os.path.dirname(__file__), "ground_truth_dataset.json")
DB_PATH           = os.path.join(os.path.dirname(__file__), "portfolio.db")
CACHE_PATH        = os.path.join(os.path.dirname(__file__), ".query_cache.json")
RESULTS_PATH      = os.path.join(os.path.dirname(__file__), "evaluation_results.json")
RATE_LIMIT_DELAY  = 5

# Scoring helpers
def run_ground_truth_sql(sql: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def normalise(value) -> str:
    if value is None:
        return "none"
    return str(value).strip().lower()


def compare_sql_results(agent_answer: str, expected_rows: list) -> bool:
    if not expected_rows:
        return True
    agent_lower = agent_answer.lower()
    if len(expected_rows) == 1 and len(expected_rows[0]) == 1:
        return normalise(list(expected_rows[0].values())[0]) in agent_lower
    hits = sum(
        1 for row in expected_rows
        if any(v is not None and normalise(v) in agent_lower for v in row.values())
    )
    return hits >= max(1, int(len(expected_rows) * 0.7))


def compare_exposure_results(agent_answer: str, portfolio_name: str) -> bool:
    result = get_sector_exposures(portfolio_name)
    if result["error"]:
        return False
    top_sectors = list(result["exposures"].keys())[:3]
    agent_lower = agent_answer.lower()
    matches = sum(1 for s in top_sectors if s.lower() in agent_lower)
    required = 1 if len(top_sectors) == 1 else 2
    return matches >= required

# Main evaluator
def evaluate(client, bust_cache: bool = False):
    if bust_cache and os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)
        CACHE.clear()
        print("Cache cleared — all questions will make fresh API calls.\n")

    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        questions = json.load(f)["questions"]

    total          = len(questions)
    passed         = 0
    api_calls_made = 0
    results        = []

    print("Portfolio Agent Evaluator")
    print("=" * 60)

    for q in questions:
        qid        = q["id"]
        question   = q["question"]
        qtype      = q["type"]
        difficulty = q["difficulty"]

        print(f"\n[Q{qid}] ({difficulty.upper()}) {question}")
        print(f"  Type: {qtype}")

        is_cached = question in CACHE

        try:
            agent_answer = run_agent(question, client, verbose=False)
        except Exception as e:
            agent_answer = f"AGENT ERROR: {e}"

        if not is_cached and qtype == "text2sql":
            api_calls_made += 1
            print(f"  [evaluator] API call #{api_calls_made}. Pausing {RATE_LIMIT_DELAY}s...")
            time.sleep(RATE_LIMIT_DELAY)
# Score
        if qtype == "text2sql":
            expected_rows = run_ground_truth_sql(q["ground_truth"]["sql_query"])
            ok = compare_sql_results(agent_answer, expected_rows)
        elif qtype == "exposure_calculator":
            portfolio_name = q["ground_truth"]["parameters"]["portfolio_name"]
            ok = compare_exposure_results(agent_answer, portfolio_name)
        else:
            ok = False

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1

        print(f"  Status : {'✅ PASS' if ok else '❌ FAIL'}")
        print(f"  Answer : {agent_answer[:150].strip()}...")

        results.append({
            "id":           qid,
            "question":     question,
            "type":         qtype,
            "difficulty":   difficulty,
            "status":       status,
            "agent_answer": agent_answer,
            "cached":       is_cached,
        })

# Console summary
    print("\n" + "=" * 60)
    print(f"RESULTS  : {passed}/{total} passed  ({round(passed / total * 100)}% accuracy)")
    print(f"API calls: {api_calls_made} this run  ({total - api_calls_made} served from cache)")
    print("=" * 60)
    for level in ["easy", "medium", "hard"]:
        lvl      = [r for r in results if r["difficulty"] == level]
        lvl_pass = sum(1 for r in lvl if r["status"] == "PASS")
        if lvl:
            print(f"  {level.capitalize():<8}: {lvl_pass}/{len(lvl)}")

# Save evaluation_results.json
    output = {
        "metadata": {
            "evaluated_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_questions": total,
            "passed":          passed,
            "failed":          total - passed,
            "accuracy_pct":    round(passed / total * 100, 1),
            "model_used":      "gemini-2.0-flash",
            "note": (
                "Answers cached in .query_cache.json. "
                "To re-run with live API calls: python evaluator.py --no-cache"
            ),
        },
        "results": [
            {
                "id":           r["id"],
                "question":     r["question"],
                "type":         r["type"],
                "difficulty":   r["difficulty"],
                "status":       r["status"],
                "agent_answer": r["agent_answer"],
                "cached":       r["cached"],
            }
            for r in results
        ],
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: evaluation_results.json")
    return results

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Evaluate the Portfolio Agent")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Clear cache and force fresh API calls for all questions"
    )
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env file")
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    evaluate(client, bust_cache=args.no_cache)

if __name__ == "__main__":
    main()