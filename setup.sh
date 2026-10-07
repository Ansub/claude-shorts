#!/bin/zsh
# One-time setup for claude-shorts (macOS). Safe to run again: it skips what is already there.
# Installs: ffmpeg, whisper.cpp, yt-dlp (Homebrew) + a private Python venv with Pillow and CairoSVG,
# and downloads the Whisper large-v3 model (about 3 GB) to ~/.cache/claude-shorts/.
set -e
command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh"; exit 1; }
for pkg in ffmpeg whisper-cpp yt-dlp cairo; do
  brew list $pkg >/dev/null 2>&1 || brew install $pkg
done
VENV=~/.cache/claude-shorts/venv
if [ ! -x $VENV/bin/python ]; then
  python3 -m venv $VENV
  $VENV/bin/pip install --quiet pillow cairosvg
fi
MODEL=~/.cache/claude-shorts/ggml-large-v3.bin
if [ ! -f $MODEL ]; then
  echo "Downloading Whisper large-v3 (about 3 GB, once)..."
  curl -L --fail -o $MODEL.part https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin
  mv $MODEL.part $MODEL
fi
mkdir -p ~/.config/claude-shorts/fonts
echo "claude-shorts is ready. In Claude Code, type /claude-shorts"
