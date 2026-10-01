# aw-app-kali-linux

A full **Kali Linux KDE desktop in the browser**, packaged as a decoupled
aw-workspace app. Port of the `agentic-workspace` monolith's `aw-kali` docker
service (`src/config/aw.json` → `docker_services[] name: "aw-kali"`, exposed
in the UI as the workspace app `id: "linux"`, label **Linux**).

Kali became the workspace's default **automation browser** (not just a
desktop): this repo now derives its own image, `FROM
lscr.io/linuxserver/kali-linux:latest` plus Chromium, a pinned Playwright
MCP, and a pinned checkout of [`aw-mcp-gateway`](https://github.com/tekflox/aw-mcp-gateway)'s
`back/` running as a long-running s6 service on `:9200` — the workspace's
MAIN MCP Gateway federates it in as a `type: gateway` upstream (root
`mcp.json`), so Kali's Playwright tools show up on every agent session as
`aw__kali__playwright__browser_*`, with no `docker exec` needed. See
`docs/architecture/aw-app-kali-linux.md` and the ADR this implements
(Kanban `feature:kali-standalone-mcp-gateway-playwright`) for the full
design and the alternatives rejected.

## Layout

```
aw-app.json                   the whole app — Tier-2 container manifest
mcp.json                      registers this app's OWN gateway as a federated upstream
container/Dockerfile          the derived image (Chromium + Playwright MCP + aw-mcp-gateway)
container/services/           s6 long-running service that boots the leaf gateway
container/defaults/           baked default upstream pool for the leaf gateway (playwright)
custom-cont-init.d/           one-shot root hooks (UNCHANGED by the gateway work above)
skills/aw-kali-linux/         SKILL.md contributed to the workspace skills index
schemas/                      manifest JSON Schema (mirrored from aw-app-template)
tests/
.github/workflows/            build (image) + release (→ aw-marketplace catalog sync)
```

## Manifest at a glance

| | |
|---|---|
| tier | `container` (Tier-2) |
| image | `ghcr.io/tekflox/aw-app-kali-linux:latest` (derived — see Dockerfile) |
| port | 3500 (`CUSTOM_PORT`) — the desktop; the leaf gateway's `:9200` is unpublished, reached by container name only |
| run flags | `--shm-size=1g` |
| resources | 2 CPU / 4096 MB |
| permissions | `containers:manage`, `fs:workspace-data` |
| window | `managed_app` / `kind: web` → the KasmVNC desktop at `/` |
| settings | `mcp_gateway_config` — override the leaf gateway's upstream pool (JSON) |

### Volumes

| source | target | mode |
|---|---|---|
| `$AW_APP_DATA` | `/config` | rw |
| `$AW_APP_DATA/custom-cont-init.d` | `/custom-cont-init.d` | rw |
| `$AW_WORKSPACE_REPOS` | `/config/repos` | **ro** |

`/config` is the desktop's `$HOME` in every linuxserver image, so persisting
it is what makes the machine feel like a machine across container recreates.
The init-hook bind is what keeps the *stock* image extensible: drop an
executable script in there and it runs as root before KDE starts — that is
how the monolith delivered its PipeWire bridge, and it means a user can
install durable tooling without this repo ever building an image.

## Known gaps vs the monolith

- **No webcam / device passthrough.** The monolith passed
  `--device=/dev/video10` + `group_add: video`. aw-workspace's
  `_parse_run_flags` (`src/apps/containers.py`) accepts only `--shm-size`,
  and the manifest has no `devices` field — so the monolith's
  `tools/aw-kali/custom-cont-init.d/10-pipewire.sh` is deliberately not
  ported (it exists to feed `/dev/video10`).
- **No shared network namespace.** The monolith ran
  `network_mode: container:aw-sandbox`; Tier-2 apps join the workspace podman
  network and are reached by container name.
- **The workspace tree is read-only here**, where the monolith bound it
  read-write at `/home/abc/agentic-workspace`.

Details and the workarounds are in [`skills/aw-kali-linux/SKILL.md`](skills/aw-kali-linux/SKILL.md).

## Install

Through the marketplace, once the catalog serves this version:

```bash
aw-workspace-cli marketplace install kali-linux
```

Sideloading (`POST /api/apps/install {package_dir}`) works for a first look
but the reconciler converges to the catalog and will revert it — see the
`aw-create-app` skill, §10.

## Validate

```bash
python tests/validate_manifest.py
```
