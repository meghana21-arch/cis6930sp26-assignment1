from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

import pandas as pd
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("GainesvilleTransformServer")

def _loads_rows(data: str) -> List[Dict[str, Any]]:
    obj = json.loads(data)
    if isinstance(obj, dict) and "rows" in obj and isinstance(obj["rows"], list):
        return obj["rows"]
    if isinstance(obj, list):
        return obj
    raise ValueError("Expected JSON list OR {'rows': [...]} JSON object")


def _dumps_rows(rows: List[Dict[str, Any]], meta: Dict[str, Any] | None = None) -> str:
    payload = {"rows": rows}
    if meta:
        payload["meta"] = meta
    return json.dumps(payload)


def _find_date_fields(sample_row: Dict[str, Any]) -> List[str]:
    # standardize any key containing “date” or “time”
    date_like = []
    for k in sample_row.keys():
        lk = k.lower()
        if "date" in lk or "time" in lk:
            date_like.append(k)
    return date_like


def _choose_text_field(row: Dict[str, Any]) -> Tuple[str | None, str]:
    candidates = [
        "incident_type",
        "incident",
        "offense",
        "offense_description",
        "call_type",
        "nature",
        "description",
        "report_type",
    ]
    for c in candidates:
        if c in row and row.get(c):
            return c, str(row.get(c))
    # fallback: first non-empty string value
    for k, v in row.items():
        if isinstance(v, str) and v.strip():
            return k, v
    return None, ""


@mcp.tool()
def clean_dates(data: str) -> str:
    """Parse and standardize date fields to ISO-8601 strings when possible."""
    try:
        rows = _loads_rows(data)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"clean_dates: invalid input data - {e}") from e
    except Exception as e:
        raise RuntimeError(f"clean_dates failed: {e}") from e
    if not rows:
        return _dumps_rows(rows, {"clean_dates": {"date_fields": [], "changed": 0}})

    date_fields = _find_date_fields(rows[0])
    changed = 0

    for r in rows:
        for f in date_fields:
            if f not in r or r[f] in (None, ""):
                continue
            dt = pd.to_datetime(r[f], errors="coerce", utc=True)
            if pd.isna(dt):
                continue
            iso = dt.isoformat()
            if r[f] != iso:
                r[f] = iso
                changed += 1

    return _dumps_rows(rows, {"clean_dates": {"date_fields": date_fields, "changed": changed}})


@mcp.tool()
def categorize_incidents(data: str, categories: List[str]) -> str:
    """
    Group incidents into broader categories.
    Adds: category (one of categories or 'other')
    """
    try:
        rows = _loads_rows(data)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"categorize_incidents: invalid input data - {e}") from e
    except Exception as e:
        raise RuntimeError(f"categorize_incidents failed: {e}") from e
    cats = [c.strip().lower() for c in categories if c and c.strip()]
    if not cats:
        cats = ["violent", "property", "drug", "traffic", "other"]

    keyword_map = {
        "violent": [r"\bassault\b", r"\bbattery\b", r"\brobbery\b", r"\bweapon\b", r"\bhomicide\b"],
        "property": [r"\btheft\b", r"\bburglary\b", r"\blarceny\b", r"\bvandal\b", r"\bstolen\b"],
        "drug": [r"\bdrug\b", r"\bnarcotic\b", r"\bmarijuana\b", r"\bpossession\b"],
        "traffic": [r"\btraffic\b", r"\bdui\b", r"\bspeed\b", r"\bcrash\b", r"\bcitation\b"],
    }

    compiled = {k: [re.compile(pat, re.I) for pat in pats] for k, pats in keyword_map.items()}
    assigned = 0

    for r in rows:
        _, text = _choose_text_field(r)
        text_l = text.lower()

        label = "other"
        for k, patterns in compiled.items():
            if any(p.search(text_l) for p in patterns):
                label = k
                break

        # respect user-provided categories if they differ
        if label not in cats:
            label = "other" if "other" in cats else cats[-1]

        r["category"] = label
        assigned += 1

    return _dumps_rows(rows, {"categorize_incidents": {"categories": cats, "assigned": assigned}})


@mcp.tool()
def detect_anomalies(data: str) -> str:
    """Identify potential data quality issues and return a report (JSON string)."""
    try:
        rows = _loads_rows(data)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"detect_anomalies: invalid input data - {e}") from e
    except Exception as e:
        raise RuntimeError(f"detect_anomalies failed: {e}") from e
    if not rows:
        return json.dumps({"anomalies": [], "summary": {"total_rows": 0}})

    anomalies = []
    total = len(rows)

    # date parsing check
    date_fields = _find_date_fields(rows[0])

    for i, r in enumerate(rows):
        issues = []

        # missing type/text
        _, text = _choose_text_field(r)
        if not text.strip():
            issues.append("missing_incident_text/type")

        # lat/long sanity
        for lat_key in ["latitude", "lat", "y"]:
            if lat_key in r and r.get(lat_key) not in (None, ""):
                try:
                    lat = float(r[lat_key])
                    if not (-90 <= lat <= 90):
                        issues.append(f"invalid_latitude:{lat_key}")
                except Exception:
                    issues.append(f"non_numeric_latitude:{lat_key}")

        for lon_key in ["longitude", "lon", "lng", "x"]:
            if lon_key in r and r.get(lon_key) not in (None, ""):
                try:
                    lon = float(r[lon_key])
                    if not (-180 <= lon <= 180):
                        issues.append(f"invalid_longitude:{lon_key}")
                except Exception:
                    issues.append(f"non_numeric_longitude:{lon_key}")

        for f in date_fields:
            if f in r and r.get(f):
                dt = pd.to_datetime(r[f], errors="coerce", utc=True)
                if pd.isna(dt):
                    issues.append(f"unparseable_date:{f}")

        if issues:
            anomalies.append({"row_index": i, "issues": issues})

    report = {
        "summary": {
            "total_rows": total,
            "rows_with_issues": len(anomalies),
            "issue_rate": round(len(anomalies) / total * 100, 2),
            "date_fields_checked": date_fields,
        },
        "anomalies": anomalies[:50], 
        "note": "Only first 50 anomaly rows returned; summary reflects full scan of provided data.",
    }
    return json.dumps(report)
    
if __name__ == "__main__":
    mcp.run()
