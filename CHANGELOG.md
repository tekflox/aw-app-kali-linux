# Changelog

## Unreleased

Feature: Kali becomes the workspace's default **automation browser**. This
repo now derives its own image instead of using the stock one as-is —
`container/Dockerfile` adds Chromium, a pinned `@playwright/mcp@0.0.77`, and
a pinned checkout of [`aw-mcp-gateway`](https://github.com/tekflox/aw-mcp-gateway)'s
`back/` running as a long-running s6 service on `:9200`. The workspace's
MAIN MCP Gateway federates that leaf gateway in as a `type: gateway` upstream
(new root `mcp.json`), so Kali's Playwright tools surface on every agent
session as `aw__kali__aw__playwright__browser_*` — no `docker exec` needed.
Origin: a manually-piloted, headed Chromium inside this desktop reached
Google's password prompt with zero automation-detection rejection, where
`aw-app-browser`'s headless Chromium was rejected outright; see the ADR
(Kanban `feature:kali-standalone-mcp-gateway-playwright`) for the full design
and rejected alternatives.

The leaf gateway runs `require_token: false` (new opt-in in
`aw-mcp-gateway` v0.39.0+) — reachable only from sibling containers on the
podman app network, never published, same trust posture as
`aw-app-browser`'s unauthenticated CDP on `:9223`. New `mcp_gateway_config`
Settings field overrides the leaf's upstream pool (baked default: just
`playwright`) without a rebuild.

`custom-cont-init.d/*` is unchanged by this work — the s6 service that boots
the leaf gateway is a separate, new long-running service
(`/etc/services.d/aw-mcp-gateway`, not `/custom-services.d` — this base image
has no such directory, confirmed against the live container).

Fix: `/config` ownership drift silently blocking writes (e.g. plasmashell
refusing to start with "Configuration file ... not writable"). linuxserver.io
images chown `/config` to PUID:PGID exactly once, on first boot, and never
revisit it — once this volume's ownership drifts to the wrong uid it stays
wrong forever, through every later container recreation, app update, or
workspace redeploy. Fixed by shipping
`custom-cont-init.d/00-fix-config-ownership.sh`, which re-chowns `/config` to
`abc:abc` on every boot (excluding the separate read-only `/config/repos`
mount), as a package-relative, single-file volume mounted the same way as
`10-unblock-selkies.sh` — numbered `00-` so it runs first, before anything
else in the hook dir tries to write.

Fix: permanent black screen, KasmVNC stuck on "WebSocket disconnected.
Attempting to reconnect..." — the stock image's `svc-selkies` init script
deadlocks forever waiting for `/defaults/pid`, a file nothing in the image's
boot chain ever creates when `PIXELFLUX_WAYLAND=true`, so `selkies`/`labwc`
never start. Fixed by shipping `custom-cont-init.d/10-unblock-selkies.sh`
(pre-creates `/dev/shm/audio.lock` to skip the deadlocked audio-sink gate)
as a package-relative, single-file volume mounted into the existing
`/custom-cont-init.d` hook dir — lands on every install, including a fresh
one, without depending on `$AW_APP_DATA` already having a copy of it.

## 0.3.0

Renamed. The app was briefly published as `kalix` (repo `aw-app-kalix`) — a
typo. It is now `kali-linux`, repo `tekflox/aw-app-kali-linux`, shown in the
Apps grid and its window as **Kali Linux**. The skill moved with it:
`aw-kalix` → `aw-kali-linux`.

Because the slug is the app's identity, this is a new app rather than an
upgrade: `$AW_APP_DATA` moves from `data/kalix` to `data/kali-linux`, so the
desktop's `/config` starts fresh again. The `kalix` catalog entry is retired.

## 0.1.0

Initial release — port of the `agentic-workspace` monolith's `aw-kali`
docker service (workspace app `id: "linux"`, label **Linux**) to a decoupled
Tier-2 app.

- Stock `lscr.io/linuxserver/kali-linux:latest` image, no derived build.
- Persistent `$HOME` (`$AW_APP_DATA` → `/config`) and a writable
  `/custom-cont-init.d` hook dir so packages/boot scripts survive container
  recreation without forking the image.
- This workspace's repos mounted read-only at `/config/repos` (the monolith
  mounted the whole tree read-write).
- `managed_app` window onto the KasmVNC desktop; `timezone` config knob.
- Contributes the `aw-kali-linux` skill.

Not ported: `/dev/video10` webcam passthrough + the PipeWire/V4L2 init
script, and `network_mode: container:aw-sandbox` — neither has a Tier-2
equivalent today. See README.
