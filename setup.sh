#!/usr/bin/env bash
# Native macOS/Linux setup. Safe to rerun; existing tools and model are reused.
set -euo pipefail
SK=$(cd "$(dirname "$0")" && pwd)
CACHE="${CLAUDE_SHORTS_CACHE:-$HOME/.cache/claude-shorts}"
VENV="$CACHE/venv"
export CLAUDE_SHORTS_CACHE="$CACHE"
export PATH="$CACHE/bin:$PATH"
OS=$(uname -s)
case "$OS" in Darwin|Linux) ;; *) echo "Use setup.ps1 on Windows."; exit 1 ;; esac

# Find an existing Homebrew even in a Claude session with an old PATH.
if ! command -v brew >/dev/null; then
  for brew_path in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
    if [ -x "$brew_path" ]; then eval "$("$brew_path" shellenv)"; break; fi
  done
fi
if [ "$OS" = Darwin ] && ! command -v brew >/dev/null; then
  echo "Installing Homebrew automatically (macOS may ask for your password)..."
  installer=$(mktemp)
  curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$installer"
  /bin/bash "$installer"
  rm -f "$installer"
  for brew_path in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -x "$brew_path" ]; then eval "$("$brew_path" shellenv)"; break; fi
  done
fi

if command -v brew >/dev/null; then
  for pkg in ffmpeg whisper-cpp yt-dlp cairo python; do
    brew list "$pkg" >/dev/null 2>&1 || brew install "$pkg"
  done
  PYTHON="$(brew --prefix python)/bin/python3"
else
  # Linux package installation is automated; sudo may request the user's password.
  SUDO=()
  if [ "$(id -u)" != 0 ]; then
    command -v sudo >/dev/null || { echo "Package installation requires sudo or a root session."; exit 1; }
    SUDO=(sudo)
  fi
  if command -v apt-get >/dev/null; then
    "${SUDO[@]}" apt-get update
    "${SUDO[@]}" apt-get install -y ffmpeg libcairo2 python3 python3-venv python3-pip cmake build-essential git ca-certificates
  elif command -v dnf >/dev/null; then
    "${SUDO[@]}" dnf install -y cairo python3 python3-pip cmake gcc-c++ make git ca-certificates
    # Fedora's ffmpeg-free omits libx264. Enable RPM Fusion Free for the full build.
    if ! command -v ffmpeg >/dev/null || ! ffmpeg -hide_banner -encoders 2>/dev/null | grep libx264 >/dev/null; then
      if [ -f /etc/fedora-release ]; then
        "${SUDO[@]}" dnf install -y "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm"
      fi
      "${SUDO[@]}" dnf install -y ffmpeg --allowerasing
    fi
  elif command -v pacman >/dev/null; then
    "${SUDO[@]}" pacman -S --needed --noconfirm ffmpeg cairo python python-pip cmake base-devel git ca-certificates
  else
    echo "Supported Linux package managers: Homebrew, apt, dnf, pacman."; exit 1
  fi
  PYTHON=$(command -v python3)
fi

mkdir -p "$CACHE/bin"
if ! command -v whisper-cli >/dev/null; then
  # Use a stable source release, with static libraries so the copied CLI is standalone.
  command -v cmake >/dev/null || brew install cmake
  command -v git >/dev/null || brew install git
  SRC="$CACHE/whisper.cpp"
  if [ ! -d "$SRC/.git" ]; then
    git clone --depth 1 --branch v1.9.2 https://github.com/ggml-org/whisper.cpp.git "$SRC"
  fi
  cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DWHISPER_BUILD_TESTS=OFF
  cmake --build "$SRC/build" --config Release --target whisper-cli -j 2
  cp "$SRC/build/bin/whisper-cli" "$CACHE/bin/whisper-cli"
fi
if [ ! -x "$VENV/bin/python" ]; then "$PYTHON" -m venv "$VENV"; fi
# Also repairs an existing, partly installed venv; never changes system Python packages.
"$VENV/bin/python" -m pip install --quiet pillow cairosvg yt-dlp
"$VENV/bin/python" "$SK/scripts/check_setup.py"
"$VENV/bin/python" -c 'import sys; sys.path.insert(0, sys.argv[1]); from platform_tools import download_model; download_model()' "$SK/scripts"
mkdir -p "$HOME/.config/claude-shorts/fonts"
echo "claude-shorts is ready. In Claude Code, type /claude-shorts"
