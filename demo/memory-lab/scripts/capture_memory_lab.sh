#!/usr/bin/env bash

set -euo pipefail

PKG="${1:-com.androidperformance.memorylab}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${2:-./captures/${TS}}"
REMOTE_HPROF="/data/local/tmp/memory_lab_${TS}.hprof"

mkdir -p "$OUT"

echo "Restarting adbd as root..."
adb root >/dev/null
adb wait-for-device

ROOT_ID="$(adb shell id | tr -d '\r')"
if [[ "$ROOT_ID" != *"uid=0"* ]]; then
  echo "adb root is not available on this device build."
  echo "This capture flow requires root adbd (userdebug/eng)."
  exit 1
fi

PID="$(adb shell pidof "$PKG" | tr -d '\r')"
if [[ -z "$PID" ]]; then
  echo "Process not found for package: $PKG"
  exit 1
fi

echo "Package: $PKG"
echo "PID: $PID"
echo "Output: $OUT"

adb shell showmap "$PID" > "$OUT/showmap.txt"

if adb shell "su -c 'cat /proc/$PID/smaps'" > "$OUT/smaps.txt" 2>/dev/null; then
  true
else
  adb shell "cat /proc/$PID/smaps" > "$OUT/smaps.txt"
fi

adb shell dumpsys meminfo -d "$PKG" > "$OUT/meminfo.txt"
adb shell dumpsys gfxinfo "$PKG" > "$OUT/gfxinfo.txt"
adb shell am dumpheap "$PKG" "$REMOTE_HPROF"
adb pull "$REMOTE_HPROF" "$OUT/heap.hprof" >/dev/null

adb shell rm "$REMOTE_HPROF"

echo "Capture completed: $OUT"
echo "Suggested analysis:"
echo "python3 analyze.py panorama -d \"$OUT\""
echo "python3 analyze.py combined --modern --hprof \"$OUT/heap.hprof\" --smaps \"$OUT/smaps.txt\" --meminfo \"$OUT/meminfo.txt\""
