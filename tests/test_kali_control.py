"""kali_control's handler logic — proxy_set / proxy_status / tools/list.

Run with: python3 -m pytest tests/test_kali_control.py

Exercises the pure functions directly (handle_call, proxy_status, proxy_set)
rather than spawning the server as a real stdio child — the NDJSON framing
in main() is a thin, mechanically-verified wrapper around these; what matters
is the tool CONTRACT (ADR-kali-proxy-toggle.md §2d) and the invariant that
tools/list must never go empty (§5.1 — a zero-tool upstream is treated as a
failed start and parked by the gateway).
"""
import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT / "container" / "kali-control" / "server.py"

spec = importlib.util.spec_from_file_location("kali_control_server", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
sys.modules["kali_control_server"] = server
spec.loader.exec_module(server)


def test_tools_list_always_publishes_both_tools():
    names = {t["name"] for t in server.TOOLS}
    assert names == {"proxy_set", "proxy_status"}


def test_flag_round_trips_through_the_file(tmp_path, monkeypatch):
    flag_path = tmp_path / "aw-proxy" / "config.json"
    monkeypatch.setattr(server, "FLAG_PATH", str(flag_path))

    assert server._read_flag() is False  # missing file degrades to disabled

    server._write_flag(True)
    assert server._read_flag() is True

    server._write_flag(False)
    assert server._read_flag() is False


def test_a_corrupt_flag_file_degrades_to_disabled_not_an_exception(tmp_path, monkeypatch):
    flag_path = tmp_path / "config.json"
    flag_path.write_text("{not json")
    monkeypatch.setattr(server, "FLAG_PATH", str(flag_path))

    assert server._read_flag() is False


def test_proxy_status_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "FLAG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(server, "_effective", lambda: None)
    monkeypatch.setattr(server, "_proxy_probe", lambda: (True, True))
    monkeypatch.setattr(server, "_mitm_ca_installed", lambda: False)

    status = server.proxy_status()

    assert status == {
        "enabled": False,
        "effective": None,
        "pending_browser_restart": False,
        "proxy_reachable": True,
        "mitm_ca": "available",
        "proxy_url": "http://127.0.0.1:9124",
    }


def test_pending_browser_restart_when_effective_disagrees_with_the_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "FLAG_PATH", str(tmp_path / "config.json"))
    server._write_flag(True)
    monkeypatch.setattr(server, "_effective", lambda: False)  # browser still unproxied
    monkeypatch.setattr(server, "_proxy_probe", lambda: (True, False))
    monkeypatch.setattr(server, "_mitm_ca_installed", lambda: False)

    status = server.proxy_status()

    assert status["enabled"] is True
    assert status["effective"] is False
    assert status["pending_browser_restart"] is True


def test_unreachable_proxy_reports_reachable_false_not_an_exception(monkeypatch):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(server.urllib.request, "urlopen", boom)

    reachable, mitm_capable = server._proxy_probe()

    assert reachable is False
    assert mitm_capable is False


def test_a_pre_mitm_proxy_404_still_counts_as_reachable(monkeypatch):
    """The installed aw-app-proxy (0.12.1) has no MITM endpoints at all —
    its 404 for /mitm-ca-spki must not be confused with the proxy being
    down. See ADR §2d."""
    import urllib.error

    def raise_404(*a, **k):
        raise urllib.error.HTTPError("url", 404, "not found", {}, None)

    monkeypatch.setattr(server.urllib.request, "urlopen", raise_404)

    reachable, mitm_capable = server._proxy_probe()

    assert reachable is True
    assert mitm_capable is False


def test_proxy_set_persists_and_returns_fresh_status(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "FLAG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(server, "_kill_profile_chromium", mock.Mock())
    monkeypatch.setattr(server, "_effective", lambda: None)
    monkeypatch.setattr(server, "_proxy_probe", lambda: (False, False))
    monkeypatch.setattr(server, "_mitm_ca_installed", lambda: False)

    result = server.proxy_set(True)

    assert result["enabled"] is True
    assert server._read_flag() is True


def test_proxy_set_restarts_the_browser_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "FLAG_PATH", str(tmp_path / "config.json"))
    kill = mock.Mock()
    monkeypatch.setattr(server, "_kill_profile_chromium", kill)
    monkeypatch.setattr(server, "_effective", lambda: None)
    monkeypatch.setattr(server, "_proxy_probe", lambda: (False, False))
    monkeypatch.setattr(server, "_mitm_ca_installed", lambda: False)

    server.proxy_set(True)
    kill.assert_called_once()


def test_proxy_set_can_skip_the_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "FLAG_PATH", str(tmp_path / "config.json"))
    kill = mock.Mock()
    monkeypatch.setattr(server, "_kill_profile_chromium", kill)
    monkeypatch.setattr(server, "_effective", lambda: None)
    monkeypatch.setattr(server, "_proxy_probe", lambda: (False, False))
    monkeypatch.setattr(server, "_mitm_ca_installed", lambda: False)

    server.proxy_set(True, restart_browser=False)
    kill.assert_not_called()


def test_kill_matches_only_the_playwright_profile_not_other_processes(monkeypatch):
    """The scope that must never widen: a loose match would also kill the
    KDE/Selkies desktop's own processes. See ADR §5.2."""
    cmdlines = {
        "/proc/111/cmdline": b"/usr/bin/chromium\x00--user-data-dir=/config/aw-playwright-profile\x00",
        "/proc/222/cmdline": b"/usr/bin/plasmashell\x00",
    }
    monkeypatch.setattr(server.glob, "glob",
                        lambda pattern: list(cmdlines) if "proc" in pattern else [])

    real_open = open

    def fake_open(path, mode="r", *a, **k):
        if path in cmdlines:
            import io
            return io.BytesIO(cmdlines[path])
        return real_open(path, mode, *a, **k)

    monkeypatch.setattr("builtins.open", fake_open)
    killed = []
    monkeypatch.setattr(server.os, "kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(server.os, "remove", lambda path: None)

    server._kill_profile_chromium()

    assert killed == [111]


def test_handle_call_proxy_status():
    with mock.patch.object(server, "proxy_status", return_value={"enabled": False}):
        payload, is_error = server.handle_call("proxy_status", {})
    assert payload == {"enabled": False}
    assert is_error is False


def test_handle_call_proxy_set_requires_enabled():
    payload, is_error = server.handle_call("proxy_set", {})
    assert is_error is True
    assert "enabled" in payload["error"]


def test_handle_call_unknown_tool_is_an_error_not_a_crash():
    payload, is_error = server.handle_call("not_a_real_tool", {})
    assert is_error is True


def test_handle_call_never_raises_even_when_the_handler_blows_up(monkeypatch):
    def boom():
        raise RuntimeError("disk full")
    monkeypatch.setattr(server, "proxy_status", boom)

    payload, is_error = server.handle_call("proxy_status", {})

    assert is_error is True
    assert "disk full" in payload["error"]


def test_respond_writes_one_ndjson_line(capsys):
    server._respond("req-1", result={"ok": True})
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert out.count("\n") == 1
    assert json.loads(out) == {"jsonrpc": "2.0", "id": "req-1", "result": {"ok": True}}
