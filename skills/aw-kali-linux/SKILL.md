---
name: aw-kali-linux
description: The Kali Linux app — a full KDE desktop running in the browser as a Tier-2 aw-workspace container (stock lscr.io/linuxserver/kali-linux image). Covers what is mounted where, what survives a container recreation, how to install packages or add boot hooks so they persist, the device limits (no webcam/GPU passthrough) that come from running it as an app instead of a compose service, and the app's own federated MCP tools — Playwright browser automation (`aw__kali__aw__playwright__*`) and the `kali_control` aw-app-proxy routing toggle (`aw__kali__aw__kali_control__*`). Load this whenever a task involves the Kali Linux desktop window, piloting its automation browser, the proxy toggle, or when something in that desktop was lost after an update.
---

# Kali Linux — the browser desktop

This app is the decoupled-app port of the monolith's `aw-kali` docker service
(`agentic-workspace` → `src/config/aw.json`, `docker_services[].name ==
"aw-kali"`, surfaced as the workspace app `id: "linux"`, label **Linux**).
Same upstream image, no fork: `lscr.io/linuxserver/kali-linux:latest`.

Open it from the Apps grid, or at its own subdomain
`https://kali-linux.app.<slug>.workspace.<apex>`. It is a KasmVNC web desktop —
no VNC client, no extra port.

## The filesystem map

| Path in the desktop | Backed by | Survives recreate? |
|---|---|---|
| `/config` (the `abc` user's `$HOME`) | `$AW_APP_DATA` | **yes** |
| `/config/repos` | `$AW_WORKSPACE_REPOS`, **read-only** | yes (it's the live tree) |
| `/custom-cont-init.d` | `$AW_APP_DATA/custom-cont-init.d` | **yes** |
| everything else (`/usr`, `/etc`, `/opt`, …) | container writable layer | **no** |

That last row is the one that bites. `apt-get install <x>` writes to `/usr`
and `/var`, so it is **gone** on the next app update, workspace redeploy, or
`aw-workspace-cli restart kali-linux` that recreates the container.

To make a package stick, install it from a boot hook instead:

```bash
# from inside the desktop's terminal
cat > /config/custom-cont-init.d/20-my-tools.sh <<'EOF'
#!/bin/bash
set -e
dpkg -l my-tool 2>/dev/null | grep -q '^ii' && exit 0   # idempotent: warm container
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends my-tool
EOF
chmod +x /config/custom-cont-init.d/20-my-tools.sh
```

…except the hook dir is mounted at `/custom-cont-init.d`, not under
`/config` — write it there (`/custom-cont-init.d/20-my-tools.sh`). Scripts
run **as root, before the KDE session starts**, in filename order. Make them
idempotent: they re-run on every boot, including warm ones.

> Do **not** express this as a KDE autostart `.desktop` entry. The monolith
> tried that and it crash-looped `plasmashell` on any fresh container where
> the binary wasn't installed yet — which is exactly the case the autostart
> was there to fix.

Two more package-relative files land in this same directory on every boot,
both bind-mounted read-only straight from the app package (not from
`$AW_APP_DATA`): `custom-cont-init.d/00-fix-config-ownership.sh`, which
re-chowns `/config` to `abc:abc` (excluding `/config/repos`) — see "Known
issues" below — and `custom-cont-init.d/10-unblock-selkies.sh`, which
pre-creates `/dev/shm/audio.lock` to skip a deadlock in the stock image's own
`svc-selkies` init script. The `00-`/`10-` numbering is deliberate: ownership
has to be fixed before anything else in the hook dir tries to write.
Package-relative volumes ship with every install of the repo's own version,
so both fixes reach a brand-new install too, without depending on
`$AW_APP_DATA` already having a copy.

## Known issues

**`/config` ownership drift blocking writes** (e.g. plasmashell refusing to
start with "Configuration file ... not writable. Please contact your system
administrator.") (kali-linux:config-ownership-drift-blocks-writes,
root-caused 2026-09-10) — linuxserver.io images chown `/config` to
PUID:PGID exactly once, on first boot, guarded by an internal sentinel, and
never revisit it on later boots. If this volume's ownership ever drifts to
the wrong uid (confirmed once: 2890 of 2897 files under uid 1001, not
`abc`/1000), it stays wrong forever, through every later container
recreation, app update, or workspace redeploy — until something re-chowns
it. Fixed as of the `00-fix-config-ownership.sh` hook above, which does that
on every boot. If this ever regresses, `docker exec -u root kali-linux ls -la
/config` and compare owners against `id abc` inside the container.

**Black screen, KasmVNC stuck on "WebSocket disconnected. Attempting to
reconnect..."** (bug:kali-linux-desktop-black-screen, root-caused
2026-09-03) — the stock image's `svc-selkies/run` gates the whole service
behind `until [ -f /defaults/pid ]; do sleep .5; done`, and nothing in the
image's boot chain ever creates `/defaults/pid` when `PIXELFLUX_WAYLAND=true`
(`svc-xorg`, the only plausible writer, bails immediately in Wayland mode).
The loop spins forever, `selkies`/`labwc` never start, `/config/.XDG/wayland-1`
never appears, and KasmVNC has nothing to serve. Fixed as of the
`10-unblock-selkies.sh` hook above — if this ever regresses (e.g. a
linuxserver image update reworks the gate), check `docker logs kali-linux`
for the boot log stalling at `[svc-de] Wayland mode: Waiting for socket at
/config/.XDG/wayland-1...`, then `ps aux` inside the container for a stuck
`sleep .5`/`sleep 0.5` pair with no `selkies`/`labwc` process.

## What did NOT come across from the monolith

Three things in `aw.json`'s `aw-kali` service have no Tier-2 equivalent
today. Don't spend time looking for the manifest key — it isn't there.

1. **Webcam / V4L2 passthrough.** The monolith passed
   `devices: ["/dev/video10:/dev/video10"]` and `group_add: ["video"]`, and
   shipped `tools/aw-kali/custom-cont-init.d/10-pipewire.sh` to install
   PipeWire + `pipewire-v4l2` and start them once `plasmashell` was up.
   `_parse_run_flags` in aw-workspace `src/apps/containers.py` accepts
   **only** `--shm-size` and raises on anything else, and the manifest has no
   `devices`/`group_add` fields — so there is no camera here. The
   PipeWire script is not shipped for the same reason (it exists to feed
   `/dev/video10`); if device passthrough ever lands, port it from the
   monolith path above rather than rewriting it.

   Related host-side gotcha, still true: `/dev/video10` only exists if
   `v4l2loopback-dkms` + matching `linux-headers-$(uname -r)` are installed
   and the module is loaded **on the bare-metal host**. A container that
   sits in `Created` with no logs and an error about "no such file or
   directory" for a `/dev/*` device is a missing kernel module, not a broken
   image.

2. **`network_mode: container:aw-sandbox`.** In the monolith the desktop
   shared the sandbox's network namespace, so `localhost:<port>` reached
   every other AW service. Tier-2 apps attach to the workspace podman network
   instead and are reachable by name. Dial sibling services by container
   name, not `localhost`.

3. **The workspace mounted read-write.** The monolith bound
   `.:/home/abc/agentic-workspace:cached` — the whole live tree, writable
   from a GUI session. This app mounts `$AW_WORKSPACE_REPOS` at `/config/repos`
   **read-only** on purpose. Anything you need to write, write under
   `/config`; to hand a file to the rest of the workspace, use the shared
   scratch dir conventions (`.tmp/`) from a workspace-side session instead.

## MCP tools

This app runs its own standalone MCP gateway (container port `:9200`,
`require_token: false` — reachable only from sibling containers on the
podman app network, never published) that the workspace's main gateway
federates in. Every tool below surfaces on any agent session as
`aw__kali__aw__<leaf>__<tool>` — no `docker exec` needed, same pattern as
every other federated leaf gateway in this workspace. Two upstreams,
declared in `container/defaults/gateway-mcp.json` (overridable per-install
via the `mcp_gateway_config` Settings field, no rebuild needed):

### `playwright` — browser automation (`aw__kali__aw__playwright__*`)

Pinned `@playwright/mcp@0.0.77`, driving **this container's own headed
Chromium** (`/usr/local/bin/chromium-aw`, profile
`/config/aw-playwright-profile`) inside the live KDE desktop — not a hidden
headless browser. This is the workspace's default automation browser for a
reason: a real, visible Chromium inside a real desktop session reaches
Google's password prompt with zero automation-detection rejection, where
`aw-app-browser`'s headless Chromium gets rejected outright.

| Tool | What it does |
|---|---|
| `browser_navigate` | Go to a URL |
| `browser_navigate_back` | Back button |
| `browser_snapshot` | Accessibility-tree snapshot of the page — the usual way to "see" it before acting |
| `browser_click` | Click an element |
| `browser_hover` | Hover an element |
| `browser_drag` / `browser_drop` | Drag-and-drop |
| `browser_type` | Type into a focused element |
| `browser_press_key` | Send a single key |
| `browser_select_option` | Pick from a `<select>` |
| `browser_fill_form` | Fill multiple fields in one call |
| `browser_file_upload` | Attach a file to a file input |
| `browser_handle_dialog` | Accept/dismiss a JS `alert`/`confirm`/`prompt` |
| `browser_tabs` | List / open / close / switch tabs |
| `browser_resize` | Resize the browser window/viewport |
| `browser_wait_for` | Wait for text, a time delay, or an element |
| `browser_take_screenshot` | PNG/JPEG screenshot |
| `browser_console_messages` | Read the JS console |
| `browser_network_requests` / `browser_network_request` | List / inspect network traffic |
| `browser_evaluate` | Run JS in the page |
| `browser_run_code_unsafe` | Run arbitrary JS/Node with no sandboxing — use sparingly |
| `browser_close` | Close the browser |

### `kali_control` — aw-app-proxy routing toggle (`aw__kali__aw__kali_control__*`)

A tiny stdlib-only stdio server baked into the image
(`container/kali-control/server.py`), exposing exactly two tools that
control whether the automation Chromium above is routed through this
workspace's **aw-app-proxy** — same mechanism `aw-app-browser` already
uses, and the thing that also lets the aw-sync browser extension's cookie
push reach this container's Chromium (mirrored on `:9223` via its own
`aw-cdp-proxy`, same pattern as `aw-app-browser`'s CDP proxy).

| Tool | What it does |
|---|---|
| `proxy_set(enabled, restart_browser=true)` | Flip the flag, persisted to `/config/aw-proxy/config.json` (survives container restart). By default also SIGTERMs the profile-matched Chromium (matched strictly on its `--user-data-dir`, never the KDE desktop's own browser) so `@playwright/mcp` relaunches it lazily on the next tool call with the new setting applied — no gateway reload, no container recreate. |
| `proxy_status()` | `{enabled, effective, pending_browser_restart, proxy_reachable, mitm_ca, proxy_url}` — the persisted flag vs. what a currently-running browser actually has applied, whether aw-app-proxy answers at all, and MITM CA trust state (`installed` / `available` / `absent`). |

The Settings UI has the same switch (the `proxy` region in
`windows/settings.json`), wired through the core
`GET|POST /api/apps/kali-linux/leaf-tool/{tool}` bridge — it calls the exact
same two tools, not a separate mechanism, so flipping it from an agent
session and from the UI stay in sync.

## Config

One knob, `timezone` (IANA, default `America/New_York`), plus the
framework's own `auto_start`. Both are in the app's Settings gear. Saving
either **recreates** the container — the desktop session is lost, `/config`
is not.

## Resources

Declared at 2 CPU / 4 GB with `--shm-size=1g`. A KDE session with a browser
open will use it. If Plasma is dying under memory pressure, raise `mem_mb`
in the manifest rather than trimming the desktop.
