# Portfolio Analytics Agent

A command-line AI agent that answers natural language questions about investment portfolio data, powered by Google Gemini and SQLite.

---

## Architecture

```
User Question
      │
      ▼
  agent.py  ── keyword router ── "Which tool?"
      │
      ├── sql_tool.py       question → Gemini → SQL → SQLite → answer
      │
      └── exposure_tool.py  portfolio name → equity holdings → sector % (no LLM)
```

**Routing** is done via keyword matching — zero API calls needed.
Only the SQL tool calls Gemini (once per unique question).
All answers are cached persistently so repeated questions never hit the API.

---

## Project Structure

```
portfolio_agent/
├── agent.py                  # Main agent — CLI entry point, routing, cache
├── evaluator.py              # Evaluation script against ground truth dataset
├── setup_db.py               # Loads all CSV data into SQLite database
├── database_schema.sql       # Table definitions and indices
├── ground_truth_dataset.json # 10 evaluation Q&A pairs
├── evaluation_results.json   # Latest evaluation output (10/10 pass)
├── .query_cache.json         # Persistent answer cache (auto-generated)
├── tools/
│   ├── sql_tool.py           # Text-to-SQL via Gemini + query runner
│   └── exposure_tool.py      # Sector exposure calculator (pure Python)
└── data/                     # Source CSV files (9 total)
    ├── portfolios.csv
    ├── holdings.csv
    ├── securities.csv
    ├── sectors.csv
    └── ...
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get a Gemini API key

Generated a new api key through --> https://aistudio.google.com, sign in with a Google account and create a free API key.


### 3. Create a .env file in the project root

```
GEMINI_API_KEY=your_key_here
```

### 4. Set up the database

```bash
python setup_db.py
```

Loads all 9 CSV files into `portfolio.db` following the provided schema.

---

## Running the Agent

```bash
python agent.py
```

Example session:

```
Portfolio Analytics Agent
========================================
Type your question (or 'quit' to exit)

You: How many portfolios do we have in total?

  [agent] Tool selected: sql_tool
  [sql_tool] Generated SQL: SELECT COUNT(*) FROM portfolios;

13

----------------------------------------
You: What are the sector exposures for the Tech Innovation Fund?

  [agent] Tool selected: exposure_calculator
  [agent] Portfolio identified: Tech Innovation Fund

Sector exposures for 'Tech Innovation Fund' (equities only):

  Technology                100.00%  ##################################################

  TOTAL                     100.00%

----------------------------------------
You: quit
```

---

## Running the Evaluator

```bash
python evaluator.py
```

Runs all 10 ground truth questions through the agent and scores pass/fail.
Results are saved to `evaluation_results.json`.

```
RESULTS  : 10/10 passed  (100% accuracy)
API calls: 8 this run  (2 served from cache)
  Easy    : 3/3
  Medium  : 5/5
  Hard    : 2/2
```

On subsequent runs, all questions are served from cache — zero API calls:

```bash
# Force fresh API calls (e.g. to retest with a new key)
python evaluator.py --no-cache
```

---

## Tool Design

### SQL Tool (`tools/sql_tool.py`)
- Sends the user question + full DB schema to Gemini with a strict prompt
- Gemini returns a raw SQL SELECT query (only SELECT/WITH allowed — injection safe)
- Query executes against SQLite, results formatted as aligned text table
- Auto-retries on rate limit errors using the suggested wait time from the API

### Exposure Calculator (`tools/exposure_tool.py`)
- Zero LLM calls — pure Python + SQL
- Joins `holdings → securities → sectors`, filtering `asset_type = 'Stock'` (bonds excluded per spec)
- Sums `current_weight` per sector, re-normalises to 100% across equities only
- Returns a sorted sector → percentage breakdown

### Agent Routing (`agent.py`)
- Keyword matching decides the tool: questions containing "sector exposure", "sector breakdown" etc. go to the exposure calculator, everything else to the SQL tool
- Two-pass fuzzy portfolio name extractor: exact match first, then word-overlap scoring (handles "international equity" → "International Equity Fund")
- Persistent cache in `.query_cache.json` — answers survive across sessions

---

## Evaluation Strategy

For **text2sql** questions:
- Ground truth SQL runs directly on the DB to get expected rows
- Agent answer checked for presence of expected values (70% match threshold for multi-row)

For **exposure_calculator** questions:
- Exposure tool runs directly to get correct sector breakdown
- Checks that top sectors appear in the agent's answer
- Single-sector portfolios require only 1 match (handles Tech Innovation Fund = 100% Technology)

---

## Engineering Decisions

| Decision |                                           Reason |
------|----------------------------------------------------|
| Keyword routing instead of LLM routing | Saves 1 API call per question, more reliable, zero latency |
| Persistent JSON cache                  | Free tier quota is limited; repeated questions cost nothing |
| SELECT-only guard in run_query()       | Prevents any destructive SQL from executing |
| Re-normalise exposure weights          | `current_weight` includes bonds; equity-only % must sum to 100% |
| Retry with suggested wait time         | Rate limit errors include a `retryDelay` — we use it precisely |
| gemini-2.0-flash model                 | 1500 req/day free tier vs 20/day for gemini-2.5-flash |

## Optional Enhancements Implemented

- Persistent caching for repeated queries
- SQL injection prevention (SELECT-only whitelist)
- Query validation before execution
- Graceful error handling with retry logic
- Verbose logging mode (`[agent]`, `[sql_tool]` prefixes)
- Fuzzy portfolio name matching
- `--no-cache` flag for forced re-evaluation