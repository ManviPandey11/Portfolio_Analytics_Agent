import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "portfolio.db")

def get_sector_exposures(portfolio_name: str) -> dict:
    """
    Calculate sector exposure percentages for a given portfolio.
    - Only considers equity (Stock) holdings, ignores bonds.
    - Exposure = sum of current_weight for holdings in each sector,
      re-normalised to 100% across equities only.

    Returns a dict with keys: portfolio_name, exposures (dict sector→%), error
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
# Verify portfolio exists
        port_row = conn.execute(
            "SELECT portfolio_id, portfolio_name FROM portfolios WHERE portfolio_name = ?",
            (portfolio_name,)
        ).fetchone()

        if not port_row:
            return {
                "portfolio_name": portfolio_name,
                "exposures": {},
                "error": f"Portfolio '{portfolio_name}' not found."
            }

        portfolio_id = port_row["portfolio_id"]

# Fetch equity holdings with their sector and current_weight
        rows = conn.execute("""
            SELECT
                sec.sector_name,
                h.current_weight
            FROM holdings h
            JOIN securities s ON h.security_id = s.security_id
            JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE h.portfolio_id = ?
              AND s.asset_type = 'Stock'
        """, (portfolio_id,)).fetchall()

        if not rows:
            return {
                "portfolio_name": portfolio_name,
                "exposures": {},
                "error": "No equity holdings found for this portfolio."
            }

# Aggregate weights per sector
        sector_weights = {}
        total_equity_weight = 0.0
        for row in rows:
            sector = row["sector_name"]
            weight = row["current_weight"] or 0.0
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
            total_equity_weight += weight

# Normalise to 100% across equities
        if total_equity_weight == 0:
            return {
                "portfolio_name": portfolio_name,
                "exposures": {},
                "error": "Total equity weight is zero, cannot compute exposures."
            }

        exposures = {
            sector: round((w / total_equity_weight) * 100, 2)
            for sector, w in sorted(sector_weights.items(), key=lambda x: -x[1])
        }

        return {
            "portfolio_name": portfolio_name,
            "exposures": exposures,
            "error": None
        }

    finally:
        conn.close()

def format_exposures(result: dict) -> str:
    """Format exposure result into a readable string."""
    if result["error"]:
        return f"Error: {result['error']}"

    lines = [f"Sector exposures for '{result['portfolio_name']}' (equities only):\n"]
    for sector, pct in result["exposures"].items():
        bar = "#" * int(pct / 2)
        lines.append(f"  {sector:<25} {pct:>6.2f}%  {bar}")

    total = sum(result["exposures"].values())
    lines.append(f"\n  {'TOTAL':<25} {total:>6.2f}%")
    return "\n".join(lines)