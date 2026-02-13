# Memory Lab Demo APK

This demo APK is intentionally built to generate representative Android memory issues that are easy to observe with:

- `showmap`
- `/proc/<pid>/smaps`
- `dumpsys meminfo -d`
- `HPROF`

It is designed for this repository's analysis scripts and thresholds (`tools/panorama_analyzer.py`, `tools/meminfo_parser.py`, `tools/smaps_parser.py`, `tools/hprof_parser.py`).

## 1. Project Structure

`demo/memory-lab` is an independent Android project.

- `app/src/main/java/com/androidperformance/memorylab/MainActivity.java`: scenario trigger UI
- `app/src/main/java/com/androidperformance/memorylab/MemoryScenarioController.java`: scenario orchestrator
- `app/src/main/java/com/androidperformance/memorylab/LeakySingletons.java`: long-lived holders used to simulate leaks
- `app/src/main/java/com/androidperformance/memorylab/NativeBridge.java`: JNI bridge
- `app/src/main/cpp/native_memory_demo.cpp`: native allocation logic (`malloc` + `mmap`)

## 2. Scenarios

1. **Java leak + collections**
   - Leaks Activity reference in static holder
   - Creates long-lived object payloads
   - Creates low-utilization collections and empty collections

2. **Bitmap duplicates + large bitmap**
   - Includes repeated `820x544` bitmaps
   - Includes large bitmaps (`2112x1080`, `1091x724`, `968x544`)

3. **DirectByteBuffer native pressure**
   - Allocates retained direct buffers in Java static list

4. **JNI malloc/mmap native pressure**
   - Allocates native blocks and keeps pointers alive until explicit free

5. **Ashmem pressure**
   - Uses `SharedMemory.create()` and retains references

6. **Thread stack pressure**
   - Starts many sleeping threads to increase stack mappings

7. **WebView native pressure**
   - Creates retained WebViews and loads heavy HTML canvas content

8. **View storm (coverage for high view count rules)**
   - Creates and retains hundreds of TextView instances

9. **UI jank storm (coverage for frame jank rules)**
   - Runs deliberate UI-thread blocking work in short bursts

10. **Fragment/Service/BroadcastReceiver leak set**
   - Retains multiple reachable instances for component leak heuristics

11. **Business LruCache misconfiguration**
   - Low utilization and low hit-rate cache behavior for HPROF cache checks

Use `0) One-click trigger all scenarios` on the home screen to inject all major patterns at once.

## 3. Build and Install

From `demo/memory-lab`:

```bash
./gradlew :app:assembleDebug
./gradlew :app:installDebug
```

If the Gradle wrapper is not present in your environment, open this folder in Android Studio and let it generate/use local Gradle automatically.

## 4. Capture Commands

Root-first capture variables:

```bash
PKG=com.androidperformance.memorylab
TS=$(date +%Y%m%d_%H%M%S)
OUT=./captures/$TS
REMOTE_HPROF=/data/local/tmp/memory_lab_$TS.hprof

adb root
adb wait-for-device

PID=$(adb shell pidof $PKG)
mkdir -p "$OUT"
```

If `adb root` is unavailable (common on user builds), keep the same flow but skip `adb root` and prefer fallback collection where `smaps` may be unavailable.

Capture all primary artifacts:

```bash
adb shell showmap $PID > "$OUT/showmap.txt"
adb shell "cat /proc/$PID/smaps" > "$OUT/smaps.txt" || adb shell "su -c 'cat /proc/$PID/smaps'" > "$OUT/smaps.txt" || adb shell "su 0 cat /proc/$PID/smaps" > "$OUT/smaps.txt"
adb shell dumpsys meminfo -d $PKG > "$OUT/meminfo.txt"
adb shell dumpsys gfxinfo $PKG > "$OUT/gfxinfo.txt"
adb shell am dumpheap $PKG $REMOTE_HPROF
adb pull $REMOTE_HPROF "$OUT/heap.hprof"
adb shell rm $REMOTE_HPROF
```

Or run the bundled script (same root-first flow): `./scripts/capture_memory_lab.sh`

## 5. Analyze with This Repository

```bash
python3 analyze.py panorama -d "$OUT"

python3 analyze.py combined --modern \
  --hprof "$OUT/heap.hprof" \
  --smaps "$OUT/smaps.txt" \
  --meminfo "$OUT/meminfo.txt" \
  --json-output "$OUT/report.json"
```

## 6. Expected Signals by Scenario

- Java leak + collections:
  - `meminfo`: Java Heap rises, Activities/Views may rise
  - `HPROF`: accumulation points, duplicate-like component retention, collection capacity issues
- Bitmap scenario:
  - `meminfo -d`: Bitmap malloced/nonmalloced count+size grows
  - `HPROF`: large and duplicate bitmap dimensions visible
  - `smaps/showmap`: graphics-related mappings increase
- JNI/native/direct buffer/ashmem:
  - `meminfo`: Native Heap rises
  - `smaps/showmap`: native allocator or ashmem-related mappings increase
  - `HPROF`: Java side does not fully explain native growth (good for untracked native discussion)
- Thread scenario:
  - `meminfo`: Stack rises
  - `smaps/showmap`: stack mappings increase
- WebView scenario:
  - `meminfo`: WebViews count and Native Heap may rise

## 7. Reset Strategy

- Use app buttons:
  - `Clear Java objects/bitmaps/buffers`
  - `Free JNI native + ashmem`
  - `Stop extra threads`
  - `Clear ALL scenarios`
- For strict baseline between scenarios:

```bash
adb shell am force-stop com.androidperformance.memorylab
adb shell monkey -p com.androidperformance.memorylab 1
```

## 8. Refresh Repository Demo Samples

After capturing `./captures/latest`, refresh the root `demo/*_sample` datasets used by `analyze.py --demo`:

```bash
gzip -c ./captures/latest/heap.hprof > ../hprof_sample/heapdump_latest.hprof.gz
cp ./captures/latest/smaps.txt ../smaps_sample/smaps
cp ./captures/latest/meminfo.txt ../smaps_sample/meminfo.txt
cp ./captures/latest/showmap.txt ../smaps_sample/showmap.txt
cp ./captures/latest/gfxinfo.txt ../smaps_sample/gfxinfo.txt
cp ./captures/latest/report.json ../smaps_sample/report.json
cp ./captures/latest/panorama_report.json ../smaps_sample/panorama_report.json
```

`analyze.py` supports `.hprof.gz` and extracts it to a temporary file during analysis.
