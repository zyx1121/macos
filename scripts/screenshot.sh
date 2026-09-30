#!/usr/bin/env bash
# screenshot — macOS screen / window / region capture via screencapture(1).
# Default output is /tmp/screenshot.png so the agent can Read() it immediately.
set -euo pipefail

OUT="/tmp/screenshot.png"
MODE="screen"
REGION=""

usage() {
    cat <<EOF
screenshot — macOS screen capture (wraps screencapture)

Usage:
  scripts/screenshot.sh [path]                       full screen → path (default /tmp/screenshot.png)
  scripts/screenshot.sh --area [path]                interactive: drag to select a region
  scripts/screenshot.sh --window [path]              interactive: click a window to capture
  scripts/screenshot.sh --region x,y,w,h [path]      programmatic region capture (no UI)
  scripts/screenshot.sh --clipboard                  capture to clipboard, no file
  scripts/screenshot.sh -h | --help

Examples:
  scripts/screenshot.sh                              # quick full-screen snapshot
  scripts/screenshot.sh ~/Desktop/now.png            # save elsewhere
  scripts/screenshot.sh --area /tmp/region.png       # let the user drag a selection
  scripts/screenshot.sh --region 0,0,1920,1080       # top-left 1920x1080 patch
  scripts/screenshot.sh --clipboard                  # to clipboard, paste anywhere

The capture is always silent (-x to screencapture, no shutter sound). On file
modes, the output path is printed to stdout so the next step can pipe it into
Read, image conversion, etc.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0;;
        --area|--interactive) MODE="area"; shift;;
        --window) MODE="window"; shift;;
        --region) MODE="region"; REGION="${2:?--region needs x,y,w,h}"; shift 2;;
        --clipboard|-c) MODE="clipboard"; shift;;
        -o|--out) OUT="${2:?-o needs a path}"; shift 2;;
        --) shift; break;;
        -*) echo "screenshot: unknown flag '$1' — try --help" >&2; exit 2;;
        *) OUT="$1"; shift;;
    esac
done

case "$MODE" in
    screen)    screencapture -x "$OUT" ;;
    area)      screencapture -x -i "$OUT" ;;
    window)    screencapture -x -W "$OUT" ;;
    region)    screencapture -x -R "$REGION" "$OUT" ;;
    clipboard) screencapture -x -c ;;
esac

if [ "$MODE" = "clipboard" ]; then
    echo "captured to clipboard"
else
    echo "$OUT"
fi
