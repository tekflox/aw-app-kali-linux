# Kali Linux desktop + Chromium automation target + standalone MCP gateway.
#
# Base: stock lscr.io/linuxserver/kali-linux:latest (KDE/KasmVNC/Selkies
# desktop, s6-overlay v3). This derived image adds Chromium (a headed,
# manually-piloted Chromium in this desktop reached Google's password prompt
# with zero automation-detection rejection, where aw-app-browser's headless
# Chromium was rejected on 9/9 conditions — see the ADR this image
# implements), a pinned Playwright MCP, and a pinned checkout of
# aw-mcp-gateway's back/ running as a long-running s6 service, so the
# workspace's MAIN gateway can federate this container's tools in as a
# scanned `type: gateway` upstream (see the repo-root mcp.json).
#
# Published by .github/workflows/build.yml as ghcr.io/tekflox/aw-app-kali-linux.
FROM lscr.io/linuxserver/kali-linux:latest

# Pin the exact aw-mcp-gateway release this image's s6 service runs. Bump
# this (and this image's own aw-app.json version) whenever aw-mcp-gateway
# cuts a release this image should pick up — never clone without --branch,
# the upstream default branch moves on every merge from elsewhere in this
# workspace.
ARG AW_MCP_GATEWAY_REF=v0.39.0

# chromium/chromium-driver: the automation target (apt install confirmed
# functional in the ADR's live manual test). nodejs: runs @playwright/mcp —
# Kali's `nodejs` package is the NodeSource build, which bundles its own npm
# and Conflicts: the separate Debian `npm` package (verified by a failed
# local build: "nodejs Conflicts npm" aborts apt-get outright) — install
# nodejs alone. python3/venv/pip: runs aw-mcp-gateway's back/. git: one-shot
# clone below. curl: chromium-aw fetches the MITM CA/SPKI from aw-app-proxy
# per launch. libnss3-tools: certutil, for the same wrapper's NSS trust-store
# install — do not assume the Kali base has it (aw-app-browser's own
# Dockerfile installs it explicitly for the identical reason).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      chromium \
      chromium-driver \
      nodejs \
      python3 \
      python3-venv \
      python3-pip \
      git \
      curl \
      libnss3-tools \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

# Pre-fetch @playwright/mcp globally so the first boot needs no network —
# same pin as aw-app-browser/mcp.json, kept in lockstep deliberately.
# HOME=/root for this step only: the base image sets ENV HOME=/config
# globally (so the ONE persistent volume doubles as every tool's dotfile
# home), which at BUILD time means npm's cache would otherwise get baked
# into the image's own /config/.npm, owned by build-time root — found live:
# EACCES at runtime, from a container started with no $AW_APP_DATA volume
# mounted over /config, hitting exactly that baked-in root-owned cache.
RUN HOME=/root npm install -g @playwright/mcp@0.0.77

# Pinned clone of the gateway this container's own standalone MCP gateway
# runs (public repo, no token needed) + its own venv, kept off the system
# python the base image's own init scripts use.
RUN git clone --branch "${AW_MCP_GATEWAY_REF}" --depth 1 \
      https://github.com/tekflox/aw-mcp-gateway.git /opt/aw-mcp-gateway && \
    python3 -m venv /opt/aw-mcp-gateway/.venv && \
    /opt/aw-mcp-gateway/.venv/bin/pip install --no-cache-dir \
      -r /opt/aw-mcp-gateway/back/requirements.txt

# s6-overlay v3's OWN generic "legacy service" conversion: an executable at
# /etc/services.d/<name>/run becomes a supervised, auto-restarted longrun —
# verified directly against this exact base image (no "custom-services"
# string, and no /custom-services.d scanner, exist anywhere in it; only the
# built-in /etc/services.d support shipped by s6-overlay-3.2.1.0 itself is
# present here). LSIO's /custom-services.d convenience wrapper, which some
# OTHER linuxserver baseimages add on top of this, is NOT one of them — do
# not assume it from other LSIO images.
COPY --chmod=755 services/aw-mcp-gateway/run /etc/services.d/aw-mcp-gateway/run
COPY defaults/gateway-mcp.json /defaults/aw-gateway-mcp.json

# cdp-proxy: a second s6 longrun, same mechanism as aw-mcp-gateway above —
# exposes this container's own Chromium's CDP on :9223 (HTTP-aware Host
# rewrite, same pattern aw-app-browser already uses) so aw-app-proxy's
# multi-target cookie push can reach it, and so this container is pilotable
# over CDP by name like aw-app-browser already is.
COPY --chmod=755 services/aw-cdp-proxy/run /etc/services.d/aw-cdp-proxy/run
COPY cdp-proxy/cdp_proxy.py /opt/aw-kali/cdp_proxy.py

# kali_control: the second upstream of this container's own gateway (see
# gateway-mcp.json above) — stdlib-only, so it runs fine on the system
# python3 rather than needing the gateway's own pinned venv.
COPY --chmod=755 kali-control/server.py /opt/kali-control/server.py

# chromium-aw: what gateway-mcp.json's playwright entry points
# --executable-path at instead of /usr/bin/chromium directly — see the
# wrapper's own header for why.
COPY --chmod=755 chromium-aw /usr/local/bin/chromium-aw

# Documentation only on a user-defined podman network (does not publish or
# restrict anything) — the workspace's main gateway reaches this by
# container name, never through a host-published port.
EXPOSE 9200 9223
