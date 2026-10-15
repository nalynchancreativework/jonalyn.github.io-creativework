#!/usr/bin/env bash
# One-time setup per session. Safe to re-run.
# Creates a Python venv with the transcription + image tools and fetches the
# colour emoji font used for word-triggered emoji stickers.
set -euo pipefail

CACHE="${REEL_CACHE:-$HOME/.cache/reel-edit}"
VENV="$CACHE/venv"
mkdir -p "$CACHE"

command -v ffmpeg >/dev/null || { echo "ffmpeg is missing (apt-get install -y ffmpeg)"; exit 1; }

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip >/dev/null
"$VENV/bin/pip" install -q faster-whisper pocketsphinx pillow

# Noto Color Emoji (CBDT build - Pillow can render this one, the Google Fonts
# COLRv1 build renders blank).
EMOJI="$CACHE/NotoColorEmoji.ttf"
if [ ! -s "$EMOJI" ]; then
  if [ -s /usr/share/fonts/truetype/noto/NotoColorEmoji.ttf ]; then
    cp /usr/share/fonts/truetype/noto/NotoColorEmoji.ttf "$EMOJI"
  else
    tmp=$(mktemp -d)
    ( cd "$tmp" && (apt-get download fonts-noto-color-emoji >/dev/null 2>&1 \
        || (apt-get update -qq >/dev/null 2>&1 && apt-get download fonts-noto-color-emoji >/dev/null 2>&1)) ) || true
    deb=$(ls "$tmp"/*.deb 2>/dev/null | head -1 || true)
    if [ -n "$deb" ]; then
      dpkg-deb -x "$deb" "$tmp/x"
      cp "$(find "$tmp/x" -name NotoColorEmoji.ttf | head -1)" "$EMOJI"
    else
      echo "WARNING: could not fetch the colour emoji font - emoji overlays will fail; image overlays still work."
    fi
    rm -rf "$tmp"
  fi
fi

# Can the better transcriber download its model? (needs huggingface.co)
if curl -sS -o /dev/null -m 10 https://huggingface.co 2>/dev/null; then
  echo "TRANSCRIBER: whisper (huggingface.co reachable)"
else
  echo "TRANSCRIBER: pocketsphinx fallback (huggingface.co blocked) - pass --script for accurate timing"
fi
echo "READY: $VENV/bin/python"
