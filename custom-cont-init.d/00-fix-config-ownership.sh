#!/bin/bash
# THIS IS A FALLBACK, NOT THE FIX. Read the next paragraph before treating a
# green boot here as evidence the problem is solved.
#
# Real root cause (2026-09-10, proven on
# kali-linux:config-ownership-drift-root-cause-review): on every workspace
# boot/redeploy, the layer that creates the workspace container recursively
# chowns the ENTIRE /opt/aw-workspace bind mount to the workspace's own host
# uid. $AW_APP_DATA lives at <AW_WORKSPACE_HOME>/data/<app_id>, i.e. INSIDE
# that mount, so every Tier-2 app's bind-mounted /config is swept along with
# it. Proven by ctime: on 2026-09-10 at 08:04:36–42 the tracked source files,
# .aw-workspace/secrets and every app data dir all took the same ctime while
# keeping mtimes from weeks earlier — ownership rewritten, contents untouched.
# The chown itself lives outside this repo and is tracked separately on
# core:workspace-redeploy-chowns-app-data-dirs.
#
# An earlier version of this header claimed the opposite — that "whatever
# populated this volume the first time did it under the wrong uid, and
# nothing since has ever corrected it — including every later container
# recreation, app update, or workspace redeploy." That was wrong, and wrong
# in the direction that matters: the redeploy is not innocent, it is the
# thing that re-applies the drift. The consequence is that this hook cannot
# be durable on its own. It repairs ownership at boot; anything the outer
# chown does WHILE the container stays up survives until the next restart,
# and that window is exactly the "not writable" failure this was meant to
# end.
#
# The actual fix is to stop the two uids from differing at all: PUID/PGID are
# now DERIVED from the real owner of $AW_APP_DATA (`"PUID": "${data.uid}"` in
# aw-app.json, resolved by core's containers.expand_env / app_data_owner)
# instead of hardcoded to 1000. The outer chown then becomes a no-op — it
# chowns the tree to the uid abc already is — and nothing needs healing.
#
# This script stays anyway, deliberately, for the two cases derivation does
# not cover: a workspace still running a core build without the ${data.uid}
# placeholder, and an already-populated /config whose contents were left
# mid-transition. Changing PUID on a populated data dir is a one-way door for
# that dir's existing contents, so the fallback has to outlive the transition.
#
# Symptom it was first found by: 2890 of 2897 files/dirs under /config owned
# by uid 1001 rather than abc. /config/.config/plasmashellrc is mode 600
# (owner-only), so abc had zero permission on it and plasmashell refused to
# start — "Configuration file ... not writable. Please contact your system
# administrator." — a black/broken desktop. The same class of failure was
# found live and unnoticed on aw-app-blender (367 files, PulseAudio cookie
# and mesa shader cache unreadable), which has no hook of its own.
#
# Relevant upstream behaviour: linuxserver.io images chown /config to
# PUID:PGID exactly once, on first boot, guarded by an internal sentinel, and
# never revisit it on later boots (their own init skips the expensive
# recursive chown on every restart by design). So the image will not repair
# this by itself. Re-chowning /config on every boot is cheap enough here
# (this app's own home directory, not a multi-TB data store). Numbered "00-"
# so it runs BEFORE 10-unblock-selkies.sh (plain lexical loop over this dir)
# — ownership needs to be correct before anything else in the hook dir tries
# to write.
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
