import json
from servers.transform_server import clean_dates, categorize_incidents, detect_anomalies

def test_clean_dates():
    inp = json.dumps({"rows": [{"report_date": "2020-01-01T10:00:00.000"}]})
    out = json.loads(clean_dates(inp))
    assert "rows" in out
    assert "report_date" in out["rows"][0]

def test_categorize():
    inp = json.dumps({"rows": [{"incident_type": "ROBBERY"}]})
    out = json.loads(categorize_incidents(inp, ["violent", "other"]))
    assert out["rows"][0]["category"] in ["violent", "other"]

def test_detect_anomalies():
    inp = json.dumps({"rows": [{"incident_type": ""}]})
    out = json.loads(detect_anomalies(inp))
    assert "summary" in out
