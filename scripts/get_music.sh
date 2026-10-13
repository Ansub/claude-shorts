#!/usr/bin/env bash
# Compatibility wrapper. New callers should use the venv Python and get_music.py.
set -euo pipefail
CACHE="${CLAUDE_SHORTS_CACHE:-$HOME/.cache/claude-shorts}"
exec "$CACHE/venv/bin/python" "$(dirname "$0")/get_music.py" "$@"
