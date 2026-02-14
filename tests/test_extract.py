import json
from servers.extract_server import _infer_schema

def test_infer_schema():
    sample = [{"a": 1, "b": "x"}, {"b": "y", "c": 3}]
    schema = _infer_schema(sample)
    assert "fields" in schema
    assert set(schema["fields"]) == {"a", "b", "c"}
