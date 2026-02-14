from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List

import pandas as pd
from mcp.server.fastmcp import FastMCP


def _sqlite_safe_column(name: str) -> str:
    """Make a column name valid for SQLite (no ':', '@', or leading digits)."""
    s = re.sub(r"[^\w]", "_", str(name).strip())
    s = s.lstrip("_") or "unnamed"
    if s[0].isdigit():
        s = "c_" + s
    return s or "unnamed"

mcp = FastMCP("GainesvilleLoadServer")


def _db_path() -> str:
    return os.getenv("SQLITE_PATH", "data/incidents.db")


def _ensure_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _loads_rows(data: str) -> List[Dict[str, Any]]:
    obj = json.loads(data)
    # Unwrap MCP-style {"result": "<json string>"} if present
    if isinstance(obj, dict) and "result" in obj and isinstance(obj["result"], str):
        obj = json.loads(obj["result"])
    if isinstance(obj, dict) and "rows" in obj and isinstance(obj["rows"], list):
        return obj["rows"]
    if isinstance(obj, list):
        return obj
    raise ValueError("Expected JSON list OR {'rows': [...]} JSON object")


@mcp.tool()
def save_to_sqlite(data: str, table_name: str) -> str:
    """Save processed data to SQLite database."""
    if not table_name or not table_name.strip():
        raise ValueError("table_name must be non-empty")

    rows = _loads_rows(data)
    db = _db_path()
    _ensure_dir(db)

    df = pd.DataFrame(rows)
    # Avoid empty dataframe issues
    if df.empty:
        return json.dumps({"status": "ok", "saved_rows": 0, "table": table_name, "db": db})

    # SQLite rejects column names with ':' (bind param) or '@'; sanitize to valid identifiers
    df.columns = [_sqlite_safe_column(c) for c in df.columns]
    # Ensure unique names (e.g. multiple columns could become "unnamed")
    seen: Dict[str, int] = {}
    new_cols = []
    for c in df.columns:
        key = c
        seen[key] = seen.get(key, 0) + 1
        new_cols.append(f"{c}_{seen[key]}" if seen[key] > 1 else c)
    df.columns = new_cols

    # SQLite cannot store dict/list; serialize object columns so INSERT doesn't fail
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda x: json.dumps(x) if isinstance(x, (dict, list)) else (x if pd.notna(x) else None)
            )
            df[col] = df[col].astype(str).replace("nan", "")

    try:
        with sqlite3.connect(db) as conn:
            df.to_sql(table_name, conn, if_exists="replace", index=False)
        return json.dumps({"status": "ok", "saved_rows": int(len(df)), "table": table_name, "db": db})
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        raise RuntimeError(f"Failed to write to sqlite: {err_msg}") from e


@mcp.tool()
def query_database(sql: str) -> str:
    """Execute a SQL query on the processed data. Returns JSON string with rows."""
    if not sql or not sql.strip():
        raise ValueError("sql must be non-empty")

    db = _db_path()
    if not os.path.exists(db):
        raise FileNotFoundError(f"Database not found at {db}. Run save_to_sqlite first.")

    try:
        with sqlite3.connect(db) as conn:
            cur = conn.cursor()
            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cols else []
        out = [dict(zip(cols, r)) for r in rows]
        return json.dumps({"columns": cols, "rows": out})
    except Exception as e:
        raise RuntimeError(f"SQL query failed: {e}") from e


@mcp.tool()
def generate_summary(table_name: str) -> str:
    """Generate summary statistics for a table."""
    if not table_name or not table_name.strip():
        raise ValueError("table_name must be non-empty")

    db = _db_path()
    if not os.path.exists(db):
        raise FileNotFoundError(f"Database not found at {db}. Run save_to_sqlite first.")

    try:
        with sqlite3.connect(db) as conn:
            df = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT 20000", conn)

        summary = {
            "table": table_name,
            "rows_sampled_for_summary": int(len(df)),
            "columns": list(df.columns),
        }

        # common summaries
        if "category" in df.columns:
            summary["category_counts"] = df["category"].value_counts(dropna=False).to_dict()

        # date columns heuristic
        date_cols = [c for c in df.columns if "date" in c.lower() or "time" in c.lower()]
        summary["date_columns_detected"] = date_cols

        # added checks for null rates 
        summary["null_rate_by_column"] = {}
        for c in df.columns:
            v = df[c].isna().mean()
            summary["null_rate_by_column"][c] = float(v) if pd.notna(v) else 0.0

        return json.dumps(summary, indent=2)
    except Exception as e:
        raise RuntimeError(f"Failed to generate summary: {e}") from e


if __name__ == "__main__":
    mcp.run()
