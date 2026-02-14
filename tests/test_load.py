import json
import os
from servers.load_server import save_to_sqlite, query_database, generate_summary

def test_save_and_query(tmp_path, monkeypatch):
    db = tmp_path / "incidents.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))

    data = json.dumps({"rows": [{"category": "other", "x": "1"}]})
    save = json.loads(save_to_sqlite(data, "t"))
    assert save["saved_rows"] == 1
    assert os.path.exists(db)

    q = json.loads(query_database("SELECT COUNT(*) as n FROM t"))
    assert q["rows"][0]["n"] == 1

    s = json.loads(generate_summary("t"))
    assert s["table"] == "t"
