# cis6930sp26-assignment1

ETL pipeline for Gainesville crime incident data: **Extract** (Socrata API) → **Transform** (clean, categorize, anomaly detection) → **Load** (SQLite). The pipeline is orchestrated by a rule-based planner or an LLM that decides fetch size, categories, and summary SQL.

---

## Setup and Usage Instructions

### Prerequisites

- **Python**: 3.10, 3.11, or 3.12
- **Optional**: [uv](https://docs.astral.sh/uv/) for dependency management (recommended)
- **For LLM mode only**: API key for an OpenAI-compatible service (NavigatorAI).
- **Network**: Required for Extract (Socrata API). Tests run without network.

### Clone and install

```bash
git clone <your-repo-url>
cd cis6930sp26-assignment1
```

**With uv (recommended):**

```bash
uv sync --extra dev
```

**With pip:**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

**Optional environment:**

```bash
cp .env.example .env
# add NAVIGATORAI_KEYS
```

### Starting MCP servers and running the orchestration script

You do **not** start the MCP servers by hand. The orchestration script (`pipeline.py`) starts them automatically as subprocesses and connects via MCP stdio:

1. When you run `python pipeline.py` (or `uv run python pipeline.py`), it:
   - Spawns `servers/extract_server.py`, `servers/transform_server.py`, and `servers/load_server.py` as child processes
   - Connects to each using the MCP client (stdio transport)
   - Calls the tools on each server in sequence (get_schema, fetch_incidents, detect_anomalies, clean_dates, categorize_incidents, save_to_sqlite, generate_summary, query_database)

So a single command runs both “start servers” and “execute orchestration.”

### Run the full pipeline end-to-end

**Rule-based (default):**

```bash
uv run python pipeline.py
# or: python pipeline.py
```

**LLM-orchestrated (requires API key):**

```bash
NAVIGATORAI_API_KEY=sk-xxxxx
uv run python pipeline.py
```

### Run tests

```bash
uv run pytest tests/ -v
# or: pytest tests/ -v
```

CI runs the same via `.github/workflows/pytest.yml` on push/PR.

### Expected output and how to verify success

**Console output:** The pipeline prints a **PIPELINE REPORT** with:

- **Schema (inferred):** endpoint, `num_fields_in_sample`, `fields`, notes
- **Anomaly summary:** `total_rows`, `rows_with_issues`, `issue_rate`, `date_fields_checked`
- **Saved:** `status`, `saved_rows`, `table`, `db` (e.g. `saved_rows: 2000`, `db: data/incidents.db`)
- **Table summary:** table name, `rows_sampled_for_summary`, `columns`, `category_counts`, `date_columns_detected`, `null_rate_by_column`
- **SQL summary:** result of the summary query (e.g. category counts)

**Verification:**

1. **Exit code:** Process exits with 0.
2. **File:** `data/incidents.db` exists and is non-empty.
3. **Report:** “Saved” shows `"status": "ok"` and `saved_rows` > 0; “Table summary” shows `rows_sampled_for_summary` > 0; “SQL summary” shows `rows` with at least one category count.

---

## Pipeline Comparison (MCP + LLM vs traditional)

This section compares the **MCP pipeline with optional LLM orchestration** to a **traditional single-process ETL script** (e.g. one Python file that imports extract/transform/load functions and runs them in order).

### Flexibility: How does the LLM handle unexpected data quality issues?

- **Traditional:** Logic is fixed in code (e.g. always fetch 2000 rows, same categories). Handling new data issues requires code changes.
- **This pipeline:** The LLM receives schema + a sample + an **anomaly summary** (from the `detect_anomalies` tool). It can respond in the **plan** (e.g. lower `fetch_limit` if anomalies are high, or keep defaults). The pipeline does not today let the LLM add new transformation steps on the fly; it only chooses parameters (fetch limit, categories, summary SQL). So flexibility is in **parameter choice** based on data quality, not in changing the set of tools or steps.

### Transparency: Can you understand why the LLM made certain decisions?

- **Traditional:** Decisions are explicit in code (e.g. constants and conditionals).
- **This pipeline:** When `USE_LLM=1`, the LLM is prompted to return a **reasoning** field in its JSON plan. That string is printed as `[LLM reasoning]` before the report, so you can see the model’s stated rationale. The plan itself (fetch_limit, categories, summary_sql) is also visible in the code path that executes it. So transparency is via the optional reasoning text and the fixed, readable orchestration flow.

### Reliability: Did the LLM ever make mistakes? How did you handle them?

- **Possible mistakes:** The LLM might return invalid JSON, omit required keys, or suggest values that break constraints (e.g. negative limit).
- **Handling:** (1) The pipeline parses the LLM response with a **fallback**: if the string is empty, contains “unknown tool”/“error”, or is not valid JSON, it uses the **rule-based plan** instead.
- (2) Tool calls still go through the same MCP tools, which validate inputs (e.g. `fetch_incidents` raises `ValueError` for bad limit/offset). So a bad plan can cause a tool error but not silent wrong behavior; and many LLM output failures fall back to the rule-based plan so the pipeline still completes.

### Performance: Execution time and token usage

- **Execution time:** The MCP pipeline is slower than a traditional in-process script because:
- (1) three server processes are started and communicated with over stdio;
- (2) each tool call is a round-trip (request/response). A traditional script would do the same work with in-process function calls and no serialization.
- **LLM mode** adds one HTTP request to the LLM API (and optionally a small sample fetch + anomaly run) before the main fetch; so it’s slightly slower than rule-based MCP, but the dominant cost is still the MCP tool calls and the Socrata fetch.
- **Token usage (LLM mode only):** One request per run: the prompt includes schema (truncated), a sample (truncated), and anomaly summary; the model returns a short JSON plan and optional reasoning. So token usage is on the order of a few hundred to low thousands of tokens per run, depending on model and truncation.

---

## Bugs and Assumptions

**Assumptions:**

- Socrata API returns a JSON array (or we treat it as such) and remains available at the default endpoint.
- Extract/transform/load servers are run from the **project root** (pipeline sets `cwd` so `data/incidents.db` and relative paths resolve correctly).
- LLM response, when used, is JSON with at least `fetch_limit`, `fetch_offset`, `categories`, and optionally `table_name`, `summary_sql`, `reasoning`; missing optional fields are defaulted in code.
- Column names from the API (e.g. `:@computed_region_*`) are sanitized for SQLite (no `:`, `@`); object/dict columns are serialized to strings so SQLite INSERT succeeds.

**Known limitations:**

- Transform categorization is keyword-based (regex on a single text field); the LLM does not redefine the categorization logic, only the category list.
- Pipeline does not retry on transient API or LLM failures.
- `generate_summary` uses a 20,000-row cap for the sample; very large tables are summarized from a subset.

**Known bugs:**

- None currently. If you find issues (e.g. on a specific Python or OS version), document them here.

---

## Project structure

| Path | Description |
|------|-------------|
| `servers/extract_server.py` | MCP Extract: `fetch_incidents`, `get_incident_types`, `get_schema` |
| `servers/transform_server.py` | MCP Transform: `clean_dates`, `categorize_incidents`, `detect_anomalies` |
| `servers/load_server.py` | MCP Load: `save_to_sqlite`, `query_database`, `generate_summary` |
| `pipeline.py` | Orchestrator: connects to MCP servers, runs ETL (rule-based or LLM plan) |
| `tests/` | Pytest tests per server (`test_extract.py`, `test_transform.py`, `test_load.py`) |
| `data/` | Output directory; `data/incidents.db` is written here |

---
