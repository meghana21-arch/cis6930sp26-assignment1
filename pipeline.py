from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Dict
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession


def _text_from_result(resp: Any) -> str:
    if getattr(resp, "structuredContent", None) is not None:
        return json.dumps(resp.structuredContent)
    if not getattr(resp, "content", None):
        return ""
    parts = []
    for block in resp.content:
        if getattr(block, "text", None) is not None:
            parts.append(block.text)
        elif getattr(block, "content", None):
            for sub in block.content:
                if getattr(sub, "text", None) is not None:
                    parts.append(sub.text)
    return "\n".join(parts) if parts else ""


def _unwrap_result(s: str) -> str:
    """If the MCP server returned {"result": "<json string>"}, return the inner string."""
    if not s or not s.strip():
        return s
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and "result" in obj and isinstance(obj["result"], str):
            return obj["result"]
    except (json.JSONDecodeError, TypeError):
        pass
    return s


@dataclass
class Servers:
    extract: ClientSession
    transform: ClientSession
    load: ClientSession


async def connect_servers() -> tuple[Servers, AsyncExitStack]:
    """
    Starts all 3 servers as subprocesses (stdio) and connects MCP clients.
    Returns (Servers, exit_stack); call await exit_stack.aclose() when done.
    """
    exit_stack = AsyncExitStack()

    project_root = os.path.dirname(os.path.abspath(__file__))

    async def start(path: str) -> ClientSession:
        params = StdioServerParameters(command="python", args=[path], cwd=project_root)
        read_stream, write_stream = await exit_stack.enter_async_context(
            stdio_client(params)
        )
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        return session

    extract = await start("servers/extract_server.py")
    transform = await start("servers/transform_server.py")
    load = await start("servers/load_server.py")

    return Servers(extract=extract, transform=transform, load=load), exit_stack


async def safe_call(session: ClientSession, tool: str, args: Dict[str, Any]) -> Any:
    resp = await session.call_tool(tool, args)
    return _text_from_result(resp)


def rule_based_plan(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    A simple “LLM-like” planner:
    - fetch more rows if schema seems small/unknown
    - always run anomaly detection
    - always clean dates + categorize
    """
    # You can tune this
    return {
        "fetch_limit": 2000,
        "fetch_offset": 0,
        "categories": ["violent", "property", "drug", "traffic", "other"],
        "table_name": "incidents_processed",
        "summary_sql": "SELECT category, COUNT(*) as n FROM incidents_processed GROUP BY category ORDER BY n DESC;",
    }


async def main():
    servers, exit_stack = await connect_servers()
    try:
        # 1) schema + sample
        schema_json = _unwrap_result((await safe_call(servers.extract, "get_schema", {}) or "").strip())
        if not schema_json or "unknown tool" in schema_json.lower() or "error" in schema_json.lower():
            schema = {"fields": [], "num_fields_in_sample": 0, "notes": "fallback (get_schema not available or failed)"}
        else:
            try:
                schema = json.loads(schema_json)
            except json.JSONDecodeError:
                schema = {"fields": [], "num_fields_in_sample": 0, "notes": "fallback (invalid JSON from get_schema)"}
        if not isinstance(schema, dict):
            schema = {"fields": [], "num_fields_in_sample": 0}

        # 2) plan
        plan = rule_based_plan(schema)

        # 3) extract
        raw_json = _unwrap_result(await safe_call(
            servers.extract,
            "fetch_incidents",
            {"limit": plan["fetch_limit"], "offset": plan["fetch_offset"]},
        ))

        # 4) detect anomalies
        anomalies_json = _unwrap_result((await safe_call(servers.transform, "detect_anomalies", {"data": raw_json}) or "").strip())
        try:
            anomalies = json.loads(anomalies_json) if anomalies_json else {}
        except json.JSONDecodeError:
            anomalies = {"summary": {"total_rows": 0, "note": "detect_anomalies returned invalid/empty response"}, "anomalies": []}
        if not isinstance(anomalies, dict):
            anomalies = {"summary": {}, "anomalies": []}

        # 5) transform (clean dates + categorize)
        cleaned_json = _unwrap_result(await safe_call(servers.transform, "clean_dates", {"data": raw_json}))
        categorized_json = _unwrap_result(await safe_call(
            servers.transform,
            "categorize_incidents",
            {"data": cleaned_json, "categories": plan["categories"]},
        ))

        # 6) load to sqlite
        save_json = _unwrap_result(await safe_call(
            servers.load,
            "save_to_sqlite",
            {"data": categorized_json, "table_name": plan["table_name"]},
        ))
        try:
            save_out = json.loads(save_json) if save_json.strip() else {}
        except json.JSONDecodeError:
            save_out = {"error": "save_to_sqlite returned invalid JSON", "raw_preview": save_json[:200] if save_json else "(empty)"}

        # 7) summary
        summary_json = _unwrap_result(await safe_call(servers.load, "generate_summary", {"table_name": plan["table_name"]}))
        sql_summary_json = _unwrap_result(await safe_call(servers.load, "query_database", {"sql": plan["summary_sql"]}))

        print("\n=== PIPELINE REPORT ===")
        print("Schema (inferred):")
        print(json.dumps(schema, indent=2)[:1200], "...\n")
        print("Anomaly summary:")
        print(json.dumps(anomalies.get("summary", {}), indent=2), "\n")
        print("Saved:")
        print(json.dumps(save_out, indent=2), "\n")
        print("Table summary:")
        print(summary_json, "\n")
        print("SQL summary:")
        print(sql_summary_json, "\n")

    finally:
        await exit_stack.aclose()

if __name__ == "__main__":
    asyncio.run(main())
