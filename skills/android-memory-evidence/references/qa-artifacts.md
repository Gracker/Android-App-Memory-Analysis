# QA Logs and Screenshots

## Intake contract

Preserve every supplied file and record its source, build, device, package/process, reproduction step, timestamp or time window, phase, and whether it is complete or filtered. The normal intake is the complete QA handoff directory plus the issue title or symptom. Do not require the user to pre-classify, rename, or enumerate its contents. Keep multiple logs and screenshots separate; do not concatenate them before hashing or validation.

The bundled runtime recursively indexes regular files without following symlinks. Known names and extensions are hints, then content signatures identify supported evidence; all remaining indexed files become `unclassified_file` records. Plain, gzip, and bugreport ZIP logs are supported without extracting archives to disk. Check `folder_inventory` and limitations before claiming complete coverage. Defaults are 2,048 indexed files, 64 processed artifacts per type, 32 MiB decoded per log/archive, 256 ZIP members, 512 MiB per-file hashing, and 1 GiB total hashing. Use repeatable overrides only when files live outside the evidence directory:

```bash
python3 .agents/skills/android-memory-evidence/scripts/build_context.py \
  --dump-dir /path/to/case \
  --android-log /path/to/logcat-main.log \
  --android-log /path/to/system.log.gz \
  --qa-screenshot /path/to/leakcanary.png \
  --qa-screenshot /path/to/memory-chart.jpg \
  --question "QA saw a leak after five loops" \
  --output android-memory-context.json
```

## Log handling

The runtime scans at most 32 MiB of decoded content per log/archive and emits no raw lines. ZIP scanning reads at most 256 non-directory members in place, skips binary/encrypted members, and never extracts paths. It records signal type, strength, count, archive member when applicable, one-based line numbers, line SHA-256, available threadtime timestamps/tags, scan truncation, and a `does_not_prove` boundary. Use those entries as an index into the original authorized log.

Zero signal matches means only that the bounded pattern inventory found none of its known markers. It does not prove the log is irrelevant or the issue is absent. Use the issue title, file provenance, time window, tags, stacks, and neighboring artifacts to decide which original logs still need manual inspection.

For each relevant match:

1. Open the original line and enough surrounding context to capture the complete event or stack.
2. Confirm time, tag, PID/TID, package/process, build, scenario, and phase.
3. Distinguish a detector report, runtime warning, allocation failure, pressure symptom, and system kill event.
4. Bind the observation to the log artifact ID, line number, and line hash.
5. Keep alternative explanations until an owner path, comparison, or matching accounting evidence discriminates them.

A complete LeakCanary owner-path candidate needs a GC Root, at least one `Leaking: YES` state, and the reference path. A notification, retained-object count, `OutOfMemoryError`, GC line, or isolated `Leaking: YES` marker is not an equivalent owner path.

Capture a bounded reproduction window when QA can rerun:

```bash
adb logcat -c
# Reproduce the exact scenario.
adb logcat -d -b main,system,crash -v threadtime > logcat.txt
```

Do not use package-only filtering when the hypothesis involves LMKD, system_server, WebView renderer, GPU services, or another process. Preserve the required system/crash buffers and record any access limitation.

## Screenshot handling

The runtime validates only image format, dimensions, size, and hash; it performs no OCR and does not embed pixels. The AI must inspect every relevant attached or locally authorized screenshot.

Record only what is visibly present:

- screen/report name and selected tab or filter;
- package/process/build/device if visible;
- timestamp, phase, loop count, and units if visible;
- exact visible warning, metric, class/path, or chart point;
- cropped or hidden regions, ambiguous text, and anything inferred rather than visible.

Bind each observation to the screenshot artifact ID and a human-readable region such as `top warning`, `retained-path row 3`, or `chart 09:10-09:15`. A single chart or summary screenshot cannot prove a trend outside its visible window, and a LeakCanary notification screenshot is not the complete reference path.

## Privacy

Logs and screenshots can contain user text, URLs, account IDs, tokens, file paths, notifications, business data, and other apps' activity. Keep raw artifacts local by default, minimize the capture window and buffers, redact only on an authorized copy, and preserve the original hash. Never infer that a redacted or cropped region is empty.

## Primary references

- [Android Logcat command-line tool](https://developer.android.com/tools/logcat)
- [How LeakCanary works](https://square.github.io/leakcanary/fundamentals-how-leakcanary-works/)
- [Fixing a memory leak with a complete leak trace](https://square.github.io/leakcanary/fundamentals-fixing-a-memory-leak/)
- [StrictMode VM leak detectors](https://developer.android.com/reference/android/os/StrictMode.VmPolicy.Builder)
- [AOSP low memory killer daemon](https://source.android.com/docs/core/perf/lmkd)
