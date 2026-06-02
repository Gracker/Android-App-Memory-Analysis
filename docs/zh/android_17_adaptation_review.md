# Android 17 / API 37 适配 Review

这份 review 只覆盖本仓库真实会受影响的边界：

- `tools/` 要能在 Android 17 设备上保留内存证据，包括目标进程已经被杀掉的场景。
- `demo/memory-lab` 要真正以 API 37 编译和运行。
- `docs/` 要区分离线解析兼容和 Android 17 设备侧证据。

## 当前结论

| 项目面 | 当前状态 | 证据 |
|--------|----------|------|
| Android 17 SDK | `compileSdk = 37`、`targetSdk = 37` | `demo/memory-lab/app/build.gradle.kts` |
| AGP/Gradle | AGP `9.2.0`、Gradle `9.4.1`，高于 Android 17 setup 要求的 AGP `8.9.0-rc01` 下限 | `demo/memory-lab/build.gradle.kts`、`gradle-wrapper.properties` |
| 16 KB page size | 继续保留 non-legacy JNI packaging 和 16 KB ELF alignment | `app/build.gradle.kts`、`CMakeLists.txt` |
| Android 17 memory limiter 证据 | 一键采集和 demo 脚本都会归档 raw `exit-info`、memory-limiter status、package UID、进程列表和设备元信息 | `tools/live_dumper.py`、`scripts/capture_memory_lab.sh` |
| 大屏 target 行为 | Demo 没有方向、宽高比、resize opt-out 限制，主界面是可滚动根布局 | `AndroidManifest.xml`、`activity_main.xml` |

还缺的是 Android 17 真机或模拟环境的设备侧复验；本地构建和 zipalign 可以按第 6 节命令复跑。

## 1. 构建适配

Android 17 对应 API 37。Demo 要分开 review `compileSdk` 和 `targetSdk`：

```kotlin
android {
    compileSdk = 37

    defaultConfig {
        targetSdk = 37
    }
}
```

`compileSdk` 决定能否引用 API 37；`targetSdk` 才会让 Android 17 target-only 行为生效。

本地构建前先确认：

```bash
java -version
ls "$ANDROID_HOME/platforms/android-37"
ls "$ANDROID_HOME/build-tools" | grep '^37'
```

Android 17 setup 还要求兼容的 Android Studio/SDK 和 Build Tools 37.x。当前 AGP `9.2.0` 已高于官方 AGP `8.9.0-rc01` 下限，所以不需要只为 API 37 再升级 AGP。

## 2. App Memory Limits

Android 17 引入的 app memory limits 是 Android 17 设备上的 all-app 行为，不是只有 `targetSdk = 37` 才触发；并且该限制只会在部分设备上施加。

本仓库的证据优先级：

1. `exit_info.txt` 里 `ApplicationExitInfo` 的 description 包含 `MemoryLimiter:AnonSwap`；对应 exit reason 预期是 `REASON_OTHER`。
2. `memory_limiter_status.txt` 说明设备级 memory-limiter 状态和当前限制配置。
3. `meminfo.txt`、`proc_meminfo.txt`、`zram_swap.txt`、`smaps.txt`、`showmap.txt` 解释事件前后内存形态。

`am memory-limiter status` 是全局能力和配置证据，不能单独证明当前 package 被 limiter 杀掉。判断是否命中 limiter 时，以 `exit-info` 中的 `MemoryLimiter:AnonSwap` 为更强证据。

Trigger-based profiling 可以用 `TRIGGER_TYPE_ANOMALY` 在系统杀进程前抓 heap dump。不要把 `TRIGGER_TYPE_OOM` 写成 Android 17 memory limiter 的核心证据，除非另有 Java 或 native OOM 证据。

## 3. 采集行为

现在 live dumper 会先创建采集目录，并在依赖 PID 的采集前归档 Android 17 证据。这样当目标进程已经被 memory limiter 杀掉时，仍然能保留最近一次退出相关材料。

预期产物：

- `build_fingerprint.txt`、`android_release.txt`、`android_sdk.txt`、`page_size.txt`
- `package_uid.txt`、`processes.txt`、`activity_processes.txt`
- `exit_info.txt` 或 `exit_info.err`
- `memory_limiter_status.txt` 或 `memory_limiter_status.err`
- 如果进程仍在运行：`showmap.txt`、`smaps.txt`、`meminfo.txt`、`gfxinfo.txt`、`proc_meminfo.txt`、`zram_swap.txt`、`dmabuf_debug.txt`，以及可选 `heap.hprof`

如果进程已经不在运行，这次 dump 仍适合做退出诊断，但不能当作完整 panorama 样本。

## 4. 大屏和可调整窗口

对 target API 37 的应用，Android 17 在大屏设备上移除了方向和可调整窗口行为的开发者 opt-out。当前 Demo manifest 没有限制方向、resize 或宽高比，主内容是 ScrollView。

仍需在真实 Android 17 大屏或可调整窗口环境复验：

- 旋转设备，或在可用环境中调整窗口大小。
- 确认所有场景按钮仍可触达。
- 确认 Activity 重建后状态文本和底部操作没有被裁剪。

## 5. Android 17 Review 清单

- [ ] `compileSdk = 37`
- [ ] `targetSdk = 37`
- [ ] 已安装 Android SDK Platform 37
- [ ] 已安装 Build Tools 37.x，并用它跑 `zipalign`
- [ ] APK 能用 JDK 17 和 AGP `9.2.0` 构建
- [ ] APK 通过 `zipalign -c -P 16`
- [ ] 采集记录 Android release/sdk、build fingerprint、page size
- [ ] 采集记录 `exit-info` 和 `am memory-limiter status`
- [ ] 如果出现 `MemoryLimiter:AnonSwap`，结论引用 `exit-info`，而不是只看内存总量
- [ ] 缺失 `smaps`、`showmap` 或 `dmabuf` 时报告为 unavailable，不误写成 0

## 6. 复验命令

```bash
cd demo/memory-lab
./gradlew :app:assembleDebug

APK=app/build/outputs/apk/debug/app-debug.apk
BUILD_TOOLS_37="$(ls -d "$ANDROID_HOME"/build-tools/37* | tail -n 1)"
"$BUILD_TOOLS_37/zipalign" -c -P 16 -v 4 "$APK"

adb install -r "$APK"
adb shell am force-stop com.androidperformance.memorylab
adb shell monkey -p com.androidperformance.memorylab 1

# 在 app 内触发场景后执行：
./scripts/capture_memory_lab.sh com.androidperformance.memorylab ./captures/android17

cd ../..
python3 analyze.py panorama -d demo/memory-lab/captures/android17 --markdown -o demo/memory-lab/captures/android17/report.md
```

如果进程已经被杀掉：

```bash
python3 analyze.py live --package com.androidperformance.memorylab --dump-only -o ./dumps
```

先看输出目录中的 `exit_info.txt`、`memory_limiter_status.txt`、`processes.txt` 和 `meta.txt`。

## 参考

- Android 17 SDK 设置: <https://developer.android.com/about/versions/17/setup-sdk>
- Android 17 全应用行为变更: <https://developer.android.com/about/versions/17/behavior-changes-all>
- Android 内存管理: <https://developer.android.com/topic/performance/memory>
- Android 17 大屏方向和可调整窗口变化: <https://developer.android.com/blog/posts/prepare-your-app-for-the-resizability-and-orientation-changes-in-android-17>
