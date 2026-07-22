# Verification Matrix

| Change type | Code/functional verification | Memory evidence | Regression checks |
|-------------|------------------------------|-----------------|-------------------|
| Activity/Fragment/View/Service/Receiver leak | Lifecycle tests, navigation/recreation, callbacks | Repeated HPROF retained path plus meminfo phase trend | State restoration, event delivery, crashes |
| Collection/cache | Unit tests for budget/eviction/concurrency | Object/count/retained trend plus process-page direction | Hit rate, latency, I/O/network, stale data |
| Native/JNI | Native/unit/integration tests, error/cancel paths | heapprofd/malloc stacks plus smaps/meminfo | UAF/double free, symbolization, throughput |
| DirectByteBuffer/shared memory | Owner/release and cross-thread/process tests | Wrapper path plus native mapping/buffer evidence | Consumer lifetime, data integrity |
| Bitmap/Surface/graphics | Visual, lifecycle, renderer/recreation tests | gfxinfo + DMA-BUF/memtrack/smaps + meminfo | Jank, artifacts, black frames, reload cost |
| WebView | Navigation/process/provider/recreation tests | App and renderer evidence, partition_alloc/buffers | Page state, session, latency, crashes |
| Background/process policy | Work scheduling and process-state tests | PSI/Perfetto/exit-info/system pages over time | Startup/recovery, battery, notifications |
| Instrumentation only | Parser/schema/status tests | Expected artifact appears with correct target/phase | Privacy, overhead, permissions, storage |
| QA-log/screenshot-driven owner | Source/lifecycle test for the exact bound component or callsite | Original line/stack or visible region plus matching retained-path/page/buffer evidence after the same scenario | Build/phase identity, cropped context, log filtering, clock alignment, false keyword matches |

## Before/after gate

Require:

- same device bucket, API, fingerprint policy, page size, app revision, build variant, and scenario;
- same target process role and stable PID semantics;
- same loops, waits, exit action, cooldown, and collection perturbation;
- multiple runs when natural variance can overlap the expected improvement;
- same accounting domain and formula;
- functional and user-experience checks alongside memory evidence.

Report unavailable device or production validation separately. Do not replace it with a local parser test.
