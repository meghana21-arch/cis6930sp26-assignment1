"""Tests for the transform server (MCP tools: clean_dates, categorize_incidents, detect_anomalies)."""
import json
import pytest
from servers.transform_server import clean_dates, categorize_incidents, detect_anomalies

def test_clean_dates():
    inp = json.dumps({"rows": [{"report_date": "2020-01-01T10:00:00.000"}]})
    out = json.loads(clean_dates(inp))
    assert "rows" in out
    assert len(out["rows"]) == 1
    assert "report_date" in out["rows"][0]

def test_clean_dates_empty_rows():
    inp = json.dumps({"rows": []})
    out = json.loads(clean_dates(inp))
    assert out["rows"] == []
    assert "meta" in out

def test_categorize():
    inp = json.dumps({"rows": [{"incident_type": "ROBBERY"}]})
    out = json.loads(categorize_incidents(inp, ["violent", "other"]))
    assert "rows" in out
    assert out["rows"][0]["category"] in ["violent", "other"]

def test_categorize_default_categories():
    inp = json.dumps({"rows": [{"narrative": "theft at store"}]})
    out = json.loads(categorize_incidents(inp, []))
    assert out["rows"][0]["category"] == "property"

def test_detect_anomalies():
    inp = json.dumps({"rows": [{"incident_type": ""}]})
    out = json.loads(detect_anomalies(inp))
    assert "summary" in out
    assert "total_rows" in out["summary"]
    assert "anomalies" in out

def test_detect_anomalies_empty_rows():
    inp = json.dumps({"rows": []})
    out = json.loads(detect_anomalies(inp))
    assert out["summary"]["total_rows"] == 0
    assert out["anomalies"] == []

def test_invalid_input_raises():
    with pytest.raises((ValueError, RuntimeError)):
        clean_dates("not valid json")
    with pytest.raises((ValueError, RuntimeError)):
        detect_anomalies("not valid json")
