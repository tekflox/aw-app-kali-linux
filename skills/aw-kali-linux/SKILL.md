---
name: aw-kali-linux
description: The Kali Linux app — a full KDE desktop running in the browser as a Tier-2 aw-workspace container (stock lscr.io/linuxserver/kali-linux image). Covers what is mounted where, what survives a container recreation, how to install packages or add boot hooks so they persist, and the device limits (no webcam/GPU passthrough) that come from running it as an app instead of a compose service. Load this whenever a task involves the Kali Linux desktop window, or when something in that desktop was lost after an update.
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

## Config

One knob, `timezone` (IANA, default `America/New_York`), plus the
framework's own `auto_start`. Both are in the app's Settings gear. Saving
either **recreates** the container — the desktop session is lost, `/config`
is not.

## Resources

Declared at 2 CPU / 4 GB with `--shm-size=1g`. A KDE session with a browser
open will use it. If Plasma is dying under memory pressure, raise `mem_mb`
in the manifest rather than trimming the desktop.
