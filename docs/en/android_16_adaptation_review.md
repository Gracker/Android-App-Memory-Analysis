# Android 16 / API 36 Adaptation Review

This review is scoped to this repository:

- `tools/` must keep collecting and interpreting memory data on Android 16 devices, including permission-denied fallbacks.
- `demo/memory-lab` is a native-code demo APK and must be valid when targeting API 36.
- `docs/` must explain which conclusions are supported by `meminfo`, `smaps`, `showmap`, `hprof`, `dmabuf`, and `zram`, and which are only hypotheses.

## Current Status

| Area | Status | Evidence |
|------|--------|----------|
| Android 16 SDK | `compileSdk = 36`, `targetSdk = 36` | `demo/memory-lab/app/build.gradle.kts` |
| AGP/Gradle | AGP `9.2.0`, Gradle `9.4.1` | `demo/memory-lab/build.gradle.kts`, `gradle-wrapper.properties` |
| Edge-to-edge | Explicitly enabled with system bar and cutout insets | `MainActivity.setupSystemBarInsets()` |
| Predictive back | No custom back interception, no temporary opt-out required | `MainActivity` |
| 16 KB page size | Non-legacy JNI packaging plus 16 KB ELF linker flags | `app/build.gradle.kts`, `CMakeLists.txt` |
| Collection fallback | `proc_meminfo`, `zram_swap`, and `dmabuf_debug` are included; non-root capture continues | `tools/live_dumper.py`, `scripts/capture_memory_lab.sh` |

Device-side validation is still required on an Android 16 or 16 KB page-size environment.

## Build Adaptation

Android 16 maps to API 36. `compileSdk` and `targetSdk` must be reviewed separately:

```kotlin
android {
    compileSdk = 36

    defaultConfig {
        targetSdk = 36
    }
}
```

`compileSdk` only allows access to API 36. `targetSdk` opts the app into Android 16 target-only behavior changes.

Before building, verify the local environment:

```bash
java -version
ls "$ANDROID_HOME/platforms/android-36"
ls "$ANDROID_HOME/build-tools/36.0.0"
```

## 16 KB Page Size

16 KB page size affects both installation/runtime compatibility and memory interpretation:

- `smaps` still reports kB values; parsers must not assume 4 KB pages.
- `mmap`, ashmem, DirectByteBuffer, and thread stack mappings can show larger page-rounding overhead.
- Native `.so` files need 16 KB-compatible ZIP and ELF alignment.
- Prebuilt SDK `.so` files must be checked as well.

The demo now uses non-legacy JNI packaging:

```kotlin
packaging {
    jniLibs {
        useLegacyPackaging = false
    }
}
```

The CMake target also has explicit 16 KB ELF alignment flags:

```cmake
target_link_options(
        memorylab
        PRIVATE
        "-Wl,-z,max-page-size=16384"
        "-Wl,-z,common-page-size=16384")
```

Required validation:

```bash
cd demo/memory-lab
./gradlew :app:assembleDebug

APK=app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/build-tools/36.0.0/zipalign" -c -P 16 -v 4 "$APK"

adb install -r "$APK"
adb shell getconf PAGE_SIZE
```

Pass criteria:

- `zipalign` reports verification success.
- 16 KB test environment returns `16384` from `getconf PAGE_SIZE`.
- The native malloc/mmap scenario starts and clears without linker or mmap errors.

## Runtime Behavior

For apps targeting API 36, Android 16 disables the edge-to-edge opt-out. The demo now explicitly enters edge-to-edge and applies `systemBars | displayCutout` insets to its content root.

Predictive back is enabled by default for target 36 apps on Android 16. The demo does not intercept back, so no manifest opt-out is needed. If custom exit/cancel behavior is added later, use supported AndroidX or platform back APIs rather than old key dispatch.

JobScheduler quota changes do not directly affect this Python+ADB collection flow. They can affect the app being analyzed, so Android 16 memory investigations should record foreground/background state, foreground-service state, and standby bucket when background work is part of the scenario.

## Collection Matrix

| Source | Android 16 risk | Current strategy |
|--------|-----------------|------------------|
| `dumpsys meminfo -d` | ROM output sections can vary | Main direction signal, cross-check with HPROF/smaps |
| `gfxinfo` | Graphics fields vary by ROM/WebView | Auxiliary Graphics/GPU signal |
| `smaps` | User builds often deny access | Direct cat -> `su -c` -> `su 0`, then degrade |
| `showmap` | May be permission-limited | Best effort |
| `/proc/meminfo` | Usually readable | Always collect system pressure context |
| `zram/swap` | Kernel fields vary | Collect both new and old zRAM fields |
| `dmabuf_debug` | debugfs usually requires root | Best effort, do not treat missing data as zero |
| HPROF | Requires debuggable/internal build or root | Demo debug build supports it |

## Review Checklist

- [ ] `compileSdk = 36`
- [ ] `targetSdk = 36`
- [ ] AGP supports API 36 without suppressing warnings
- [ ] JDK 17 and Build Tools 36 are available
- [ ] APK passes `zipalign -c -P 16`
- [ ] 16 KB environment reports `PAGE_SIZE=16384`
- [ ] Edge-to-edge content does not overlap status/nav/cutout areas
- [ ] No legacy back-key dependency
- [ ] Capture includes build fingerprint, Android release/sdk, and page size
- [ ] Non-root capture still produces a useful `meminfo/gfxinfo/proc_meminfo/zram` report

## References

- Android 16 SDK setup: <https://developer.android.com/about/versions/16/setup-sdk>
- Android 16 target behavior changes: <https://developer.android.com/about/versions/16/behavior-changes-16>
- 16 KB page size support: <https://developer.android.com/guide/practices/page-sizes>
- AGP 9.2 compatibility: <https://developer.android.com/build/releases/agp-9-2-0-release-notes>
