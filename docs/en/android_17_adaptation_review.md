# Android 17 / API 37 Adaptation Review

This review is scoped to this repository, not to every Android 17 platform change:

- `tools/` must keep collecting memory evidence on Android 17 devices, including cases where the target process has already exited.
- `demo/memory-lab` must build and run as an API 37 target.
- `docs/` must distinguish offline parser compatibility from device-side Android 17 evidence.

## Current Status

| Area | Status | Evidence |
|------|--------|----------|
| Android 17 SDK | `compileSdk = 37`, `targetSdk = 37` | `demo/memory-lab/app/build.gradle.kts` |
| AGP/Gradle | AGP `9.2.0`, Gradle `9.4.1`; above the Android 17 setup minimum AGP `8.9.0-rc01` | `demo/memory-lab/build.gradle.kts`, `gradle-wrapper.properties` |
| 16 KB page size | Existing non-legacy JNI packaging and 16 KB ELF alignment remain required | `app/build.gradle.kts`, `CMakeLists.txt` |
| Android 17 memory-limiter evidence | Live dump and demo capture now archive raw `exit-info`, memory-limiter status, package UID, process list, and device metadata | `tools/live_dumper.py`, `scripts/capture_memory_lab.sh` |
| Large-screen target behavior | Demo has no orientation, aspect ratio, or resize opt-out restrictions and uses a scrollable root | `AndroidManifest.xml`, `activity_main.xml` |

Device-side validation is still required on an Android 17 device with SDK 37 platform/build tools installed locally.

## 1. Build Adaptation

Android 17 maps to API 37. The demo must review `compileSdk` and `targetSdk` separately:

```kotlin
android {
    compileSdk = 37

    defaultConfig {
        targetSdk = 37
    }
}
```

`compileSdk` allows access to API 37. `targetSdk` opts the demo into Android 17 target-only behavior changes.

Before building, verify the local environment:

```bash
java -version
ls "$ANDROID_HOME/platforms/android-37"
ls "$ANDROID_HOME/build-tools" | grep '^37'
```

Android 17 setup also requires a compatible Android Studio/SDK setup and Build Tools 37.x. AGP `9.2.0` is already above the published minimum AGP `8.9.0-rc01`, so this repo does not need an AGP bump only for API 37.

## 2. App Memory Limits

Android 17 introduces app memory limits as an all-app behavior on Android 17 devices. This is not gated only by `targetSdk = 37`, and the limits are only imposed on a subset of devices.

Evidence priority for this repository:

1. `exit_info.txt` contains an `ApplicationExitInfo` description with `MemoryLimiter:AnonSwap`; the exit reason is expected to be `REASON_OTHER`.
2. `memory_limiter_status.txt` shows device-level memory-limiter status and configured limits.
3. `meminfo.txt`, `proc_meminfo.txt`, `zram_swap.txt`, `smaps.txt`, and `showmap.txt` explain the memory shape before or around the event.

`am memory-limiter status` is a global capability/configuration signal. It does not prove the current package was killed by the limiter. Treat `exit-info` as the stronger source.

Trigger-based profiling can use `TRIGGER_TYPE_ANOMALY` to collect heap dumps before the system kills a process for anomalous memory usage. Do not treat `TRIGGER_TYPE_OOM` as the primary Android 17 memory-limiter signal unless separate evidence shows an actual Java or native OOM path.

## 3. Collection Behavior

The live dumper now creates the dump directory and archives Android 17 evidence before requiring a running PID. This matters because a memory-limiter investigation often starts after the target process has already exited.

Expected artifacts:

- `build_fingerprint.txt`, `android_release.txt`, `android_sdk.txt`, `page_size.txt`
- `package_uid.txt`, `processes.txt`, `activity_processes.txt`
- `exit_info.txt` or `exit_info.err`
- `memory_limiter_status.txt` or `memory_limiter_status.err`
- If the process is running: `showmap.txt`, `smaps.txt`, `meminfo.txt`, `gfxinfo.txt`, `proc_meminfo.txt`, `zram_swap.txt`, `dmabuf_debug.txt`, and optional `heap.hprof`

If the process is not running, the dump is still useful for exit diagnostics but is not a full panorama sample.

## 4. Large Screens and Resizability

For apps targeting API 37, Android 17 removes the developer opt-out from orientation and resizability behavior on large-screen devices. The demo currently has no manifest orientation, resize, or aspect-ratio restrictions, and its main content is scrollable.

Validation still needs a real Android 17 large-screen or resizable environment:

- Rotate the device and resize the window when possible.
- Confirm all scenario buttons remain reachable.
- Confirm status text and bottom actions are not clipped after recreation.

## 5. Android 17 Review Checklist

- [ ] `compileSdk = 37`
- [ ] `targetSdk = 37`
- [ ] Android SDK Platform 37 is installed
- [ ] Build Tools 37.x is installed and used for `zipalign`
- [ ] APK builds with JDK 17 and AGP `9.2.0`
- [ ] APK passes `zipalign -c -P 16`
- [ ] Capture records Android release/sdk, build fingerprint, and page size
- [ ] Capture records `exit-info` and `am memory-limiter status`
- [ ] If `MemoryLimiter:AnonSwap` is present, conclusions cite `exit-info`, not only memory totals
- [ ] Missing `smaps`, `showmap`, or `dmabuf` is reported as unavailable, not as zero

## 6. Validation Commands

```bash
cd demo/memory-lab
./gradlew :app:assembleDebug

APK=app/build/outputs/apk/debug/app-debug.apk
BUILD_TOOLS_37="$(ls -d "$ANDROID_HOME"/build-tools/37* | tail -n 1)"
"$BUILD_TOOLS_37/zipalign" -c -P 16 -v 4 "$APK"

adb install -r "$APK"
adb shell am force-stop com.androidperformance.memorylab
adb shell monkey -p com.androidperformance.memorylab 1

# After triggering scenarios in the app:
./scripts/capture_memory_lab.sh com.androidperformance.memorylab ./captures/android17

cd ../..
python3 analyze.py panorama -d demo/memory-lab/captures/android17 --markdown -o demo/memory-lab/captures/android17/report.md
```

If the process was killed before capture:

```bash
python3 analyze.py live --package com.androidperformance.memorylab --dump-only -o ./dumps
```

Use the resulting `exit_info.txt`, `memory_limiter_status.txt`, `processes.txt`, and `meta.txt` as the first-pass evidence.

## References

- Android 17 SDK setup: <https://developer.android.com/about/versions/17/setup-sdk>
- Android 17 behavior changes for all apps: <https://developer.android.com/about/versions/17/behavior-changes-all>
- Manage your app's memory: <https://developer.android.com/topic/performance/memory>
- Android 17 resizability and orientation changes: <https://developer.android.com/blog/posts/prepare-your-app-for-the-resizability-and-orientation-changes-in-android-17>
