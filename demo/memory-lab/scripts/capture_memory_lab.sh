#!/usr/bin/env bash

set -euo pipefail

PKG="${1:-com.androidperformance.memorylab}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${2:-./captures/${TS}}"
REMOTE_HPROF="/data/local/tmp/memory_lab_${TS}.hprof"

mkdir -p "$OUT"

echo "Trying to restart adbd as root..."
adb root >/dev/null 2>&1 || true
adb wait-for-device

ROOT_ID="$(adb shell id | tr -d '\r')"
if [[ "$ROOT_ID" != *"uid=0"* ]]; then
  echo "adb root is not available on this device build."
  echo "Continuing with non-root capture; smaps and dmabuf may be unavailable."
fi

PID="$(adb shell pidof "$PKG" | tr -d '\r' | awk '{print $1}')"
if [[ -z "$PID" ]]; then
  PID="$(adb shell ps -A | tr -d '\r' | awk -v pkg="$PKG" '$NF == pkg || $NF ~ "^" pkg ":" { for (i = 2; i < NF; i++) if ($i ~ /^[0-9]+$/) { print $i; exit } }')"
fi
if [[ -z "$PID" ]]; then
  echo "Process not found for package: $PKG"
  exit 1
fi

echo "Package: $PKG"
echo "PID: $PID"
echo "Output: $OUT"

adb shell getprop ro.build.fingerprint > "$OUT/build_fingerprint.txt" 2>/dev/null || true
adb shell getprop ro.build.version.release > "$OUT/android_release.txt" 2>/dev/null || true
adb shell getprop ro.build.version.sdk > "$OUT/android_sdk.txt" 2>/dev/null || true
adb shell getconf PAGE_SIZE > "$OUT/page_size.txt" 2>/dev/null || true

if adb shell showmap "$PID" > "$OUT/showmap.txt" 2>"$OUT/showmap.err"; then
  true
else
  echo "showmap unavailable; see $OUT/showmap.err"
fi

SMAPS_OK=0
for CMD in \
  "cat /proc/$PID/smaps" \
  "su -c 'cat /proc/$PID/smaps'" \
  "su 0 cat /proc/$PID/smaps"; do
  if adb shell "$CMD" > "$OUT/smaps.txt" 2>"$OUT/smaps.err" && [[ -s "$OUT/smaps.txt" ]]; then
    SMAPS_OK=1
    break
  fi
done
if [[ "$SMAPS_OK" -ne 1 ]]; then
  echo "smaps unavailable; see $OUT/smaps.err"
fi

adb shell dumpsys meminfo -d "$PKG" > "$OUT/meminfo.txt"
adb shell dumpsys gfxinfo "$PKG" > "$OUT/gfxinfo.txt"
adb shell cat /proc/meminfo > "$OUT/proc_meminfo.txt" 2>/dev/null || true

{
  echo "===== /proc/swaps ====="
  adb shell cat /proc/swaps 2>/dev/null || true
  echo
  for DEVICE in $(adb shell "ls -d /sys/block/zram* 2>/dev/null" | tr -d '\r'); do
    NAME="$(basename "$DEVICE")"
    echo "===== $NAME ====="
    adb shell "cat /sys/block/$NAME/disksize 2>/dev/null" | sed 's/^/disksize: /' || true
    adb shell "cat /sys/block/$NAME/mm_stat 2>/dev/null" | sed 's/^/mm_stat: /' || true
    adb shell "cat /sys/block/$NAME/stat 2>/dev/null" | sed 's/^/stat: /' || true
    echo
  done
} > "$OUT/zram_swap.txt"

DMABUF_OK=0
for CMD in \
  "cat /sys/kernel/debug/dma_buf/bufinfo" \
  "su -c 'cat /sys/kernel/debug/dma_buf/bufinfo'" \
  "su 0 cat /sys/kernel/debug/dma_buf/bufinfo"; do
  if adb shell "$CMD" > "$OUT/dmabuf_debug.txt" 2>"$OUT/dmabuf.err" && [[ -s "$OUT/dmabuf_debug.txt" ]]; then
    DMABUF_OK=1
    break
  fi
done
if [[ "$DMABUF_OK" -ne 1 ]]; then
  echo "dmabuf unavailable; see $OUT/dmabuf.err"
fi

if adb shell am dumpheap "$PKG" "$REMOTE_HPROF"; then
  adb pull "$REMOTE_HPROF" "$OUT/heap.hprof" >/dev/null
  adb shell rm "$REMOTE_HPROF"
else
  echo "HPROF dump failed; continuing without heap.hprof"
fi

cat > "$OUT/meta.txt" <<META
Package: $PKG
PID: $PID
Timestamp: $TS
PageSize: $(tr -d '\r' < "$OUT/page_size.txt" 2>/dev/null || true)
AndroidRelease: $(tr -d '\r' < "$OUT/android_release.txt" 2>/dev/null || true)
AndroidSdk: $(tr -d '\r' < "$OUT/android_sdk.txt" 2>/dev/null || true)
META

echo "Capture completed: $OUT"
echo "Suggested analysis:"
echo "python3 analyze.py panorama -d \"$OUT\""
if [[ -f "$OUT/heap.hprof" && -s "$OUT/smaps.txt" ]]; then
  echo "python3 analyze.py combined --modern --hprof \"$OUT/heap.hprof\" --smaps \"$OUT/smaps.txt\" --meminfo \"$OUT/meminfo.txt\""
fi
