"""Tests for the load server (MCP tools: save_to_sqlite, query_database, generate_summary)."""
import json
import os
import pytest
from servers.load_server import (
    _loads_rows,
    save_to_sqlite,
    query_database,
    generate_summary,
)

def test_loads_rows_accepts_list():
    data = json.dumps([{"a": 1}, {"b": 2}])
    rows = _loads_rows(data)
    assert rows == [{"a": 1}, {"b": 2}]

def test_loads_rows_accepts_rows_object():
    data = json.dumps({"rows": [{"id": "1"}]})
    rows = _loads_rows(data)
    assert rows == [{"id": "1"}]

def test_loads_rows_unwraps_result():
    """MCP can return {"result": "<json string>"}; load server should accept it."""
    inner = json.dumps({"rows": [{"x": 1}]})
    data = json.dumps({"result": inner})
    rows = _loads_rows(data)
    assert rows == [{"x": 1}]

def test_save_and_query(tmp_path, monkeypatch):
    db = tmp_path / "incidents.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))

    data = json.dumps({"rows": [{"category": "other", "x": "1"}]})
    save = json.loads(save_to_sqlite(data, "t"))
    assert save["saved_rows"] == 1
    assert save["status"] == "ok"
    assert os.path.exists(db)

    q = json.loads(query_database("SELECT COUNT(*) as n FROM t"))
    assert "rows" in q and "columns" in q
    assert q["rows"][0]["n"] == 1

    s = json.loads(generate_summary("t"))
    assert s["table"] == "t"
    assert "columns" in s
    assert "null_rate_by_column" in s

def test_save_to_sqlite_rejects_empty_table_name():
    with pytest.raises(ValueError, match="non-empty"):
        save_to_sqlite(json.dumps({"rows": []}), "")
def test_query_database_rejects_empty_sql():
    with pytest.raises(ValueError, match="non-empty"):
        query_database("")
