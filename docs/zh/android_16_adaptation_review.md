# Android 16 / API 36 适配 Review

这份 review 不是泛泛列 Android 16 行为变更，而是把本仓库的真实边界拆开：

- `tools/` 是离线和在线采集分析工具，重点是 Android 16 设备上的输入格式、权限退化和证据口径。
- `demo/memory-lab` 是带 JNI 的 Demo APK。这份文档记录 API 36 基线；当前 `master` 已经 target API 37，当前 SDK 复验请看 `android_17_adaptation_review.md`。
- `docs/` 是教学链路，重点是让团队知道哪些结论能从 `meminfo/smaps/showmap/hprof/dmabuf/zram` 交叉证明，哪些只能作为假设。

## 当前结论

| 项目面 | 当前状态 | 证据 |
|--------|----------|------|
| Android 16 SDK | 保留 API 36 基线；当前 Demo SDK 已被 Android 17 / API 37 supersede | `demo/memory-lab/app/build.gradle.kts`、`android_17_adaptation_review.md` |
| AGP/Gradle | 已升到 AGP `9.2.0`、Gradle `9.4.1` | `demo/memory-lab/build.gradle.kts`、`gradle-wrapper.properties` |
| edge-to-edge | 已显式启用并处理 system bars/display cutout insets | `MainActivity.setupSystemBarInsets()` |
| predictive back | 当前 Demo 没有拦截 back，不需要临时 opt-out | `MainActivity` 未使用 `onBackPressed`/`KEYCODE_BACK` |
| 16 KB page size | 已显式关闭 legacy JNI packaging，并给 CMake `.so` 增加 16 KB ELF alignment linker flags | `app/build.gradle.kts`、`CMakeLists.txt` |
| 采集退化 | 已补 `proc_meminfo`、`zram_swap`、`dmabuf_debug`，并允许非 root 采集继续执行 | `tools/live_dumper.py`、`scripts/capture_memory_lab.sh` |

还缺的是设备侧实测：需要在 Android 16 真机或 16 KB page size 环境跑一次 `assembleDebug -> install -> trigger -> capture -> panorama`，把 `PAGE_SIZE=16384`、`zipalign -P 16`、采集结果一起归档。

## 1. 构建适配

### 1.1 compileSdk/targetSdk

Android 16 对应 API 36。这一节记录 API 36 基线；当前 `master` 使用 API 37。如果复验 API 36 分支，需要分别检查编译目标和运行目标：

```kotlin
android {
    compileSdk = 36

    defaultConfig {
        targetSdk = 36
    }
}
```

这里不能只升 `compileSdk`。`compileSdk` 只决定能否引用 API 36，`targetSdk` 才会让 Android 16 target-only 行为真正生效。适配 review 必须把这两个维度分开看。

### 1.2 AGP/Gradle

本仓库之前用 AGP `8.5.2`，在 `compileSdk 35` 下已经有 unsupported compileSdk warning。Android 16 SDK 官方建议先升级 AGP；AGP `9.2.0` 当前支持 API 36.1，并要求 Gradle `9.4.1`、JDK 17、Build Tools `36.0.0`。

本地构建前先确认：

```bash
java -version
ls "$ANDROID_HOME/platforms/android-36"
ls "$ANDROID_HOME/build-tools/36.0.0"
```

## 2. 16 KB Page Size 适配

### 2.1 为什么这和内存分析项目有关

16 KB page size 不只是安装兼容问题，也会影响内存分析解读：

- `smaps` 的 `Size/Rss/Pss/Private_*` 仍以 kB 输出，解析器不应该假设 1 page = 4 KB。
- `mmap`、ashmem、DirectByteBuffer、thread stack 等映射的最小提交粒度可能变大，小对象压力在 `smaps/showmap` 中会表现为更明显的 page rounding。
- Native `.so` 如果没有 16 KB ELF/ZIP alignment，APK 可能在 16 KB 设备上安装或运行失败，导致后续采集链路无意义。
- 线上 SDK 的 prebuilt `.so` 也要一起验，不能只验 Demo 自己编出来的 `libmemorylab.so`。

### 2.2 当前 Demo 的处理

Gradle 侧固定不使用 legacy JNI packaging：

```kotlin
packaging {
    jniLibs {
        useLegacyPackaging = false
    }
}
```

CMake 侧显式增加 16 KB ELF alignment：

```cmake
target_link_options(
        memorylab
        PRIVATE
        "-Wl,-z,max-page-size=16384"
        "-Wl,-z,common-page-size=16384")
```

这对 NDK r27 及以下也有效；NDK r28+ 默认已经按 16 KB 对齐，但保留 linker flags 能让项目对本机默认 NDK 选择更稳。

### 2.3 必跑验证

```bash
cd demo/memory-lab
./gradlew :app:assembleDebug

APK=app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/build-tools/36.0.0/zipalign" -c -P 16 -v 4 "$APK"

adb install -r "$APK"
adb shell getconf PAGE_SIZE
```

通过标准：

- `zipalign` 输出 `Verification successful`。
- 16 KB 环境下 `adb shell getconf PAGE_SIZE` 返回 `16384`。
- App 能启动、能触发 `JNI malloc/mmap native pressure`，不出现 linker 或 `mmap` 参数错误。

## 3. Android 16 Runtime 行为

### 3.1 Edge-to-edge

Android 16 上，面向 API 36 的应用不能再通过 `windowOptOutEdgeToEdgeEnforcement` 退出 edge-to-edge。Demo 是单 Activity + ScrollView，所以适配策略是：

- 调用 `WindowCompat.setDecorFitsSystemWindows(getWindow(), false)` 明确进入 edge-to-edge。
- 对内容根节点应用 `systemBars | displayCutout` insets，保留原始 16dp 内容 padding。
- 不依赖状态栏高度常量，不手写 magic number。

验证方式：

```bash
adb shell am start -n com.androidperformance.memorylab/.MainActivity
```

检查顶部标题、底部按钮和状态栏/导航栏/挖孔区域不重叠。

### 3.2 Predictive back

Android 16 target 36 默认启用 predictive back 动画，并且旧式 back 事件路径会变化。当前 Demo 不拦截 back，不需要设置 `android:enableOnBackInvokedCallback="false"`。后续如果增加自定义退出确认、采集中断确认，必须使用 AndroidX `OnBackPressedDispatcher` 或平台 back APIs，而不是重写旧式 key 事件。

### 3.3 JobScheduler/WorkManager

本仓库的采集入口是桌面侧 Python + ADB，不通过 Android app 内部 `JobScheduler`。因此 Android 16 的 job quota 不是 Demo APK 的直接 blocker。

但被分析的真实业务 App 如果依赖 WorkManager/JobScheduler 做后台预热、同步、上传，Android 16 上 job quota 可能改变触发时机。做内存复验时必须记录应用状态：

- 前台可见、后台、前台服务并发、standby bucket 分别跑。
- 采集前记录 `dumpsys activity processes` 或至少记录复现场景状态。
- 不要把“后台任务没跑起来”误判成“内存修好了”。

## 4. 采集链路适配

Android 16 用户版本设备上，`smaps`、debugfs DMA-BUF 很可能不可读。工具链应该退化，而不是失败退出。

| 数据源 | Android 16 风险 | 当前策略 |
|--------|-----------------|----------|
| `dumpsys meminfo -d` | ROM 输出段落可能变化，Native Allocations 不一定完整 | 作为主方向信号，但 Bitmap/Native 结论需要和 HPROF/smaps 交叉验证 |
| `gfxinfo` | 图形缓存字段受 ROM 和 WebView 实现影响 | 作为 Graphics/GPU 辅助口径 |
| `smaps` | user build 常见权限拒绝 | 直接 cat -> `su -c` -> `su 0`，失败则保留其他证据 |
| `showmap` | 可能权限受限 | 能采则采，不能采不阻断 |
| `/proc/meminfo` | 通常可读 | 固定采集，提供系统压力上下文 |
| `zram/swap` | sysfs 字段因内核版本变化 | 固定采集，解析器按新旧字段兼容 |
| `dmabuf_debug` | debugfs 通常需要 root | 尝试采集，失败只降级图形硬件缓冲分析 |
| HPROF | 非 debuggable app 受限 | Demo debug 可用；业务 App 需 debug/internal build 或 root |

## 5. Android 16 内存分析 Review 清单

### 构建清单

- [ ] API 36 分支或基线使用 `compileSdk = 36`
- [ ] API 36 分支或基线使用 `targetSdk = 36`
- [ ] AGP 版本支持 API 36，不靠 suppress warning 过关
- [ ] JDK 17、Build Tools 36 可用
- [ ] Native `.so` 通过 `zipalign -c -P 16`
- [ ] 16 KB 环境 `getconf PAGE_SIZE` 实测为 `16384`

### UI/行为清单

- [ ] edge-to-edge 下内容不被 status bar/navigation bar/cutout 遮挡
- [ ] 没有依赖旧 back key dispatch 的退出逻辑
- [ ] 如有横竖屏/大屏限制，已验证 Android 16 大屏兼容策略
- [ ] 非英文复杂文字布局没有因为 font metric 变化而裁剪

### 采集清单

- [ ] 同一次采集记录 `build_fingerprint`、Android release/sdk、`PAGE_SIZE`
- [ ] root 和非 root 两条路径都有明确输出
- [ ] `meminfo/gfxinfo/proc_meminfo/zram` 即使无 root 也能形成报告
- [ ] `smaps/showmap/dmabuf` 缺失时报告不误报为 0
- [ ] before/after 使用同一套采集方式，避免口径漂移

### 结论清单

- [ ] Java 泄漏结论必须有 HPROF 或 Objects 证据
- [ ] Native 未追踪结论必须说明 `meminfo Native Heap - Native Allocations` 的口径
- [ ] Graphics/DMA-BUF 结论必须说明是否有 `dmabuf_debug` 权限
- [ ] 16 KB page size 场景下，不用 4 KB page 数推导内存大小

## 6. 一次完整 Android 16 复验命令

```bash
cd demo/memory-lab
./gradlew :app:assembleDebug

APK=app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/build-tools/36.0.0/zipalign" -c -P 16 -v 4 "$APK"

adb install -r "$APK"
adb shell am force-stop com.androidperformance.memorylab
adb shell monkey -p com.androidperformance.memorylab 1

# 在设备上点击 0) One-click trigger all scenarios 后执行：
./scripts/capture_memory_lab.sh com.androidperformance.memorylab ./captures/android16

cd ../..
python3 analyze.py panorama -d demo/memory-lab/captures/android16 --markdown -o demo/memory-lab/captures/android16/report.md
```

最终归档至少包含：

- `app-debug.apk`
- `zipalign` 输出
- `page_size.txt`
- `meta.txt`
- `meminfo.txt`
- `gfxinfo.txt`
- `proc_meminfo.txt`
- `zram_swap.txt`
- `smaps.txt` 或 `smaps.err`
- `dmabuf_debug.txt` 或 `dmabuf.err`
- `report.md`

## 参考

- Android 16 SDK 设置: <https://developer.android.com/about/versions/16/setup-sdk>
- Android 16 target 行为变更: <https://developer.android.com/about/versions/16/behavior-changes-16>
- 16 KB page size 支持: <https://developer.android.com/guide/practices/page-sizes>
- AGP 9.2 兼容性: <https://developer.android.com/build/releases/agp-9-2-0-release-notes>
