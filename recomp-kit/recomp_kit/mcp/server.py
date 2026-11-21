"""Zero-dependency stdio JSON-RPC 2.0 MCP server for recomp-kit (Principle 8).

Usage:
    .venv/bin/python recomp-kit/recomp mcp <project_dir>
"""
from __future__ import annotations

import json
import sys
from typing import Any

from recomp_kit import __version__
from recomp_kit.arch import get_arch
from recomp_kit.config import ProjectConfig, load_project
from recomp_kit.pipeline.builder import lift_project
from recomp_kit.re.inspect import get_function_detail, tag_function
from recomp_kit.re.queue import build_queue

TOOLS = [
    {
        "name": "recomp_status",
        "description": "Return full project status: target config, discovery counts, lift report summary, difftest gate, and RE queue summary.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "recomp_queue",
        "description": "Return coverage-weighted RE & trap priority queue (T1=ran+trapped, T2=ran+unnamed, T3=static_trapped).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 25, "description": "Max entries per tier"},
            },
        },
    },
    {
        "name": "recomp_inspect_function",
        "description": "Inspect one guest function: lifted C source, traps, seed type, coverage state, and current V/I/U ledger entry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "addr": {"type": "string", "description": "Hex address (e.g. '0x408000' or '408000')"},
            },
            "required": ["addr"],
        },
    },
    {
        "name": "recomp_tag_function",
        "description": "Record a function name & subsystem with strict V/I/U truth state and re-merge census/names.tsv.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "addr": {"type": "string", "description": "Hex address"},
                "name": {"type": "string", "description": "Function symbol name"},
                "system": {"type": "string", "description": "Subsystem tag (e.g. render, audio, core)"},
                "state": {"type": "string", "enum": ["V", "I", "U"], "default": "V"},
                "evidence": {"type": "string", "description": "Proof (exe addr, strings, 2nd tool check)"},
                "tool": {"type": "string", "default": "mcp-agent"},
            },
            "required": ["addr", "name", "system"],
        },
    },
    {
        "name": "recomp_verify_function",
        "description": "Run bit-exact Unicorn difftest on a single lifted function.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "addr": {"type": "string", "description": "Hex address of function to verify"},
                "cases": {"type": "integer", "default": 4},
            },
            "required": ["addr"],
        },
    },
    {
        "name": "recomp_lift",
        "description": "Run incremental .seal-cached static lift of the project and return lift_report summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "force": {"type": "boolean", "default": False},
                "cov": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "recomp_imports",
        "description": "List PE IAT imports, optionally filtered by DLL name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dll": {"type": "string", "description": "Optional DLL filter (e.g. d3d9.dll, kernel32.dll)"},
            },
        },
    },
]


def _call_tool(cfg: ProjectConfig, name: str, args: dict[str, Any]) -> Any:
    if name == "recomp_status":
        disc = json.loads(cfg.discovery_json.read_text(encoding="utf-8")) if cfg.discovery_json.exists() else {}
        lift = json.loads(cfg.lift_report_json.read_text(encoding="utf-8")) if cfg.lift_report_json.exists() else {}
        diff_p = cfg.census_dir / "difftest.json"
        diff = json.loads(diff_p.read_text(encoding="utf-8")) if diff_p.exists() else {}
        q = build_queue(cfg, limit=5)
        return {
            "project": cfg.name,
            "binary": str(cfg.resolve_binary()),
            "arch": cfg.arch,
            "format": cfg.fmt,
            "discovery": {
                "functions": disc.get("functions"),
                "text_coverage": disc.get("text_coverage"),
                "jump_tables": disc.get("jump_tables"),
                "imports_total": disc.get("imports", {}).get("total"),
            },
            "lift": {
                "functions": lift.get("functions"),
                "failed": len(lift.get("failed", {})),
                "real_trap_funcs": lift.get("functions_with_a_real_trap"),
                "top_traps": dict(list(lift.get("trap_sites_by_reason", {}).items())[:10]),
            },
            "difftest": {
                "gate": diff.get("gate"),
                "compared": diff.get("functions_compared"),
                "all_match": diff.get("functions_all_match"),
                "mismatch": diff.get("functions_with_mismatch"),
            },
            "queue_summary": q["summary"],
        }
    if name == "recomp_queue":
        return build_queue(cfg, limit=int(args.get("limit", 25)))
    if name == "recomp_inspect_function":
        addr = int(str(args["addr"]), 16)
        return get_function_detail(cfg, addr)
    if name == "recomp_tag_function":
        addr = int(str(args["addr"]), 16)
        return tag_function(
            cfg,
            addr=addr,
            name=str(args["name"]),
            system=str(args["system"]),
            state=str(args.get("state", "V")),
            evidence=str(args.get("evidence", "")),
            tool=str(args.get("tool", "mcp-agent")),
        )
    if name == "recomp_verify_function":
        addr = int(str(args["addr"]), 16)
        backend = get_arch(cfg.arch)
        return backend.verify(cfg, cases=int(args.get("cases", 4)), only=addr)
    if name == "recomp_lift":
        rep = lift_project(cfg, cov=bool(args.get("cov", False)), force=bool(args.get("force", False)))
        return {k: v for k, v in rep.items() if k != "blocked_functions"}
    if name == "recomp_imports":
        disc = json.loads(cfg.discovery_json.read_text(encoding="utf-8")) if cfg.discovery_json.exists() else {}
        names = disc.get("imports", {}).get("names", [])
        dll = (args.get("dll") or "").lower().strip()
        if dll:
            names = [n for n in names if n.lower().startswith(dll)]
        return {"count": len(names), "by_dll": disc.get("imports", {}).get("by_dll", {}), "imports": names}
    raise ValueError(f"Unknown tool: {name}")


def _send(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def serve_mcp(project_dir: str) -> int:
    cfg = load_project(project_dir)
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": f"recomp-kit ({cfg.name})", "version": __version__},
                },
            })
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            tname = params.get("name", "")
            targs = params.get("arguments") or {}
            try:
                res = _call_tool(cfg, tname, targs)
                _send({
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]},
                })
            except Exception as exc:
                _send({
                    "jsonrpc": "2.0",
                    "id": rid,
                    "result": {"isError": True, "content": [{"type": "text", "text": f"Error: {exc}"}]},
                })
        elif rid is not None:
            _send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}})
    return 0
