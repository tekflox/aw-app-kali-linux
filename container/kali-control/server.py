#!/usr/bin/env python3
"""kali_control — stdlib-only stdio MCP server, baked into this image and
registered as a SECOND upstream of this container's own standalone gateway
(alongside ``playwright`` — see ``container/defaults/gateway-mcp.json``).

Exposes exactly two tools: ``proxy_set`` and ``proxy_status``, letting the
workspace's Settings UI (via the core ``leaf-tool`` bridge) and any federated
agent enable/disable routing the automation Chromium through aw-app-proxy and
check the current state. See ADR-kali-proxy-toggle.md §2a/§2d.

Speaks the exact newline-delimited JSON-RPC subset
``aw-mcp-gateway/back/gateway/upstream.py``'s ``Upstream`` class speaks to
every stdio child: ``initialize`` -> ``notifications/initialized`` (no
reply) -> ``tools/list`` at startup, then any number of ``tools/call``.
stdlib only, on purpose — this runs inside the gateway's own pinned venv
(``container/Dockerfile``), which must not grow app-specific dependencies.

MUST always publish both tools in ``tools/list``, even with a missing or
corrupt flag file — a zero-tool upstream is treated as a failed start and
parked by the gateway (``server.py:171-186``). Every helper below degrades to
a safe default instead of raising, so a broken flag file never prevents
``tools/list`` from answering.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import urllib.error
import urllib.request

#: $AW_APP_DATA/aw-proxy/config.json — NOT under /config/aw-mcp-gateway/,
#: which the s6 run script clobbers on every boot (run:22-33).
FLAG_PATH = "/config/aw-proxy/config.json"
#: The ONLY profile this must ever match when killing/scanning Chromium —
#: a loose match would also catch the KDE/Selkies desktop's own processes.
PROFILE_DIR = "/config/aw-playwright-profile"
PROXY_PORT = 9124
PROXY_PROBE_TIMEOUT = 2.0

TOOLS = [
    {
        "name": "proxy_set",
        "description": (
            "Enable or disable routing the automation Chromium through "
            "aw-app-proxy. Persists to /config/aw-proxy/config.json (survives "
            "container restart) and, by default, kills the running "
            "profile-matched Chromium so @playwright/mcp relaunches it with "
            "the new setting applied — no gateway reload, no container "
            "recreate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "restart_browser": {"type": "boolean", "default": True},
            },
            "required": ["enabled"],
        },
    },
    {
        "name": "proxy_status",
        "description": (
            "Current proxy-routing state: the persisted flag, whether a "
            "running browser actually has it applied, whether aw-app-proxy "
            "is reachable, and the MITM CA trust state."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _read_flag() -> bool:
    try:
        with open(FLAG_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return bool(doc.get("enabled", False))
    except (OSError, ValueError):
        return False


def _write_flag(enabled: bool) -> None:
    os.makedirs(os.path.dirname(FLAG_PATH), exist_ok=True)
    tmp = f"{FLAG_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"enabled": bool(enabled)}, f)
    os.replace(tmp, FLAG_PATH)


def _workspace_host() -> str:
    return os.environ.get("AW_WORKSPACE_HOST", "127.0.0.1")


def _profile_cmdlines():
    """(pid, raw_cmdline_bytes) for every /proc process whose cmdline
    carries this exact profile's --user-data-dir. Best-effort: a process
    that exits mid-scan just disappears from /proc, which OSError below
    already treats as "not this one"."""
    needle = f"--user-data-dir={PROFILE_DIR}".encode()
    for cmdline_path in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(cmdline_path, "rb") as f:
                raw = f.read()
        except OSError:
            continue
        if not raw or needle not in raw:
            continue
        try:
            pid = int(cmdline_path.split("/")[2])
        except (IndexError, ValueError):
            continue
        yield pid, raw


def _effective() -> bool | None:
    """Does a RUNNING, profile-matched Chromium already have --proxy-server
    on its command line? ``None`` means no such process is up at all —
    distinct from "up but not proxied"."""
    found = False
    for _pid, raw in _profile_cmdlines():
        found = True
        if b"--proxy-server=" in raw:
            return True
    return False if found else None


def _mitm_ca_installed() -> bool:
    nssdb = os.path.join(os.environ.get("HOME", "/config"), ".pki", "nssdb")
    try:
        return os.path.isdir(nssdb) and any(os.scandir(nssdb))
    except OSError:
        return False


def _proxy_probe() -> tuple[bool, bool]:
    """(reachable, mitm_capable). A connect refused/timeout is "unreachable
    or CIDR-blocked" (aw-app-proxy silently closes disallowed source IPs,
    proxy_server.py:211-219) — NOT the same as "proxy is down", but this
    process has no way to tell those apart from here either, so it reports
    the honest union. Any HTTP response at all — including the installed
    0.12.1's 404 for an endpoint that doesn't exist yet — counts as
    reachable."""
    url = f"http://{_workspace_host()}:{PROXY_PORT}/mitm-ca-spki"
    try:
        with urllib.request.urlopen(url, timeout=PROXY_PROBE_TIMEOUT) as resp:
            return True, resp.status == 200
    except urllib.error.HTTPError:
        return True, False
    except (urllib.error.URLError, OSError, ValueError):
        return False, False


def _mitm_ca_state(reachable: bool, mitm_capable: bool) -> str:
    if _mitm_ca_installed():
        return "installed"
    return "available" if (reachable and mitm_capable) else "absent"


def proxy_status() -> dict:
    enabled = _read_flag()
    effective = _effective()
    reachable, mitm_capable = _proxy_probe()
    return {
        "enabled": enabled,
        "effective": effective,
        "pending_browser_restart": effective is not None and effective != enabled,
        "proxy_reachable": reachable,
        "mitm_ca": _mitm_ca_state(reachable, mitm_capable),
        "proxy_url": f"http://{_workspace_host()}:{PROXY_PORT}",
    }


def _kill_profile_chromium() -> None:
    """SIGTERM every profile-matched Chromium — @playwright/mcp relaunches
    lazily on its next tool call, picking up chromium-aw's new flag read.
    Also clears the Singleton* lock files the boot script only clears at
    boot (run:35-43), or the relaunch can refuse with "already in use"."""
    for pid, _raw in _profile_cmdlines():
        try:
            os.kill(pid, 15)  # SIGTERM
        except OSError:
            continue
    for lock in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            os.remove(os.path.join(PROFILE_DIR, lock))
        except OSError:
            pass


def proxy_set(enabled: bool, restart_browser: bool = True) -> dict:
    _write_flag(enabled)
    if restart_browser:
        _kill_profile_chromium()
    return proxy_status()


def handle_call(name: str, arguments: dict) -> tuple[dict, bool]:
    """(result_payload, is_error) — never raises, so a bad call degrades to
    an error-shaped result instead of ever taking the whole server down."""
    try:
        if name == "proxy_status":
            return proxy_status(), False
        if name == "proxy_set":
            if "enabled" not in arguments:
                return {"error": "enabled is required"}, True
            return proxy_set(bool(arguments["enabled"]),
                             bool(arguments.get("restart_browser", True))), False
        return {"error": f"unknown tool {name!r}"}, True
    except Exception as exc:  # noqa: BLE001 — see docstring
        return {"error": str(exc)}, True


def _write_message(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _respond(req_id, *, result=None, error=None) -> None:
    msg = {"jsonrpc": "2.0", "id": req_id}
    msg["error" if error is not None else "result"] = error if error is not None else result
    _write_message(msg)


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        req_id = msg.get("id")

        if method == "initialize":
            _respond(req_id, result={
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "kali_control", "version": "1.0.0"},
            })
        elif method == "notifications/initialized":
            continue  # a notification — no id, no reply
        elif method == "tools/list":
            _respond(req_id, result={"tools": TOOLS})
        elif method == "tools/call":
            params = msg.get("params") or {}
            payload, is_error = handle_call(params.get("name"), params.get("arguments") or {})
            _respond(req_id, result={
                "content": [{"type": "text", "text": json.dumps(payload)}],
                "isError": is_error,
            })
        elif req_id is not None:
            _respond(req_id, error={"code": -32601, "message": f"unknown method {method!r}"})


if __name__ == "__main__":
    main()
