#!/bin/bash
# Root cause (2026-09-10, kali-linux:config-ownership-drift-blocks-writes):
# 2890 of 2897 files/dirs under /config (the $AW_APP_DATA bind mount) were
# found owned by uid 1001, not abc (uid 1000 — this app's own PUID=1000/
# PGID=1000 env). /config/.config/plasmashellrc specifically is mode 600
# (owner-only), so abc had zero permission on it and plasmashell refused to
# start: "Configuration file ... not writable. Please contact your system
# administrator." — a black/broken desktop.
#
# linuxserver.io images chown /config to PUID:PGID exactly once, on first
# boot, guarded by an internal sentinel, and never revisit it on later boots
# (their own init skips the expensive recursive chown on every restart by
# design). Whatever populated this volume the first time did it under the
# wrong uid, and nothing since has ever corrected it — including every later
# container recreation, app update, or workspace redeploy. Confirmed live via
# `docker exec -u root aw-app-kali-linux chown -R abc:abc /config`, which
# unblocked plasmashell immediately.
#
# Re-chowning /config on every boot is cheap enough here (this app's own
# home directory, not a multi-TB data store) and makes the fix self-healing
# instead of a one-time unblock. Numbered "00-" so it runs BEFORE
# 10-unblock-selkies.sh (plain lexical loop over this dir) — ownership needs
# to be correct before anything else in the hook dir tries to write.
#
# /config/repos is EXCLUDED on purpose: it's a separate read-only bind mount
# ($AW_WORKSPACE_REPOS, see aw-app.json), and a naive `chown -R /config`
# would hit it and fail loudly on every file with "Read-only file system" —
# benign, but noisy on every single boot, and pointless since it's a
# different, already-correct mount.  Skipping it outright (rather than
# touching it and tolerating the errors) keeps this script's exit code 0 on
# a normal boot.
set -e
find /config -mindepth 1 -maxdepth 1 -not -name repos -exec chown -R abc:abc {} +
