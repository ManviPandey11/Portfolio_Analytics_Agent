import os
import sys
import json
from google import genai
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from tools.sql_tool import answer_with_sql
from tools.exposure_tool import get_sector_exposures, format_exposures

# Persistent cache — survives across runs, saves API quota.
# Stored as .query_cache.json next to this script.
CACHE_PATH = os.path.join(os.path.dirname(__file__), ".query_cache.json")

def _load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_cache(cache: dict):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

# Module-level cache loaded once at import time
CACHE = _load_cache()

def invalidate_cache_entry(question: str):
    """Remove a single bad entry from the cache (e.g. a previously wrong answer)."""
    if question in CACHE:
        del CACHE[question]
        _save_cache(CACHE)

# Portfolio list — used for name extraction without any LLM call
PORTFOLIOS = [
    "Growth Equity Fund",
    "Conservative Income Fund",
    "Tech Innovation Fund",
    "Balanced Portfolio",
    "ESG Sustainable Fund",
    "Small Cap Value Fund",
    "International Equity Fund",
    "Fixed Income Plus",
    "Dividend Aristocrats Fund",
    "Emerging Markets Fund",
    "Total Stock Market Index Fund",
    "Total Bond Market Index Fund",
    "Total International Index Fund",
]

# Routing — pure keyword match, zero LLM/API calls
EXPOSURE_KEYWORDS = [
    "sector exposure",
    "sector breakdown",
    "sector allocation",
    "exposure by sector",
    "sector distribution",
    "exposure breakdown",
    "exposure for",
]

def route_question(question: str) -> str:
    q = question.lower()
    if any(kw in q for kw in EXPOSURE_KEYWORDS):
        return "exposure_calculator"
    return "sql_tool"

def extract_portfolio_name(question: str) -> str | None:
    """
    Two-pass fuzzy match — no LLM needed.
    Pass 1: exact substring match (fastest).
    Pass 2: word-overlap score ≥ 0.5, ignoring stop words.
    """
    q = question.lower()

# Pass 1 — exact
    for portfolio in PORTFOLIOS:
        if portfolio.lower() in q:
            return portfolio

# Pass 2 — fuzzy word overlap
    STOP = {"fund", "the", "a", "an", "of", "for"}
    best_match, best_score = None, 0.0
    for portfolio in PORTFOLIOS:
        words = [w for w in portfolio.lower().split() if w not in STOP]
        if not words:
            continue
        score = sum(1 for w in words if w in q) / len(words)
        if score > best_score and score >= 0.5:
            best_score = score
            best_match = portfolio

    return best_match

# Main agent entry point
def run_agent(question: str, client, verbose: bool = False) -> str:
    """
    Route the question to the right tool, return a formatted answer.
    Checks the persistent cache first — no API call if already answered.
    """
# Cache lookup (exposure_calculator answers are also cached)
    if question in CACHE:
        if verbose:
            print("  [agent] Cache hit — no API call needed")
        return CACHE[question]

    tool = route_question(question)
    if verbose:
        print(f"  [agent] Tool selected: {tool}")

    if tool == "exposure_calculator":
        portfolio_name = extract_portfolio_name(question)
        if not portfolio_name:
            return (
                "Could not identify a portfolio name in your question.\n"
                f"Available portfolios:\n  " + "\n  ".join(PORTFOLIOS)
            )
        if verbose:
            print(f"  [agent] Portfolio identified: {portfolio_name}")
        result = get_sector_exposures(portfolio_name)
        answer = format_exposures(result)

    else:
# SQL tool — the ONLY place an API call happens
        result = answer_with_sql(question, client, verbose=verbose)
        if result["error"]:
            sql_hint = f"\n\nGenerated SQL:\n{result['sql']}" if result["sql"] else ""
            return f"Error: {result['error']}{sql_hint}"
        answer = result["answer"]

# Persist successful answer
    CACHE[question] = answer
    _save_cache(CACHE)
    return answer

def main():
    load_dotenv()
# Fetches api key from .env file instead of hardcording for safety measures
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env file")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print("Portfolio Analytics Agent")
    print("=" * 40)
    print("Type your question (or 'quit' to exit)\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        print()
        answer = run_agent(question, client, verbose=True)
        print(f"\n{answer}\n")
        print("-" * 40)

if __name__ == "__main__":
    main()