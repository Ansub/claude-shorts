#!/bin/zsh
# Pull the audio of a YouTube link as MP3. Updates yt-dlp first: YouTube breaks old versions often
# (a 3-month-old build failed with 403 / "page needs to be reloaded" on 2026-10-07; the update fixed it).
# Usage: get_music.sh <url> <out_dir>
set -e
url="$1"; out="$2"; mkdir -p "$out"
if command -v brew >/dev/null && brew list yt-dlp >/dev/null 2>&1; then brew upgrade yt-dlp >/dev/null 2>&1 || true
else yt-dlp -U >/dev/null 2>&1 || true; fi
yt-dlp --no-playlist -x --audio-format mp3 --audio-quality 0 -o "$out/%(title)s.%(ext)s" --print after_move:filepath "$url"
