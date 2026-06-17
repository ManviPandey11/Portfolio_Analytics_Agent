import sqlite3
import os
import re
import time
from google import genai

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "portfolio.db")

MODEL = "gemini-2.0-flash"

SCHEMA_SUMMARY = """
Tables and columns:
- sectors(sector_id, sector_name, sector_description, industry_group)
- securities(security_id, symbol, company_name, asset_type [Stock|Bond], sector_id, market_cap, current_price, currency, exchange, country, listing_date, maturity_date, coupon_rate)
- benchmarks(benchmark_id, benchmark_name, benchmark_symbol, benchmark_type, description, inception_date)
- portfolios(portfolio_id, portfolio_name, creation_date, target_risk_level, total_aum, strategy_type, benchmark_index, status)
- holdings(holding_id, portfolio_id, security_id, quantity, purchase_price, purchase_date, current_weight, cost_basis)
- transactions(transaction_id, portfolio_id, security_id, transaction_type [BUY|SELL], quantity, price, transaction_date, fees, settlement_date, notes)
- historical_prices(price_id, security_id, price_date, open_price, high_price, low_price, close_price, volume, adjusted_close)
- portfolio_performance(performance_id, portfolio_id, performance_date, nav, total_return_1m, total_return_3m, total_return_6m, total_return_1y, volatility, sharpe_ratio, max_drawdown)
- risk_metrics(risk_id, portfolio_id, calculation_date, var_95, var_99, cvar_95, beta, correlation_sp500, tracking_error, information_ratio, sortino_ratio)

Foreign keys:
- securities.sector_id → sectors.sector_id
- holdings.portfolio_id → portfolios.portfolio_id
- holdings.security_id → securities.security_id
- transactions.portfolio_id → portfolios.portfolio_id
- transactions.security_id → securities.security_id
- historical_prices.security_id → securities.security_id
- portfolio_performance.portfolio_id → portfolios.portfolio_id
- risk_metrics.portfolio_id → portfolios.portfolio_id
"""


def generate_sql(question: str, client, retries: int = 3) -> str:
    """Convert a natural language question into a SQL query via Gemini.
    Automatically retries on rate-limit errors using the suggested wait time."""
    prompt = f"""You are a SQL expert. Given the following SQLite database schema, write a SQL query to answer the question.

SCHEMA:
{SCHEMA_SUMMARY}

RULES:
- Return ONLY the raw SQL query, no explanation, no markdown, no backticks.
- ONLY generate SELECT statements. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE or PRAGMA.
- Use proper JOINs when querying across tables.
- Use aliases for clarity in complex queries.
- For aggregations, always use appropriate GROUP BY clauses.

QUESTION: {question}

SQL QUERY:"""

    last_err = None
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            sql = response.text.strip()
            sql = sql.replace("```sql", "").replace("```", "").strip()
            return sql

        except Exception as e:
            last_err = e
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if attempt < retries - 1:
                    match = re.search(r'"retryDelay":\s*"(\d+)s"', err) or re.search(r"seconds:\s*(\d+)", err)
                    wait = int(match.group(1)) + 3 if match else 35
                    print(f"  [sql_tool] Rate limited. Waiting {wait}s (attempt {attempt + 1}/{retries})...")
                    time.sleep(wait)
                    continue
            raise

    raise last_err

def run_query(sql: str) -> list[dict]:
    """Execute a SQL SELECT query and return results as list of dicts."""
    cleaned = sql.strip().lower()
    if not (cleaned.startswith("select") or cleaned.startswith("with")):
        raise ValueError("Only SELECT queries are allowed.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# Implemented the following function for smaller dataset instead of using pandas
def format_result(rows: list[dict]) -> str:
    """Format query results into a readable string."""
    if not rows:
        return "No results found."

    if len(rows) == 1 and len(rows[0]) == 1:
        value = list(rows[0].values())[0]
        return str(value)

    headers = list(rows[0].keys())
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, key in enumerate(headers):
            col_widths[i] = max(col_widths[i], len(str(row[key])))

    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator   = "  ".join("-" * w for w in col_widths)
    lines = [header_line, separator]
    for row in rows:
        line = "  ".join(str(row[k]).ljust(col_widths[i]) for i, k in enumerate(headers))
        lines.append(line)

    return "\n".join(lines)

def answer_with_sql(question: str, client, verbose: bool = False) -> dict:
    """Full pipeline: question → SQL → query DB → formatted result."""
    sql = None
    try:
        sql = generate_sql(question, client)
        if verbose:
            print(f"  [sql_tool] Generated SQL: {sql}")
        rows = run_query(sql)
        answer = format_result(rows)
        return {"sql": sql, "rows": rows, "answer": answer, "error": None}
    except Exception as e:
        return {"sql": sql, "rows": [], "answer": None, "error": str(e)}