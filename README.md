# cis6930sp26-assignment1

This project implements an ETL pipeline for Gainesville crime incident data using MCP (Model Context Protocol). The pipeline extracts data from the Socrata API, applies cleaning and transformation steps, and loads the processed results into a SQLite database. The workflow can be executed either using a rule-based planner or an LLM-driven orchestration.

## Structure

| Path | Description |
|------|-------------|
| **`servers/`** | MCP servers (tools used by the pipeline) |
| `servers/extract_server.py` | Extract: `fetch_incidents`, `get_incident_types`, `get_schema` |
| `servers/transform_server.py` | Transform: `clean_dates`, `categorize_incidents`, `detect_anomalies` |
| `servers/load_server.py` | Load: `save_to_sqlite`, `query_database`, `generate_summary` |
| **`pipeline.py`** | Orchestrator: connects to MCP servers, runs ETL (rule-based or LLM-driven) |
| **`tests/`** | Pytest tests for each MCP server |
| **`data/`** | Output directory; `data/incidents.db` is written here |

---

## Setup

**Option A: uv (recommended)**

```bash
uv sync --extra dev
```

**Option B: pip**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

**Environment**

```bash
cp .env.example .env
# Edit .env for: GAINESVILLE_API_ENDPOINT, SQLITE_PATH, and (for LLM mode) USE_LLM, NAVIGATOR_KEY
```

---

## Usage

### Rule-based pipeline

The ETL pipeline uses a fixed plan (fetch limit, categories, summary SQL).

```bash
uv run python pipeline.py
# or: python pipeline.py
```

Output: schema, anomaly summary, save result, table summary, and SQL summary printed to stdout.

### LLM-orchestrated pipeline

An LLM (i.e NavigatorAI) decides how much data to fetch, which categories to use, and what summary SQL to run.
NOTE : setup this Navigator keys in the .env file
```bash
# NAVIGATOR_AI_URL, NAVIGATOR_AI_API_KEY
uv run python pipeline.py
```

The LLM receives schema + a small sample + anomaly summary and returns a JSON plan; the pipeline executes that plan via the same MCP tools.

---

## Pipeline comparison

| Aspect | Rule-based | LLM-orchestrated |
|--------|------------|------------------|
| **Configuration** | No env vars required (defaults in code) | NavigatorAI |
| **Plan** | Fixed: e.g. 2000 rows, categories `["violent","property","drug","traffic","other"]`, one summary SQL | LLM chooses fetch limit, categories, and summary SQL from schema + sample + anomalies |
| **When to use** | CI, demos, reproducible runs | Exploratory runs, adaptive behavior, different summary stats per run |
| **Failure mode** | Predictable (same steps every time) | Depends on LLM output; invalid JSON falls back to rule-based plan |
| **MCP usage** | Same: all tool calls go through the three MCP servers | Same tools; only the *parameters* (limit, categories, SQL) come from the LLM |

Both modes connect to the same Extract, Transform, and Load MCP servers and run the same sequence: get_schema → fetch_incidents → detect_anomalies → clean_dates → categorize_incidents → save_to_sqlite → generate_summary + query_database.

---

## Tests

Tests target each MCP server and run without network (except any optional integration test you add).

| Server | Test file | Coverage |
|--------|-----------|----------|
| **Extract** | `tests/test_extract.py` | `_infer_schema`, `fetch_incidents` validation (limit/offset) |
| **Transform** | `tests/test_transform.py` | `clean_dates`, `categorize_incidents`, `detect_anomalies` (normal + empty input, invalid input) |
| **Load** | `tests/test_load.py` | `_loads_rows` (list, `rows` object, MCP `result` unwrap), `save_to_sqlite`, `query_database`, `generate_summary`, input validation |

**Run tests**

```bash
uv run pytest tests/ -v
# or: pytest tests/ -v
```

CI: `.github/workflows/pytest.yml` runs pytest on push/PR (uv + `--extra dev`).

---
