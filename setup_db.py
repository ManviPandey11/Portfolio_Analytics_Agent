import sqlite3
import csv
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "portfolio.db")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "database_schema.sql")

def get_connection():
    """Return a connection to the portfolio database."""
    return sqlite3.connect(DB_PATH)

def load_csv(conn, table_name, csv_path):
    """Load a CSV file into the given table."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            return

        columns = rows[0].keys()
        placeholders = ", ".join(["?" for _ in columns])
        col_names = ", ".join(columns)
        sql = f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders})"

        for row in rows:
# Replace empty strings with None so SQLite stores NULL
            values = [v if v != "" else None for v in row.values()]
            conn.execute(sql, values)
    conn.commit()
    print(f"  Loaded {len(rows)} rows into '{table_name}'")

def setup_database():
    """Create schema and load all CSV data into the database."""
# Remove existing DB so we always start fresh
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = ON")

# Create schema
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    print("Schema created.")

# Load CSVs in dependency order (respect foreign keys)
    tables = [
        ("sectors",              "sectors.csv"),
        ("benchmarks",           "benchmarks.csv"),
        ("securities",           "securities.csv"),
        ("portfolios",           "portfolios.csv"),
        ("holdings",             "holdings.csv"),
        ("transactions",         "transactions.csv"),
        ("historical_prices",    "historical_prices.csv"),
        ("portfolio_performance","portfolio_performance.csv"),
        ("risk_metrics",         "risk_metrics.csv"),
    ]

    print("Loading CSV data...")
    for table, csv_file in tables:
        csv_path = os.path.join(DATA_DIR, csv_file)
        if os.path.exists(csv_path):
            load_csv(conn, table, csv_path)
        else:
            print(f"  WARNING: {csv_file} not found, skipping.")

    conn.close()
    print(f"\nDatabase ready at: {DB_PATH}")

if __name__ == "__main__":
    setup_database()