# Changelog

## Unreleased

Feature: this container's own Chromium now receives cookies synced via the
aw-sync browser extension, not just `aw-app-browser`'s. `chromium-aw` adds
`--remote-debugging-port=9222` to every launch (unconditional — works with
the proxy toggle off, and alongside `@playwright/mcp`'s own
`--remote-debugging-pipe`, verified live), and a second s6 longrun,
`aw-cdp-proxy` (`container/cdp-proxy/cdp_proxy.py`, a copy of
`aw-app-browser`'s own CDP proxy), exposes it on `:9223` by container name
— same pattern `aw-app-browser` already uses, so `aw-app-proxy`'s cookie
push can reach it as a second target alongside the interactive browser.
Closes the lazy-launch gap (`@playwright/mcp` only starts Chromium on its
first tool call): `chromium-aw` also backgrounds a one-shot that waits for
this launch's CDP to come up, then triggers `aw-app-proxy`'s
`POST /restore-cookies` to re-push every persisted cookie immediately,
instead of waiting up to 15s for the proxy's own reconcile tick. Requires
`aw-app-proxy` 0.16.0+ (multi-target cookie push); see
`.tmp/kali-cookie-sync-design/ADR-kali-cookie-sync.md` for the full design
and rejected alternatives.

Feature: Kali Settings gains a toggle to route the automation Chromium
through **aw-app-proxy**, same as `aw-app-browser` already does. A new
stdlib-only stdio MCP server, `kali_control`, joins the leaf gateway as a
second upstream alongside `playwright` (`aw__kali__aw__kali_control__proxy_*`)
exposing `proxy_set`/`proxy_status`; state persists to
`/config/aw-proxy/config.json` (survives container restart). A new Chromium
wrapper, `/usr/local/bin/chromium-aw`, is what `@playwright/mcp`'s
`--executable-path` now points at — it reads the flag at every launch and, if
enabled, injects the proxy + MITM-trust flags, mirroring
`aw-app-browser/container/entrypoint-lite.sh`. Flipping the toggle kills the
running automation Chromium (matched strictly on
`--user-data-dir=/config/aw-playwright-profile`, never the KDE desktop);
`@playwright/mcp` relaunches it lazily on the next tool call — no gateway
reload, no container recreate. The Settings UI reaches these tools directly
via `aw-workspace` core's new `GET|POST /api/apps/{slug}/leaf-tool/{tool}`
bridge and a new `toggle` declarative widget, rather than the usual
`config_schema`+save flow — an offline container shows an explanatory
message instead of a dead switch. Works against the installed aw-app-proxy
0.12.1 (plain CONNECT splice, no MITM yet); see
`.tmp/kali-proxy-toggle-design/ADR-kali-proxy-toggle.md` for the full design
and rejected alternatives.

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
