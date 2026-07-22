# QA Signal Interpretation

## Signal ladder

| QA evidence | Treat as | Required follow-up before root cause |
|-------------|----------|--------------------------------------|
| Complete LeakCanary GC-root/reference path with `Leaking: YES` | Managed owner-path candidate | Confirm expected lifecycle, target/build/phase, suspect edge, and reproduction/comparison |
| LeakCanary notification or retained count | Detector trigger | Export the complete leak trace and identify the watched lifecycle |
| `has leaked window`, registration, SQLite, or closable warning | Runtime cleanup warning | Inspect the full stack/component teardown and verify the exact owner/release path |
| `OutOfMemoryError` or allocator failure | Terminal allocation symptom | Correlate heap/page/buffer state and earlier growth; the throw site may be innocent |
| GC blocking/emergency collection | Runtime pressure symptom | Align with heap/page trend, workload, pause window, and allocation owner evidence |
| LMKD or kernel OOM kill line | System policy/pressure event | Confirm target PID/process and time with ApplicationExitInfo, PSI/system pages, and timeline |
| JNI reference-table overflow | Native reference-management failure | Bind the creating stack, reference kind, lifecycle, and missing delete/release |
| Screenshot of a report, chart, warning, or profiler | Visual observation | Transcribe visible values/units/filters/region and return to the raw report or matching time series |

## Correlation workflow

1. Group log events by file, target identity, monotonic or wall-clock window, and phase. Do not sort lines from different clocks as one exact timeline without a synchronization point.
2. Use `qa_observations.android_logs[].signals` only as an index. Read the original authorized line and surrounding stack/event before quoting or assigning ownership; for bugreport ZIPs, bind the archive member as well as its member-local line number/hash. Zero matches are not negative evidence: inspect logs selected by the issue background, provenance, time window, and adjacent artifacts.
3. Bind screenshot claims to the screenshot artifact ID and visible region. State when text, units, filters, or time range are cropped or unreadable.
4. Separate four claim kinds:
   - observed: exact log event or visible screenshot field;
   - derived: count, time delta, or same-domain comparison with formula;
   - hypothesis: mechanism consistent with those observations;
   - recommendation: capture or code action after the owner/mechanism gate.
5. Correlate independent evidence: a LeakCanary path with lifecycle expectations, an OOM with page/object/buffer state, or an LMKD line with system pressure and exit info.
6. Preserve contradictions such as different PID/build/phase, screenshot values that disagree with text logs, truncated log scans, or missing lines between events.

## Leak report gate

A complete LeakCanary trace can serve as the managed owner-path branch instead of a separate HPROF only when the report includes the GC Root, reference path, leaking/non-leaking states, suspected edge, target identity, and enough context to verify lifecycle expectation. It still does not establish repeated growth; leak/regression claims need matching phases and comparison evidence.

## Output additions

Include a `QA observations` section before hypotheses:

- screenshot artifact and visible region, or log artifact plus archive member when present and line/hash;
- timestamp/tag/PID/package/build/phase when available;
- signal class and strength;
- exact bounded observation;
- what it does not prove;
- corroborating or contradicting artifact IDs;
- next smallest discriminator.

## Primary references

- [Android Logcat command-line tool](https://developer.android.com/tools/logcat)
- [LeakCanary retained-object detection](https://square.github.io/leakcanary/fundamentals-how-leakcanary-works/)
- [LeakCanary leak-trace interpretation](https://square.github.io/leakcanary/fundamentals-fixing-a-memory-leak/)
- [StrictMode VM leak detectors](https://developer.android.com/reference/android/os/StrictMode.VmPolicy.Builder)
- [AOSP LMKD behavior](https://source.android.com/docs/core/perf/lmkd)
