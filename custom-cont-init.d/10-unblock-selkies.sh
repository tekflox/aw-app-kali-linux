#!/bin/bash
# Root cause (2026-09-03, bug:kali-linux-desktop-black-screen): the stock
# lscr.io/linuxserver/kali-linux:latest image's svc-selkies/run gates the
# whole service behind:
#
#   if [ ! -f '/dev/shm/audio.lock' ]; then
#     until [ -f /defaults/pid ]; do sleep .5; done
#     ...pactl load-module...
#   fi
#   exec ... selkies
#
# Nothing in the image's boot chain ever creates /defaults/pid when
# PIXELFLUX_WAYLAND=true: svc-xorg (the only plausible writer, in X11 mode)
# bails immediately with `sleep infinity`, and svc-pulseaudio starts
# pulseaudio directly with no pid-file step. The `until` loop spins forever,
# `selkies`/`labwc` never start, /config/.XDG/wayland-1 never appears, and
# KasmVNC has nothing to serve — a permanent "WebSocket disconnected" black
# screen. Confirmed live via `ps aux` showing the busy-wait loop still
# spinning hours after boot, with no selkies/labwc/pulseaudio process.
#
# Pre-creating the audio.lock sentinel skips the gate outright, so selkies
# starts immediately. Desktop audio pass-through stays unconfigured, which
# is not a regression — nothing rendered before this fix either.
set -e
mkdir -p /dev/shm
touch /dev/shm/audio.lock
