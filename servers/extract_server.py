from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("GainesvilleExtractServer")

DEFAULT_ENDPOINT = "https://data.cityofgainesville.org/resource/gvua-xt9q.json"

def _endpoint() -> str:
    return os.getenv("GAINESVILLE_API_ENDPOINT", DEFAULT_ENDPOINT).strip()

def _safe_get(url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise ValueError("API did not return a JSON list.")
        return data
    except requests.RequestException as e:
        raise RuntimeError(f"HTTP error while fetching incidents: {e}") from e
    except ValueError as e:
        raise RuntimeError(f"JSON parse/schema error: {e}") from e


def _infer_schema(sample: List[Dict[str, Any]]) -> Dict[str, Any]:
    keys = sorted({k for row in sample for k in row.keys()})
    return {
        "endpoint": _endpoint(),
        "num_fields_in_sample": len(keys),
        "fields": keys,
        "notes": "Schema is inferred from a sample because Socrata metadata may vary.",
    }

@mcp.tool()
def fetch_incidents(limit: int = 100, offset: int = 0) -> str:
    """Fetch crime incident data from the Gainesville API. Returns JSON string."""
    if limit <= 0 or limit > 50000:
        raise ValueError("limit must be between 1 and 50000")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    try:
        url = _endpoint()
        params = {"$limit": limit, "$offset": offset}
        rows = _safe_get(url, params)
        return json.dumps({"rows": rows, "limit": limit, "offset": offset})
    except (RuntimeError, ValueError) as e:
        raise
    except Exception as e:
        raise RuntimeError(f"fetch_incidents failed: {e}") from e


@mcp.tool()
def get_incident_types() -> List[str]:
    """Get a list of unique incident types in the dataset."""
    try:
        url = _endpoint()
        rows = _safe_get(url, {"$limit": 5000, "$offset": 0})
    except (RuntimeError, ValueError) as e:
        raise
    except Exception as e:
        raise RuntimeError(f"get_incident_types failed: {e}") from e
    if not rows:
        return []

    candidate_fields = [
        "incident_type",
        "incident",
        "offense",
        "offense_description",
        "call_type",
        "nature",
        "type",
        "description",
    ]

    field = next((f for f in candidate_fields if f in rows[0]), None)
    if field is None:
        keys = list(rows[0].keys())
        field = keys[0]

    vals = sorted({str(r.get(field, "")).strip() for r in rows if r.get(field)})
    return [v for v in vals if v]


@mcp.tool()
def get_schema() -> str:
    """Return the schema of the incidents data (inferred from a sample). Returns JSON."""
    try:
        url = _endpoint()
        sample = _safe_get(url, {"$limit": 50, "$offset": 0})
        schema = _infer_schema(sample)
        return json.dumps(schema, indent=2)
    except (RuntimeError, ValueError) as e:
        raise
    except Exception as e:
        raise RuntimeError(f"get_schema failed: {e}") from e


if __name__ == "__main__":
    mcp.run()
