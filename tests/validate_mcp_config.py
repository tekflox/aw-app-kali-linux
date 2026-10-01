#!/usr/bin/env python3
"""Validates mcp.json — the file the MCP Gateway app's
``scan_app_mcp_servers()`` reads from this app's root directory, registering
this container's own standalone gateway as a federated `type: gateway`
upstream (see aw-mcp-gateway/back/gateway/upstream.py's GatewayUpstream).

Run with: python3 tests/validate_mcp_config.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

config = json.loads((ROOT / "mcp.json").read_text())

assert "mcpServers" in config, "mcp.json must have a top-level 'mcpServers' object"
servers = config["mcpServers"]
assert "kali" in servers, "expected a 'kali' server entry"

kali = servers["kali"]
assert kali.get("type") == "gateway", "kali server must be type 'gateway' (federates this container's own gateway)"
assert kali.get("enabled") is True, "kali server should be enabled by default"
url = kali.get("url", "")
assert url.startswith("http://aw-app-kali-linux:"), (
    f"url should target this app's own container name (aw-app-<id>), got {url!r}"
)
assert url.endswith("/mcp"), f"url should point at the leaf gateway's /mcp endpoint, got {url!r}"

print("OK: mcp.json is structurally valid")
