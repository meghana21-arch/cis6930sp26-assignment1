"""Tests for the extract server (MCP tools: fetch_incidents, get_incident_types, get_schema)."""
import json
import pytest
from servers.extract_server import _infer_schema, fetch_incidents

def test_infer_schema():
    sample = [{"a": 1, "b": "x"}, {"b": "y", "c": 3}]
    schema = _infer_schema(sample)
    assert "fields" in schema
    assert set(schema["fields"]) == {"a", "b", "c"}
    assert "num_fields_in_sample" in schema

def test_fetch_incidents_validates_limit():
    with pytest.raises(ValueError, match="limit must be between"):
        fetch_incidents(limit=0, offset=0)
    with pytest.raises(ValueError, match="limit must be between"):
        fetch_incidents(limit=50001, offset=0)

def test_fetch_incidents_validates_offset():
    with pytest.raises(ValueError, match="offset"):
        fetch_incidents(limit=100, offset=-1)
