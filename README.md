# aw-app-kalix

A full **Kali Linux KDE desktop in the browser**, packaged as a decoupled
aw-workspace app. Port of the `agentic-workspace` monolith's `aw-kali` docker
service (`src/config/aw.json` → `docker_services[] name: "aw-kali"`, exposed
in the UI as the workspace app `id: "linux"`, label **Linux**).

The container is used **as-is** — stock
`lscr.io/linuxserver/kali-linux:latest`, no derived image, no build step in
this repo. Everything this app adds is manifest-level: the port, the binds,
the resource envelope and the window.

## Layout

```
aw-app.json              the whole app — Tier-2 container manifest
skills/aw-kalix/         SKILL.md contributed to the workspace skills index
schemas/                 manifest JSON Schema (mirrored from aw-app-template)
tests/validate_manifest.py
.github/workflows/       release → aw-marketplace catalog sync
```

## Manifest at a glance

| | |
|---|---|
| tier | `container` (Tier-2) |
| image | `lscr.io/linuxserver/kali-linux:latest` |
| port | 3500 (`CUSTOM_PORT`) |
| run flags | `--shm-size=1g` |
| resources | 2 CPU / 4096 MB |
| permissions | `containers:manage`, `fs:workspace-data` |
| window | `managed_app` / `kind: web` → the KasmVNC desktop at `/` |

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

Details and the workarounds are in [`skills/aw-kalix/SKILL.md`](skills/aw-kalix/SKILL.md).

## Install

Through the marketplace, once the catalog serves this version:

```bash
aw-workspace-cli marketplace install kalix
```

Sideloading (`POST /api/apps/install {package_dir}`) works for a first look
but the reconciler converges to the catalog and will revert it — see the
`aw-create-app` skill, §10.

## Validate

```bash
python tests/validate_manifest.py
```
